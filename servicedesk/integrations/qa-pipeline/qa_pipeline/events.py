"""Eventos no Redis Stream `sd:events` (DB 7).

Envelope FIXO do projeto (WEBHOOK_CONTRACTS.md §8.2, vinculante, publicado pelo sd-ops):
  XADD sd:events MAXLEN ~ 200000 * type <type> data <envelope JSON>
  envelope = {"type","id","occurred_at","tenant_id","version":1,"source","correlation_id","caused_by",
              "subject":{"call_id","provider_call_id","ticket_id","conversation_id"},"payload":{...}}
`id` é o event_id (deduplicar por ele). Leitura tolerante: também aceita `payload` como campo direto.

Consumimos: recording.stored (sd-ops), csat.recorded e qa.reprocess.requested (propostos pelo A3 para
o n8n/console). Publicamos no mesmo formato: transcription.completed, transcription.failed, qa.completed
(sempre pela outbox). O sd-ops não consome o stream: os resultados também vão por REST para
POST /sd-ops/api/v1/analysis-results (§8.8), ver pipeline.deliver_sdops.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

log = logging.getLogger(__name__)

CONSUMED = {"recording.stored", "csat.recorded", "qa.reprocess.requested"}


def _dec(v):
    return v.decode() if isinstance(v, (bytes, bytearray)) else v


def parse_message(fields: dict) -> Optional[dict]:
    f = {_dec(k): _dec(v) for k, v in fields.items()}
    env = None
    for key in ("data", "event", "envelope"):
        if key in f:
            try:
                env = json.loads(f[key])
            except (TypeError, json.JSONDecodeError):
                return None
            break
    if env is None:
        env = dict(f)
    if isinstance(env.get("payload"), str):
        try:
            env["payload"] = json.loads(env["payload"])
        except json.JSONDecodeError:
            return None
    if not isinstance(env, dict):
        return None
    typ = env.get("type") or f.get("type") or env.get("event_type")
    if not typ:
        return None
    payload = dict(env.get("payload") or {})
    subject = env.get("subject") if isinstance(env.get("subject"), dict) else {}
    for k in ("call_id", "ticket_id", "conversation_id"):
        if payload.get(k) in (None, "") and subject.get(k) not in (None, ""):
            payload[k] = subject[k]
    return {"type": typ, "event_id": env.get("id") or env.get("event_id"),
            "occurred_at": env.get("occurred_at"), "tenant_id": env.get("tenant_id") or payload.get("tenant_id"),
            "correlation_id": env.get("correlation_id"), "caused_by": env.get("caused_by"),
            "subject": subject, "payload": payload}


def envelope(event_type: str, payload: dict, tenant_id: str, correlation_id: Optional[str] = None,
             event_id: Optional[str] = None) -> dict:
    """Campos do XADD: type + data (envelope JSON), no mesmo formato do sd-ops."""
    env = {"type": event_type, "id": event_id or str(uuid.uuid4()),
           "occurred_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "tenant_id": tenant_id,
           "version": 1, "source": "qa-pipeline", "correlation_id": correlation_id, "caused_by": None,
           "subject": {k: payload.get(k) for k in ("call_id", "ticket_id", "conversation_id")},
           "payload": payload}
    return {"type": event_type, "data": json.dumps(env, ensure_ascii=False, default=str)}


class EventBus:
    def __init__(self, redis_client, stream: str, group: str, consumer: str, start_id: str = "0",
                 dlq: str = "sd:events:dlq:qa"):
        self.r = redis_client
        self.stream = stream
        self.group = group
        self.consumer = consumer
        self.start_id = start_id
        self.dlq = dlq

    def ensure_group(self) -> None:
        try:
            self.r.xgroup_create(self.stream, self.group, id=self.start_id, mkstream=True)
        except Exception as exc:  # BUSYGROUP: já existe
            if "BUSYGROUP" not in str(exc):
                raise

    def read(self, count: int = 10, block_ms: int = 5000):
        """Primeiro reentrega as pendentes deste consumidor (recuperação após reinício), depois novas."""
        out = []
        pending = self.r.xreadgroup(self.group, self.consumer, {self.stream: "0"}, count=count)
        for _, msgs in pending or []:
            out.extend(m for m in msgs if m[1])
        if out:
            return out
        fresh = self.r.xreadgroup(self.group, self.consumer, {self.stream: ">"}, count=count, block=block_ms)
        for _, msgs in fresh or []:
            out.extend(msgs)
        return out

    def ack(self, msg_id) -> None:
        self.r.xack(self.stream, self.group, msg_id)

    def dead_letter(self, msg_id, fields: dict, reason: str) -> None:
        data = {_dec(k): _dec(v) for k, v in fields.items()}
        data.update({"dlq_reason": reason[:500], "dlq_source_id": _dec(msg_id), "dlq_consumer": self.consumer})
        self.r.xadd(self.dlq, data, maxlen=10000, approximate=True)
        self.ack(msg_id)

    def publish(self, env: dict) -> str:
        return _dec(self.r.xadd(self.stream, env, maxlen=200000, approximate=True))
