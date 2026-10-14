"""Serialização para a API (sem dados sensíveis: nada de URL da 55PBX, CPF ou payload bruto)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from pbx_bridge.normalize import mobile_variants

from . import db, sla, tickets
from . import models as m
from .normalize55 import mask_e164

LEG_PUBLIC = ("id", "seq", "provider_call_id", "state", "direction", "branch", "agent_email", "agent_name", "queue",
              "ura", "talk_s", "wait_s", "total_s", "disconnection", "status_raw", "has_audio_url",
              "transferred_from_leg_id", "transfer_to_provider_call_id")


def call_view(conn: Connection, c: Dict[str, Any], full: bool = False) -> Dict[str, Any]:
    out = {k: c.get(k) for k in ("id", "root_provider_call_id", "direction", "state", "outcome", "status_raw",
                                  "number_e164", "contact_id", "conversation_id", "queue", "ura", "branch",
                                  "agent_email", "talk_s", "wait_s", "total_s", "disconnection", "legs_count",
                                  "needs_classification", "ticket_policy")}
    for k in ("started_at", "answered_at", "ended_at"):
        out[k] = db.iso(c.get(k))
    tks = tickets.tickets_of_call(conn, c["id"])
    out["tickets"] = [{"id": t["id"], "protocol": t["protocol"], "status": t["status"]} for t in tks]
    recs = conn.execute(sa.select(m.call_recordings).where(m.call_recordings.c.call_id == c["id"])).fetchall()
    out["recordings"] = [{"id": r.id, "leg_id": r.leg_id, "status": r.status, "mime": r.mime,
                          "duration_s": r.duration_s, "size_bytes": r.size_bytes, "integrity": r.integrity,
                          "stored_at": db.iso(r.stored_at)} for r in recs]
    cb = conn.execute(sa.select(m.callback_tasks).where(m.callback_tasks.c.call_id == c["id"])).first()
    out["callback"] = {"id": cb.id, "status": cb.status, "reason": cb.reason, "due_at": db.iso(cb.due_at)} if cb else None
    if full:
        legs = conn.execute(sa.select(m.call_legs).where(m.call_legs.c.call_id == c["id"]).order_by(
            m.call_legs.c.seq)).fetchall()
        out["legs"] = []
        for lg in legs:
            d = {k: getattr(lg, k) for k in LEG_PUBLIC}
            for k in ("started_at", "answered_at", "ended_at"):
                d[k] = db.iso(getattr(lg, k))
            out["legs"].append(d)
        out["events"] = [{"id": e.id, "kind": e.kind, "source": e.source, "received_at": db.iso(e.received_at),
                          "provider_call_id": e.provider_call_id, "anomalies": e.anomalies}
                         for e in conn.execute(sa.select(m.call_events).where(m.call_events.c.call_id == c["id"])
                                               .order_by(m.call_events.c.id)).fetchall()]
    return out


def ticket_view(conn: Connection, t: Dict[str, Any], full: bool = False) -> Dict[str, Any]:
    d = tickets.to_dict(t)
    d["sla"] = sla.ticket_sla(conn, t["id"])
    d["conversations"] = tickets.linked_conversations(conn, t["id"])
    d["calls"] = tickets.linked_calls(conn, t["id"])
    d["chatwoot_status"], d["zd_status"], _ = tickets.CHATWOOT_MAP[t["status"]]
    if full:
        d["activities"] = [{"id": a.id, "kind": a.kind, "body": a.body, "data": a.data, "call_id": a.call_id,
                            "author_id": a.author_id, "author_name": a.author_name, "created_at": db.iso(a.created_at)}
                           for a in conn.execute(sa.select(m.ticket_activities).where(
                               m.ticket_activities.c.ticket_id == t["id"]).order_by(m.ticket_activities.c.id))]
        d["allowed_transitions"] = sorted(tickets.TRANSITIONS[t["status"]])
    return d


def calls_query(tenant_id: str, conversation_id: Optional[int] = None, contact_id: Optional[int] = None,
                ticket_id: Optional[str] = None, phone: Optional[str] = None, needs_classification: Optional[bool] = None):
    c = m.calls
    q = sa.select(c).where(c.c.tenant_id == tenant_id, c.c.state != "merged")
    if conversation_id:
        q = q.where(c.c.conversation_id == conversation_id)
    if contact_id:
        q = q.where(c.c.contact_id == contact_id)
    if phone:
        q = q.where(c.c.number_e164.in_(mobile_variants(phone)))
    if ticket_id:
        q = q.where(c.c.id.in_(sa.select(m.ticket_calls.c.call_id).where(m.ticket_calls.c.ticket_id == ticket_id)))
    if needs_classification is not None:
        q = q.where(c.c.needs_classification.is_(needs_classification))
    return q.order_by(c.c.started_at.desc().nullslast(), c.c.created_at.desc())


def can_hear(conn: Connection, p, rec) -> bool:
    if p.kind == "service":
        return "recordings:read" in p.scopes
    if p.has("supervisor", "qa", "admin"):
        return True
    if not p.has("agente"):
        return False
    call = conn.execute(sa.select(m.calls).where(m.calls.c.id == rec.call_id)).first()
    if call is None:
        return False
    if p.email and (call.agent_email or "").lower() == p.email.lower():
        return True
    if p.email and conn.execute(sa.select(sa.func.count()).select_from(m.call_legs).where(
            m.call_legs.c.call_id == call.id, sa.func.lower(m.call_legs.c.agent_email) == p.email.lower())).scalar():
        return True
    return bool(conn.execute(sa.select(sa.func.count()).select_from(m.support_tickets).join(
        m.ticket_calls, m.ticket_calls.c.ticket_id == m.support_tickets.c.id).where(
        m.ticket_calls.c.call_id == call.id, m.support_tickets.c.assignee_id == p.user_id)).scalar())


def masked(n: Optional[str]) -> Optional[str]:
    return mask_e164(n)
