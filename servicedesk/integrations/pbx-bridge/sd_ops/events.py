"""Publicação no Redis Stream sd:events e entrega HMAC às rotas de automação (n8n)."""
from __future__ import annotations

import fnmatch
import hashlib
import hmac
import json
import time
from typing import Any, Dict, List, Optional

import httpx


class RedisPublisher:
    def __init__(self, url: str, key: str = "sd:events", maxlen: int = 200000):
        import redis
        self.r = redis.Redis.from_url(url, socket_timeout=5, socket_connect_timeout=5)
        self.key, self.maxlen = key, maxlen

    def publish(self, env: Dict[str, Any]) -> str:
        data = json.dumps(env, ensure_ascii=False, sort_keys=True)
        rid = self.r.xadd(self.key, {"type": env["type"], "data": data}, maxlen=self.maxlen, approximate=True)
        return rid.decode() if isinstance(rid, bytes) else str(rid)

    def ping(self) -> bool:
        return bool(self.r.ping())


class MemoryPublisher:
    """Para testes e para rodar sem Redis (o stream fica só na outbox)."""

    def __init__(self, fail: int = 0):
        self.events: List[Dict[str, Any]] = []
        self.fail = fail

    def publish(self, env: Dict[str, Any]) -> str:
        if self.fail > 0:
            self.fail -= 1
            raise ConnectionError("redis fora (simulado)")
        self.events.append(json.loads(json.dumps(env)))
        return "%d-0" % len(self.events)

    def ping(self) -> bool:
        return True

    def types(self) -> List[str]:
        return [e["type"] for e in self.events]


def route_matches(patterns: List[str], etype: str) -> bool:
    return any(fnmatch.fnmatch(etype, p) for p in patterns or [])


def sign(secret: str, ts: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()


def deliver(http: httpx.Client, url: str, env: Dict[str, Any], token: str = "", secret: str = "",
            now: Optional[float] = None) -> int:
    body = json.dumps(env, ensure_ascii=False, sort_keys=True).encode()
    ts = str(int(now or time.time()))
    headers = {"Content-Type": "application/json", "X-SD-Event-Id": env["id"], "X-SD-Event-Type": env["type"],
               "X-SD-Timestamp": ts, "X-SD-Origin": "sd-ops", "X-Correlation-Id": env.get("correlation_id") or ""}
    if token:
        headers["X-SD-Webhook-Token"] = token
    if secret:
        headers["X-SD-Signature"] = sign(secret, ts, body)
    r = http.post(url, content=body, headers=headers)
    return r.status_code
