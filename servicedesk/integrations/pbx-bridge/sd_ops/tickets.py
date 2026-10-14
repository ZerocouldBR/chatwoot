"""Domínio de ticket de negócio (modelo híbrido).

A conversa do Chatwoot é a tela de trabalho; o sd-ops guarda o ticket (protocolo, estado de negócio, SLA,
auditoria, vínculos N:N com chamadas e conversas) e sincroniza com a conversa só pela API pública
(status canônico + rótulo zd_status + atributos sd_*).
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Dict, Iterable, List, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection

from . import db, sla
from . import models as m

STATES = ("novo", "triagem", "em_atendimento", "aguardando_cliente", "aguardando_terceiro", "resolvido",
          "encerrado", "cancelado")
OPEN_STATES = ("novo", "triagem", "em_atendimento", "aguardando_cliente", "aguardando_terceiro")
FINAL = ("encerrado", "cancelado")
WAITING = ("aguardando_cliente", "aguardando_terceiro")
PRIORITIES = ("baixa", "normal", "alta", "urgente")

TRANSITIONS = {
    "novo": {"triagem", "em_atendimento", "aguardando_cliente", "aguardando_terceiro", "resolvido", "cancelado"},
    "triagem": {"em_atendimento", "aguardando_cliente", "aguardando_terceiro", "resolvido", "cancelado"},
    "em_atendimento": {"triagem", "aguardando_cliente", "aguardando_terceiro", "resolvido", "cancelado"},
    "aguardando_cliente": {"em_atendimento", "aguardando_terceiro", "resolvido", "cancelado"},
    "aguardando_terceiro": {"em_atendimento", "aguardando_cliente", "resolvido", "cancelado"},
    "resolvido": {"encerrado", "em_atendimento"},   # em_atendimento = reabertura
    "encerrado": set(),                             # reabrir = ticket de continuação (follow-up)
    "cancelado": set(),
}
# transições que exigem supervisor/admin
PRIVILEGED = {"encerrado", "cancelado"}

# estado de negócio -> (status canônico da conversa, zd_status, zd_status_sistema)
CHATWOOT_MAP = {
    "novo": ("open", "Novo", "Novo"),
    "triagem": ("open", "Aberto", "Aberto"),
    "em_atendimento": ("open", "Em andamento", "Aberto"),
    "aguardando_cliente": ("snoozed", "Pendente", "Pendente"),
    "aguardando_terceiro": ("snoozed", "Pendente", "Em espera"),
    "resolvido": ("resolved", "Resolvido", "Resolvido"),
    "encerrado": ("resolved", "Concluído", "Fechado"),
    "cancelado": ("resolved", "Concluído", "Fechado"),
}
SPOKEN = {
    "novo": "registrado e aguardando triagem", "triagem": "em triagem", "em_atendimento": "em atendimento",
    "aguardando_cliente": "aguardando informações do cliente", "aguardando_terceiro": "aguardando um parceiro",
    "resolvido": "resolvido", "encerrado": "encerrado", "cancelado": "cancelado",
}
NEXT_ACTION = {
    "novo": "aguarde o contato da equipe", "triagem": "aguarde o contato da equipe",
    "em_atendimento": "aguarde o retorno da equipe", "aguardando_cliente": "envie as informações pedidas pela equipe",
    "aguardando_terceiro": "aguarde o retorno da equipe", "resolvido": "se precisar, peça a reabertura",
    "encerrado": "abra um novo atendimento", "cancelado": "abra um novo atendimento",
}

EDITABLE = ("subject", "description", "category", "subcategory", "type", "priority", "severity", "department",
            "team_id", "team_name", "assignee_id", "organization", "contact_id", "contact_email", "contact_name",
            "needs_identification")
AUDITED = ("priority", "assignee_id", "team_id", "team_name", "status")


class TicketError(Exception):
    def __init__(self, code: str, message: str, http: int = 409):
        super().__init__(message)
        self.code, self.message, self.http = code, message, http


# ------------------------------------------------------------------ protocolo
def luhn_digit(num: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(num)):
        d = int(ch)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return str((10 - total % 10) % 10)


def luhn_ok(num: str) -> bool:
    return num.isdigit() and len(num) >= 2 and luhn_digit(num[:-1]) == num[-1]


def next_protocol(conn: Connection, tenant_id: str, prefix: str, now: Optional[dt.datetime] = None) -> Tuple[str, str]:
    """Protocolo legível (PREFIXO-AAAA-NNNNNN) + numérico para URA (AAAA NNNNNN + dígito Luhn = 11 dígitos)."""
    year = (now or db.utcnow()).astimezone(sla.ZoneInfo("America/Sao_Paulo")).year
    seq = conn.execute(pg_insert(m.protocol_counters).values(tenant_id=tenant_id, year=year, last_value=1)
                       .on_conflict_do_update(index_elements=["tenant_id", "year"],
                                              set_={"last_value": m.protocol_counters.c.last_value + 1})
                       .returning(m.protocol_counters.c.last_value)).scalar()
    base = "%04d%06d" % (year, seq)
    return "%s-%04d-%06d" % (prefix, year, seq), base + luhn_digit(base)


# ------------------------------------------------------------------ leitura
def to_dict(r) -> Dict[str, Any]:
    d = dict(r._mapping) if hasattr(r, "_mapping") else dict(r)
    for k in ("created_at", "updated_at", "first_response_at", "resolved_at", "closed_at", "cancelled_at", "deleted_at"):
        if k in d:
            d[k] = db.iso(d[k])
    return d


def get(conn: Connection, tenant_id: str, ref: str, lock: bool = False) -> Optional[Dict[str, Any]]:
    t = m.support_tickets
    q = sa.select(t).where(t.c.tenant_id == tenant_id, t.c.deleted_at.is_(None))
    ref = str(ref).strip()
    if len(ref) == 36 and ref.count("-") == 4:
        q = q.where(t.c.id == ref)
    elif ref.isdigit():
        q = q.where(t.c.protocol_numeric == ref)
    else:
        q = q.where(t.c.protocol == ref.upper())
    if lock:
        q = q.with_for_update()
    r = conn.execute(q).first()
    return dict(r._mapping) if r else None


def linked_conversations(conn: Connection, ticket_id: str) -> List[int]:
    return [r[0] for r in conn.execute(sa.select(m.ticket_conversations.c.conversation_id).where(
        m.ticket_conversations.c.ticket_id == ticket_id).order_by(m.ticket_conversations.c.created_at))]


def linked_calls(conn: Connection, ticket_id: str) -> List[str]:
    return [r[0] for r in conn.execute(sa.select(m.ticket_calls.c.call_id).where(
        m.ticket_calls.c.ticket_id == ticket_id).order_by(m.ticket_calls.c.created_at))]


def tickets_of_call(conn: Connection, call_id: str) -> List[Dict[str, Any]]:
    t = m.support_tickets
    rows = conn.execute(sa.select(t).join(m.ticket_calls, m.ticket_calls.c.ticket_id == t.c.id).where(
        m.ticket_calls.c.call_id == call_id)).fetchall()
    return [dict(r._mapping) for r in rows]


def find_reusable(conn: Connection, tenant_id: str, e164: Optional[str], contact_id: Optional[int],
                  window_hours: int, now: Optional[dt.datetime] = None) -> Optional[Dict[str, Any]]:
    """Ticket aberto mais recente do mesmo cliente (telefone E.164 ou contato) dentro da janela."""
    from pbx_bridge.normalize import mobile_variants
    if not e164 and not contact_id:
        return None
    t = m.support_tickets
    conds = []
    if e164:
        conds.append(t.c.contact_e164.in_(mobile_variants(e164)))
    if contact_id:
        conds.append(t.c.contact_id == contact_id)
    since = (now or db.utcnow()) - dt.timedelta(hours=window_hours)
    r = conn.execute(sa.select(t).where(t.c.tenant_id == tenant_id, t.c.deleted_at.is_(None),
                                        t.c.status.in_(OPEN_STATES), t.c.updated_at >= since, sa.or_(*conds))
                     .order_by(t.c.updated_at.desc()).limit(1).with_for_update()).first()
    return dict(r._mapping) if r else None


# ------------------------------------------------------------------ escrita
def _event(conn, ticket: Dict[str, Any], kind: str, actor: str, **kw: Any) -> None:
    actor_type, _, actor_id = actor.partition(":")
    conn.execute(m.ticket_events.insert().values(
        tenant_id=ticket["tenant_id"], ticket_id=ticket["id"], kind=kind, actor_type=actor_type or "system",
        actor_id=actor_id or None, correlation_id=db.obs.correlation_id(), **kw))


def _payload(t: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    p = {"ticket_id": t["id"], "protocol": t["protocol"], "protocol_numeric": t["protocol_numeric"],
         "status": t["status"], "priority": t["priority"], "channel": t["channel"], "contact_id": t.get("contact_id"),
         "team_id": t.get("team_id"), "assignee_id": t.get("assignee_id")}
    p.update(extra)
    return p


def enqueue_sync(conn: Connection, ticket: Dict[str, Any]) -> None:
    db.enqueue(conn, ticket["tenant_id"], "chatwoot.sync_ticket",
               "sync_ticket:%s:%s" % (ticket["id"], ticket["version"]), {"ticket_id": ticket["id"]},
               ordering_key="ticket:" + ticket["id"])


def _save(conn, ticket: Dict[str, Any], **changes: Any) -> Dict[str, Any]:
    now = db.utcnow()
    changes["updated_at"] = now
    changes["version"] = ticket["version"] + 1
    r = conn.execute(m.support_tickets.update().where(m.support_tickets.c.id == ticket["id"]).values(**changes)
                     .returning(m.support_tickets)).first()
    return dict(r._mapping)


def create(conn: Connection, tenant_id: str, fields: Dict[str, Any], actor: str = "system",
           call_id: Optional[str] = None, call_relation: str = "origin",
           conversation_id: Optional[int] = None, now: Optional[dt.datetime] = None) -> Dict[str, Any]:
    now = now or db.utcnow()
    ten = conn.execute(sa.select(m.tenants).where(m.tenants.c.id == tenant_id)).first()
    if ten is None:
        raise TicketError("tenant_not_found", "tenant inexistente", 404)
    prio = fields.get("priority") or "normal"
    if prio not in PRIORITIES:
        raise TicketError("invalid_priority", "prioridade inválida", 422)
    protocol, numeric = next_protocol(conn, tenant_id, ten.protocol_prefix, now)
    vals = {k: fields.get(k) for k in EDITABLE if k in fields}
    vals.update(tenant_id=tenant_id, protocol=protocol, protocol_numeric=numeric, priority=prio,
                channel=fields.get("channel") or "phone", origin=fields.get("origin") or "manual",
                subject=(fields.get("subject") or "Atendimento").strip()[:250], status=fields.get("status") or "novo",
                contact_e164=fields.get("contact_e164"), created_by=actor, created_at=now, updated_at=now,
                parent_ticket_id=fields.get("parent_ticket_id"))
    if vals["status"] not in OPEN_STATES:
        raise TicketError("invalid_status", "estado inicial inválido", 422)
    r = conn.execute(m.support_tickets.insert().values(**vals).returning(m.support_tickets)).first()
    t = dict(r._mapping)
    _event(conn, t, "created", actor, to_status=t["status"])
    if call_id:
        link_call(conn, t, call_id, call_relation, actor)
    if conversation_id:
        link_conversation(conn, t, conversation_id, actor, primary=True)
    sla.start_for_ticket(conn, t, now)
    db.publish(conn, tenant_id, "ticket.created", t["id"], _payload(t, origin=t["origin"]),
               subject={"ticket_id": t["id"], "call_id": call_id, "conversation_id": conversation_id})
    db.audit(conn, tenant_id, "ticket.created", "ticket", t["id"], {"protocol": protocol, "origin": t["origin"]},
             actor_type=actor.split(":")[0], actor_id=actor.partition(":")[2] or None)
    enqueue_sync(conn, t)
    return t


def link_call(conn: Connection, t: Dict[str, Any], call_id: str, relation: str = "related", actor: str = "system") -> bool:
    res = conn.execute(pg_insert(m.ticket_calls).values(ticket_id=t["id"], call_id=call_id, tenant_id=t["tenant_id"],
                                                         relation=relation).on_conflict_do_nothing())
    if res.rowcount:
        _event(conn, t, "linked", actor, field="call", new_value={"call_id": call_id, "relation": relation})
    return bool(res.rowcount)


def link_conversation(conn: Connection, t: Dict[str, Any], conversation_id: int, actor: str = "system",
                      primary: bool = False) -> bool:
    has_primary = conn.execute(sa.select(sa.func.count()).select_from(m.ticket_conversations).where(
        m.ticket_conversations.c.ticket_id == t["id"], m.ticket_conversations.c.is_primary.is_(True))).scalar()
    res = conn.execute(pg_insert(m.ticket_conversations).values(
        ticket_id=t["id"], conversation_id=int(conversation_id), tenant_id=t["tenant_id"],
        is_primary=bool(primary or not has_primary)).on_conflict_do_nothing())
    if res.rowcount:
        _event(conn, t, "linked", actor, field="conversation", new_value={"conversation_id": int(conversation_id)})
        enqueue_sync(conn, t)
    return bool(res.rowcount)


def transition(conn: Connection, tenant_id: str, ref: str, to: str, actor: str = "system", reason: str = "",
               roles: Iterable[str] = ("admin",), approved_by: Optional[int] = None,
               now: Optional[dt.datetime] = None) -> Dict[str, Any]:
    now = now or db.utcnow()
    t = get(conn, tenant_id, ref, lock=True)
    if t is None:
        raise TicketError("not_found", "ticket não encontrado", 404)
    if to not in STATES:
        raise TicketError("invalid_status", "estado inexistente", 422)
    frm = t["status"]
    if to == frm:
        return t
    if to not in TRANSITIONS[frm]:
        raise TicketError("invalid_transition", "transição %s -> %s não permitida" % (frm, to), 409)
    roles = set(roles)
    if to in PRIVILEGED and not roles & {"supervisor", "admin", "system", "tickets:close"}:
        raise TicketError("forbidden", "encerrar/cancelar exige supervisor", 403)
    if to == "cancelado" and not reason:
        raise TicketError("reason_required", "informe o motivo do cancelamento", 422)
    changes: Dict[str, Any] = {"status": to}
    kind = "status_changed"
    if to == "resolvido":
        changes["resolved_at"] = now
        sla.stop(conn, t["id"], "resolution", now, "resolvido")
        sla.stop(conn, t["id"], "first_response", now, "resolvido sem primeira resposta registrada")
    elif to == "encerrado":
        changes.update(closed_at=now, close_reason=reason or None, close_approved_by=approved_by)
    elif to == "cancelado":
        changes.update(cancelled_at=now, cancel_reason=reason)
        sla.stop(conn, t["id"], "resolution", now, "cancelado")
        sla.stop(conn, t["id"], "first_response", now, "cancelado")
    if frm == "resolvido" and to == "em_atendimento":
        kind = "reopened"
        changes.update(reopen_count=t["reopen_count"] + 1, resolved_at=None)
        _restart_resolution(conn, t, now)
    if to in WAITING and frm not in WAITING:
        sla.pause(conn, t["id"], now)
    if frm in WAITING and to not in WAITING:
        sla.resume(conn, t["id"], tenant_id, now)
    t2 = _save(conn, t, **changes)
    _event(conn, t2, kind, actor, from_status=frm, to_status=to, reason=reason or None)
    etype = "ticket.reopened" if kind == "reopened" else "ticket.status_changed"
    db.publish(conn, tenant_id, etype, "%s:%s" % (t2["id"], t2["version"]),
               _payload(t2, **{"from": frm, "to": to, "reason": reason, "actor": actor}),
               subject={"ticket_id": t2["id"]})
    db.audit(conn, tenant_id, etype, "ticket", t2["id"], {"from": frm, "to": to, "reason": reason},
             actor_type=actor.split(":")[0], actor_id=actor.partition(":")[2] or None)
    enqueue_sync(conn, t2)
    return t2


def _restart_resolution(conn, t: Dict[str, Any], now: dt.datetime) -> None:
    bh = sla.tenant_bh(conn, t["tenant_id"])
    for r in conn.execute(sa.select(m.sla_instances).where(m.sla_instances.c.ticket_id == t["id"],
                                                           m.sla_instances.c.metric == "resolution")).fetchall():
        due = bh.add(now, r.target_min)
        conn.execute(m.sla_instances.update().where(m.sla_instances.c.id == r.id).values(
            status="running", started_at=now, due_at=due, stopped_at=None, breached=False, breached_at=None,
            paused_at=None, updated_at=now))
        conn.execute(m.sla_events.insert().values(tenant_id=t["tenant_id"], sla_instance_id=r.id, ticket_id=t["id"],
                                                  kind="restarted", at=now, data={"due_at": db.iso(due)}))


def reopen(conn: Connection, tenant_id: str, ref: str, actor: str, reason: str,
           roles: Iterable[str] = ("admin",)) -> Tuple[Dict[str, Any], bool]:
    """Reabre (resolvido -> em_atendimento) ou cria ticket de continuação (encerrado/cancelado).
    Devolve (ticket, criado_novo)."""
    t = get(conn, tenant_id, ref, lock=True)
    if t is None:
        raise TicketError("not_found", "ticket não encontrado", 404)
    if t["status"] == "resolvido":
        return transition(conn, tenant_id, t["id"], "em_atendimento", actor, reason or "reabertura", roles), False
    if t["status"] in FINAL:
        new = create(conn, tenant_id, {
            "subject": t["subject"], "description": "Continuação do protocolo %s. %s" % (t["protocol"], reason or ""),
            "contact_id": t["contact_id"], "contact_e164": t["contact_e164"], "contact_email": t["contact_email"],
            "contact_name": t["contact_name"], "channel": t["channel"], "origin": "followup", "priority": t["priority"],
            "team_id": t["team_id"], "team_name": t["team_name"], "assignee_id": t["assignee_id"],
            "category": t["category"], "subcategory": t["subcategory"], "parent_ticket_id": t["id"],
            "status": "em_atendimento"}, actor)
        for cid in linked_conversations(conn, t["id"]):
            link_conversation(conn, new, cid, actor)
        _event(conn, t, "followup_created", actor, new_value={"ticket_id": new["id"], "protocol": new["protocol"]},
               reason=reason or None)
        conn.execute(m.ticket_events.insert().values(
            tenant_id=tenant_id, ticket_id=new["id"], kind="reopened", from_status=t["status"],
            to_status="em_atendimento", reason="continuação de %s" % t["protocol"], actor_type=actor.split(":")[0],
            actor_id=actor.partition(":")[2] or None))
        db.publish(conn, tenant_id, "ticket.reopened", "%s:followup:%s" % (t["id"], new["id"]),
                   _payload(new, **{"from": t["status"], "to": "em_atendimento", "parent_ticket_id": t["id"],
                                    "reason": reason, "actor": actor}), subject={"ticket_id": new["id"]})
        return new, True
    raise TicketError("not_reopenable", "o ticket ainda está aberto", 409)


def escalate(conn: Connection, tenant_id: str, ref: str, actor: str, reason: str,
             priority: Optional[str] = None, team_id: Optional[int] = None, team_name: Optional[str] = None) -> Dict[str, Any]:
    t = get(conn, tenant_id, ref, lock=True)
    if t is None:
        raise TicketError("not_found", "ticket não encontrado", 404)
    if t["status"] not in OPEN_STATES:
        raise TicketError("not_open", "só tickets abertos podem ser escalonados", 409)
    if not priority:
        i = PRIORITIES.index(t["priority"])
        priority = PRIORITIES[min(i + 1, len(PRIORITIES) - 1)]
    if priority not in PRIORITIES:
        raise TicketError("invalid_priority", "prioridade inválida", 422)
    changes: Dict[str, Any] = {"escalation_level": t["escalation_level"] + 1, "priority": priority}
    if team_id is not None:
        changes["team_id"] = team_id
    if team_name is not None:
        changes["team_name"] = team_name
    t2 = _save(conn, t, **changes)
    _event(conn, t2, "escalated", actor, old_value={"priority": t["priority"], "team_id": t["team_id"],
                                                    "level": t["escalation_level"]},
           new_value={"priority": priority, "team_id": t2["team_id"], "level": t2["escalation_level"]},
           reason=reason or None)
    sla.start_for_ticket(conn, t2)
    db.publish(conn, tenant_id, "ticket.escalated", "%s:%s" % (t2["id"], t2["version"]),
               _payload(t2, level=t2["escalation_level"], reason=reason, actor=actor), subject={"ticket_id": t2["id"]})
    db.audit(conn, tenant_id, "ticket.escalated", "ticket", t2["id"], {"priority": priority, "reason": reason},
             actor_type=actor.split(":")[0], actor_id=actor.partition(":")[2] or None)
    enqueue_sync(conn, t2)
    return t2


def update(conn: Connection, tenant_id: str, ref: str, changes: Dict[str, Any], actor: str,
           expected_version: Optional[int] = None) -> Dict[str, Any]:
    t = get(conn, tenant_id, ref, lock=True)
    if t is None:
        raise TicketError("not_found", "ticket não encontrado", 404)
    if expected_version is not None and expected_version != t["version"]:
        raise TicketError("version_conflict", "o ticket mudou; recarregue", 409)
    bad = [k for k in changes if k not in EDITABLE]
    if bad:
        raise TicketError("invalid_field", "campos não editáveis: " + ", ".join(bad), 422)
    if "priority" in changes and changes["priority"] not in PRIORITIES:
        raise TicketError("invalid_priority", "prioridade inválida", 422)
    diff = {k: v for k, v in changes.items() if t.get(k) != v}
    if not diff:
        return t
    t2 = _save(conn, t, **diff)
    for k, v in diff.items():
        _event(conn, t2, "field_changed", actor, field=k, old_value={"v": t.get(k)}, new_value={"v": v})
        if k in AUDITED:
            db.audit(conn, tenant_id, "ticket.%s_changed" % k, "ticket", t2["id"], {"old": t.get(k), "new": v},
                     actor_type=actor.split(":")[0], actor_id=actor.partition(":")[2] or None)
    if {"priority", "team_name", "team_id"} & set(diff):
        sla.start_for_ticket(conn, t2)
    enqueue_sync(conn, t2)
    return t2


def add_activity(conn: Connection, t: Dict[str, Any], kind: str, body: Optional[str], data: Optional[dict] = None,
                 actor: str = "system", author_name: Optional[str] = None, call_id: Optional[str] = None,
                 mirror_to_chatwoot: bool = False, dedup_key: Optional[str] = None) -> Optional[Dict[str, Any]]:
    stmt = pg_insert(m.ticket_activities).values(
        tenant_id=t["tenant_id"], ticket_id=t["id"], kind=kind, body=body, data=data or {}, call_id=call_id,
        author_id=actor, author_name=author_name, dedup_key=dedup_key).on_conflict_do_nothing(
        index_elements=["dedup_key"]).returning(m.ticket_activities)
    r = conn.execute(stmt).first()
    if r is None:
        return None
    a = dict(r._mapping)
    if mirror_to_chatwoot:
        db.enqueue(conn, t["tenant_id"], "chatwoot.note", "note:%s" % a["id"], {"activity_id": a["id"]},
                   ordering_key="ticket:" + t["id"])
    return a


def record_first_response(conn: Connection, tenant_id: str, ticket_id: str, at: dt.datetime, source: str) -> bool:
    t = get(conn, tenant_id, ticket_id, lock=True)
    if t is None or t["first_response_at"] is not None:
        return False
    _save(conn, t, first_response_at=at)
    sla.stop(conn, ticket_id, "first_response", at, source)
    _event(conn, t, "first_response", "system", reason=source)
    return True
