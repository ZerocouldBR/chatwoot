"""Acesso ao Postgres (SQLAlchemy Core) e utilitários comuns (outbox, auditoria, hora UTC)."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection, Engine

from . import models as m
from . import obs

UUID_NS = uuid.UUID("5b1d0b7e-55b0-4c1e-9d0e-5d0c5d0e0001")


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def make_engine(url: str, pool_size: int = 5) -> Engine:
    return sa.create_engine(url, pool_size=pool_size, max_overflow=10, pool_pre_ping=True, future=True,
                            connect_args={"options": "-c timezone=UTC"} if url.startswith("postgresql") else {})


def sha256(s: Any) -> str:
    if not isinstance(s, (bytes, bytearray)):
        s = str(s).encode("utf-8")
    return hashlib.sha256(s).hexdigest()


def stable_id(*parts: Any) -> str:
    """UUID v5 determinístico (ids de evento do stream)."""
    return str(uuid.uuid5(UUID_NS, "|".join(str(p) for p in parts)))


def jdump(o: Any) -> str:
    return json.dumps(o, ensure_ascii=False, sort_keys=True, default=str)


def iso(d: Optional[dt.datetime]) -> Optional[str]:
    if d is None:
        return None
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ------------------------------------------------------------------ outbox
def enqueue(conn: Connection, tenant_id: str, kind: str, dedup_key: str, payload: Dict[str, Any],
            ordering_key: Optional[str] = None, delay_s: float = 0) -> bool:
    """Insere um item na outbox (idempotente pela dedup_key). True se for novo."""
    stmt = pg_insert(m.outbox).values(
        tenant_id=tenant_id, kind=kind, dedup_key=dedup_key, payload=payload, ordering_key=ordering_key,
        next_attempt_at=utcnow() + dt.timedelta(seconds=delay_s), correlation_id=obs.correlation_id(),
    ).on_conflict_do_nothing(index_elements=["dedup_key"])
    return conn.execute(stmt).rowcount == 1


def publish(conn: Connection, tenant_id: str, etype: str, natural_key: str, payload: Dict[str, Any],
            occurred_at: Optional[dt.datetime] = None, subject: Optional[Dict[str, Any]] = None) -> bool:
    """Evento para o stream sd:events, via outbox (só sai se a transação for confirmada).
    O id é determinístico (tipo + tenant + chave natural): reprocessar não gera evento novo."""
    eid = stable_id(etype, tenant_id, natural_key)
    ctx = obs.current()
    env = {"type": etype, "id": eid, "occurred_at": iso(occurred_at or utcnow()), "tenant_id": tenant_id,
           "version": 1, "source": "sd-ops", "correlation_id": ctx.get("correlation_id"),
           "caused_by": ctx.get("caused_by"), "subject": subject or {}, "payload": payload}
    return enqueue(conn, tenant_id, "stream", "stream:" + eid, env)


def audit(conn: Connection, tenant_id: Optional[str], action: str, entity_type: Optional[str] = None,
          entity_id: Optional[str] = None, data: Optional[Dict[str, Any]] = None, actor_type: str = "system",
          actor_id: Optional[str] = None, ip: Optional[str] = None) -> None:
    conn.execute(m.audit_events.insert().values(
        tenant_id=tenant_id, action=action, entity_type=entity_type, entity_id=entity_id and str(entity_id),
        data=data or {}, actor_type=actor_type, actor_id=actor_id and str(actor_id), ip=ip,
        correlation_id=obs.correlation_id()))


def sync_log(conn: Connection, tenant_id: Optional[str], target: str, operation: str, status: str,
             entity_type: Optional[str] = None, entity_id: Optional[str] = None, duration_ms: Optional[int] = None,
             error: Optional[str] = None) -> None:
    conn.execute(m.integration_sync_logs.insert().values(
        tenant_id=tenant_id, target=target, operation=operation, status=status, entity_type=entity_type,
        entity_id=entity_id and str(entity_id), duration_ms=duration_ms, error=(error or None) and error[:1000],
        correlation_id=obs.correlation_id()))


def kv_get(conn: Connection, k: str) -> Optional[str]:
    r = conn.execute(sa.select(m.kv.c.v).where(m.kv.c.k == k)).first()
    return r[0] if r else None


def kv_set(conn: Connection, k: str, v: str) -> None:
    conn.execute(pg_insert(m.kv).values(k=k, v=v, updated_at=utcnow()).on_conflict_do_update(
        index_elements=["k"], set_={"v": v, "updated_at": utcnow()}))


def row(r) -> Optional[Dict[str, Any]]:
    return dict(r._mapping) if r is not None else None
