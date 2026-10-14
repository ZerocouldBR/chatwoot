"""Observabilidade: logs estruturados (JSON) com correlation id, contexto de rastreio e métricas Prometheus."""
from __future__ import annotations

import contextlib
import contextvars
import json
import logging
import threading
import time
import uuid
from typing import Dict, Iterator, Optional, Tuple

from pbx_bridge.normalize import mask

CTX: contextvars.ContextVar[Dict[str, str]] = contextvars.ContextVar("sdops_ctx", default={})


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def current() -> Dict[str, str]:
    return CTX.get()


def correlation_id() -> Optional[str]:
    return CTX.get().get("correlation_id")


@contextlib.contextmanager
def context(**kw: Optional[str]) -> Iterator[Dict[str, str]]:
    base = dict(CTX.get())
    base.update({k: str(v) for k, v in kw.items() if v is not None})
    if "correlation_id" not in base:
        base["correlation_id"] = new_correlation_id()
    tok = CTX.set(base)
    try:
        yield base
    finally:
        CTX.reset(tok)


def bind(**kw: Optional[str]) -> None:
    base = dict(CTX.get())
    base.update({k: str(v) for k, v in kw.items() if v is not None})
    CTX.set(base)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + ".%03dZ" % record.msecs,
            "level": record.levelname,
            "logger": record.name,
            "msg": mask(record.getMessage()),
        }
        out.update(CTX.get())
        if record.exc_info:
            out["exc"] = mask(self.formatException(record.exc_info))[-2000:]
        return json.dumps(out, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ctx = " ".join("%s=%s" % kv for kv in sorted(CTX.get().items()))
        base = "%s %s %s: %s" % (self.formatTime(record), record.levelname, record.name, mask(record.getMessage()))
        return base + (" [" + ctx + "]" if ctx else "")


def setup_logging(level: str = "INFO", json_logs: bool = True) -> None:
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter() if json_logs else TextFormatter())
    root.handlers[:] = [h]
    for noisy in ("httpx", "httpcore", "uvicorn.access", "botocore", "boto3", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


# ------------------------------------------------------------------ métricas (Prometheus, sem dependência)
class Metrics:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.counters: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], float] = {}
        self.sums: Dict[Tuple[str, Tuple[Tuple[str, str], ...]], Tuple[float, int]] = {}
        self.help: Dict[str, str] = {}

    def inc(self, name: str, n: float = 1, help: str = "", **labels: str) -> None:
        key = (name, tuple(sorted((k, str(v)) for k, v in labels.items())))
        with self.lock:
            self.counters[key] = self.counters.get(key, 0) + n
            if help:
                self.help.setdefault(name, help)

    def observe(self, name: str, value: float, help: str = "", **labels: str) -> None:
        key = (name, tuple(sorted((k, str(v)) for k, v in labels.items())))
        with self.lock:
            s, c = self.sums.get(key, (0.0, 0))
            self.sums[key] = (s + value, c + 1)
            if help:
                self.help.setdefault(name, help)

    @contextlib.contextmanager
    def timer(self, name: str, **labels: str) -> Iterator[None]:
        t = time.monotonic()
        try:
            yield
        finally:
            self.observe(name, time.monotonic() - t, **labels)

    def render(self, gauges: Optional[Dict[str, float]] = None) -> str:
        lines = []

        def lab(ls):
            return "{" + ",".join('%s="%s"' % (k, v.replace('"', "'")) for k, v in ls) + "}" if ls else ""

        with self.lock:
            seen = set()
            for (name, ls), v in sorted(self.counters.items()):
                if name not in seen:
                    lines.append("# TYPE %s counter" % name)
                    seen.add(name)
                lines.append("%s%s %s" % (name, lab(ls), v))
            for (name, ls), (s, c) in sorted(self.sums.items()):
                if name not in seen:
                    lines.append("# TYPE %s summary" % name)
                    seen.add(name)
                lines.append("%s_sum%s %.6f" % (name, lab(ls), s))
                lines.append("%s_count%s %d" % (name, lab(ls), c))
        for k, v in sorted((gauges or {}).items()):
            lines.append("# TYPE %s gauge" % k)
            lines.append("%s %s" % (k, v))
        return "\n".join(lines) + "\n"


METRICS = Metrics()
