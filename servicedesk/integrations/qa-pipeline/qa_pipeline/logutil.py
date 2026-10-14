"""Logs estruturados (JSON por linha) com correlation_id, recording_id, call_id e job_id.
Nunca logar texto de transcrição, tokens ou dados pessoais."""
from __future__ import annotations

import json
import logging
import sys
import time

CTX_FIELDS = ("correlation_id", "recording_id", "call_id", "job_id", "conversation_id", "event_type", "stage")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)) + "Z",
               "level": record.levelname, "logger": record.name, "msg": record.getMessage()}
        for f in CTX_FIELDS:
            v = getattr(record, f, None)
            if v is not None:
                out[f] = v
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info).splitlines()[-1][:500]
        return json.dumps(out, ensure_ascii=False)


def setup(level: str = "INFO") -> None:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [h]
    root.setLevel(level)
    for noisy in ("httpx", "httpcore", "faster_whisper", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
