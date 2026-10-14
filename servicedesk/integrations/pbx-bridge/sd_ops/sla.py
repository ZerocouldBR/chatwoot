"""SLA próprio (primeira resposta e resolução) em horário comercial.

Horário padrão "Padrão B2B": segunda a sexta, 09:00–18:00, America/Sao_Paulo (o mesmo do Zendesk e das inboxes
do Chatwoot). Política escolhida pela primeira regra ativa (ordem `sort`) que casa prioridade, time e canal.
Pausa "por dependência" (aguardando cliente/terceiro) desconta o tempo útil parado do prazo de resolução.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy.engine import Connection

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from backports.zoneinfo import ZoneInfo  # type: ignore

from . import db
from . import models as m

DEFAULT_SCHEDULE = {str(d): [["09:00", "18:00"]] for d in range(5)}
DEFAULT_BH_NAME = "Padrão B2B"

# minutos úteis por prioridade (padrão; ajustável em ops.sla_policies)
DEFAULT_POLICIES = [
    {"name": "Urgente", "priority": "urgente", "first_response_min": 30, "resolution_min": 4 * 60, "sort": 10},
    {"name": "Alta", "priority": "alta", "first_response_min": 60, "resolution_min": 8 * 60, "sort": 20},
    {"name": "Normal", "priority": "normal", "first_response_min": 4 * 60, "resolution_min": 3 * 9 * 60, "sort": 30},
    {"name": "Baixa", "priority": "baixa", "first_response_min": 8 * 60, "resolution_min": 5 * 9 * 60, "sort": 40},
]


@dataclass
class BusinessHours:
    tz: str = "America/Sao_Paulo"
    schedule: Dict[str, List[List[str]]] = field(default_factory=lambda: dict(DEFAULT_SCHEDULE))
    holidays: List[str] = field(default_factory=list)

    def _windows(self, day: dt.date) -> List[Tuple[dt.datetime, dt.datetime]]:
        if day.isoformat() in self.holidays:
            return []
        z = ZoneInfo(self.tz)
        out = []
        for a, b in self.schedule.get(str(day.weekday()), []):
            ha, ma = (int(x) for x in a.split(":"))
            hb, mb = (int(x) for x in b.split(":"))
            s = dt.datetime(day.year, day.month, day.day, ha, ma, tzinfo=z)
            e = dt.datetime(day.year, day.month, day.day, hb, mb, tzinfo=z)
            out.append((s.astimezone(dt.timezone.utc), e.astimezone(dt.timezone.utc)))
        return out

    def is_open(self, t: dt.datetime) -> bool:
        local = t.astimezone(ZoneInfo(self.tz)).date()
        return any(s <= t < e for s, e in self._windows(local))

    def add(self, start: dt.datetime, minutes: float) -> dt.datetime:
        """start + N minutos úteis."""
        remaining = dt.timedelta(minutes=minutes)
        day = start.astimezone(ZoneInfo(self.tz)).date()
        for _ in range(3660):
            for s, e in self._windows(day):
                if e <= start:
                    continue
                s = max(s, start)
                if e - s >= remaining:
                    return s + remaining
                remaining -= e - s
            day += dt.timedelta(days=1)
        raise ValueError("horário comercial sem janelas")

    def seconds_between(self, a: dt.datetime, b: dt.datetime) -> float:
        if b <= a:
            return 0.0
        total = 0.0
        day = a.astimezone(ZoneInfo(self.tz)).date()
        last = b.astimezone(ZoneInfo(self.tz)).date()
        while day <= last:
            for s, e in self._windows(day):
                lo, hi = max(s, a), min(e, b)
                if hi > lo:
                    total += (hi - lo).total_seconds()
            day += dt.timedelta(days=1)
        return total

    def next_open(self, t: dt.datetime) -> dt.datetime:
        return self.add(t, 0) if not self.is_open(t) else t


def load_bh(conn: Connection, bh_id: Optional[int]) -> BusinessHours:
    q = sa.select(m.business_hours)
    q = q.where(m.business_hours.c.id == bh_id) if bh_id else q.where(m.business_hours.c.name == DEFAULT_BH_NAME)
    r = conn.execute(q).first()
    if not r:
        return BusinessHours()
    return BusinessHours(tz=r.timezone, schedule=r.schedule, holidays=list(r.holidays or []))


def tenant_bh(conn: Connection, tenant_id: str) -> BusinessHours:
    t = conn.execute(sa.select(m.tenants.c.business_hours_id).where(m.tenants.c.id == tenant_id)).first()
    return load_bh(conn, t[0] if t else None)


def pick_policy(conn: Connection, tenant_id: str, priority: str, team_name: Optional[str],
                channel: Optional[str]) -> Optional[Dict[str, Any]]:
    rows = conn.execute(sa.select(m.sla_policies).where(
        m.sla_policies.c.tenant_id == tenant_id, m.sla_policies.c.active.is_(True)).order_by(
        m.sla_policies.c.sort, m.sla_policies.c.id)).fetchall()
    for r in rows:
        if r.priority and r.priority != priority:
            continue
        if r.team_name and (team_name or "").strip().lower() != r.team_name.strip().lower():
            continue
        if r.channel and r.channel != channel:
            continue
        return dict(r._mapping)
    return None


def _event(conn, inst: Dict[str, Any], kind: str, at: dt.datetime, data: Optional[dict] = None) -> None:
    conn.execute(m.sla_events.insert().values(tenant_id=inst["tenant_id"], sla_instance_id=inst["id"],
                                              ticket_id=inst["ticket_id"], kind=kind, at=at, data=data or {}))


def start_for_ticket(conn: Connection, ticket: Dict[str, Any], now: Optional[dt.datetime] = None) -> List[Dict]:
    """Cria (ou recalcula, se a prioridade/time mudou) as instâncias de SLA do ticket."""
    now = now or db.utcnow()
    pol = pick_policy(conn, ticket["tenant_id"], ticket["priority"], ticket.get("team_name"), ticket.get("channel"))
    if not pol:
        return []
    bh = load_bh(conn, pol.get("business_hours_id")) if pol.get("business_hours_id") else tenant_bh(conn, ticket["tenant_id"])
    out = []
    for metric, target in (("first_response", pol.get("first_response_min")), ("resolution", pol.get("resolution_min"))):
        if not target:
            continue
        if metric == "first_response" and ticket.get("first_response_at"):
            continue
        cur = conn.execute(sa.select(m.sla_instances).where(
            m.sla_instances.c.ticket_id == ticket["id"], m.sla_instances.c.metric == metric)).first()
        if cur is None:
            started = ticket.get("created_at") or now
            due = bh.add(started, target)
            r = conn.execute(m.sla_instances.insert().values(
                tenant_id=ticket["tenant_id"], ticket_id=ticket["id"], policy_id=pol["id"], metric=metric,
                status="running", target_min=target, started_at=started, due_at=due).returning(m.sla_instances)).first()
            inst = dict(r._mapping)
            _event(conn, inst, "started", now, {"policy": pol["name"], "due_at": db.iso(due)})
            out.append(inst)
        elif cur.status != "stopped" and (cur.policy_id != pol["id"] or cur.target_min != target):
            inst = dict(cur._mapping)
            paused_s = 0.0
            # prazo recalculado a partir do início, descontando o tempo útil já pausado
            elapsed_paused = conn.execute(sa.select(sa.func.coalesce(sa.func.sum(
                sa.cast(m.sla_events.c.data["paused_business_s"].astext, sa.Float)), 0)).where(
                m.sla_events.c.sla_instance_id == inst["id"], m.sla_events.c.kind == "resumed")).scalar() or 0
            paused_s = float(elapsed_paused)
            due = bh.add(inst["started_at"], target + paused_s / 60.0)
            conn.execute(m.sla_instances.update().where(m.sla_instances.c.id == inst["id"]).values(
                policy_id=pol["id"], target_min=target, due_at=due, updated_at=now))
            _event(conn, inst, "recalculated", now, {"policy": pol["name"], "due_at": db.iso(due)})
    return out


def _instances(conn, ticket_id: str, metric: Optional[str] = None):
    q = sa.select(m.sla_instances).where(m.sla_instances.c.ticket_id == ticket_id)
    if metric:
        q = q.where(m.sla_instances.c.metric == metric)
    return [dict(r._mapping) for r in conn.execute(q.with_for_update()).fetchall()]


def stop(conn: Connection, ticket_id: str, metric: str, now: Optional[dt.datetime] = None, reason: str = "") -> None:
    now = now or db.utcnow()
    for inst in _instances(conn, ticket_id, metric):
        if inst["status"] == "stopped":
            continue
        conn.execute(m.sla_instances.update().where(m.sla_instances.c.id == inst["id"]).values(
            status="stopped", stopped_at=now, updated_at=now))
        _event(conn, inst, "met" if not inst["breached"] and now <= inst["due_at"] else "stopped_late", now,
               {"reason": reason})


def pause(conn: Connection, ticket_id: str, now: Optional[dt.datetime] = None) -> None:
    now = now or db.utcnow()
    for inst in _instances(conn, ticket_id, "resolution"):
        if inst["status"] != "running":
            continue
        pol = conn.execute(sa.select(m.sla_policies.c.pause_on_waiting).where(
            m.sla_policies.c.id == inst["policy_id"])).first()
        if pol is not None and not pol[0]:
            continue
        conn.execute(m.sla_instances.update().where(m.sla_instances.c.id == inst["id"]).values(
            status="paused", paused_at=now, updated_at=now))
        _event(conn, inst, "paused", now)


def resume(conn: Connection, ticket_id: str, tenant_id: str, now: Optional[dt.datetime] = None) -> None:
    now = now or db.utcnow()
    bh = None
    for inst in _instances(conn, ticket_id, "resolution"):
        if inst["status"] != "paused":
            continue
        bh = bh or tenant_bh(conn, tenant_id)
        paused_s = bh.seconds_between(inst["paused_at"], now)
        # o prazo anda o mesmo tempo útil que ficou pausado
        remaining_s = bh.seconds_between(inst["paused_at"], inst["due_at"]) if inst["due_at"] > inst["paused_at"] else 0
        due = bh.add(now, remaining_s / 60.0) if remaining_s > 0 else inst["due_at"]
        conn.execute(m.sla_instances.update().where(m.sla_instances.c.id == inst["id"]).values(
            status="running", paused_at=None, due_at=due, updated_at=now))
        _event(conn, inst, "resumed", now, {"paused_business_s": paused_s, "due_at": db.iso(due)})


def check_breaches(conn: Connection, now: Optional[dt.datetime] = None, limit: int = 200) -> int:
    """Marca instâncias vencidas e publica sla.breached (uma vez por instância)."""
    now = now or db.utcnow()
    rows = conn.execute(sa.select(m.sla_instances).where(
        m.sla_instances.c.status == "running", m.sla_instances.c.breached.is_(False),
        m.sla_instances.c.due_at < now).limit(limit).with_for_update(skip_locked=True)).fetchall()
    for r in rows:
        inst = dict(r._mapping)
        conn.execute(m.sla_instances.update().where(m.sla_instances.c.id == inst["id"]).values(
            breached=True, breached_at=now, updated_at=now))
        _event(conn, inst, "breached", now)
        t = conn.execute(sa.select(m.support_tickets.c.protocol).where(m.support_tickets.c.id == inst["ticket_id"])).first()
        db.publish(conn, inst["tenant_id"], "sla.breached", "%s:%s" % (inst["ticket_id"], inst["metric"]),
                   {"ticket_id": inst["ticket_id"], "protocol": t[0] if t else None, "metric": inst["metric"],
                    "due_at": db.iso(inst["due_at"])}, subject={"ticket_id": inst["ticket_id"]})
        db.audit(conn, inst["tenant_id"], "sla.breached", "ticket", inst["ticket_id"], {"metric": inst["metric"]})
    return len(rows)


def ticket_sla(conn: Connection, ticket_id: str, now: Optional[dt.datetime] = None) -> List[Dict[str, Any]]:
    now = now or db.utcnow()
    out = []
    for r in conn.execute(sa.select(m.sla_instances).where(m.sla_instances.c.ticket_id == ticket_id)).fetchall():
        out.append({"metric": r.metric, "status": r.status, "breached": r.breached or (r.status == "running" and r.due_at < now),
                    "due_at": db.iso(r.due_at), "stopped_at": db.iso(r.stopped_at), "target_min": r.target_min})
    return out
