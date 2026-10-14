"""Métricas para dashboards (telefonia e tickets). Fórmulas documentadas em WEBHOOK_CONTRACTS.md §8.7."""
from __future__ import annotations

import datetime as dt
import statistics
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from . import db
from . import models as m

ABANDON = ("abandoned_ura", "abandoned_queue")
LOST = ("missed", "after_hours", "dropped")


def _ratio(a: float, b: float) -> Optional[float]:
    return round(a / b, 4) if b else None


def _avg(xs: List[float]) -> Optional[float]:
    return round(sum(xs) / len(xs), 1) if xs else None


def telephony(conn: Connection, tenant_id: str, start: dt.datetime, end: dt.datetime, sl_threshold_s: int,
              short_abandon_s: int, filters: Dict[str, Any], group_by: Optional[str] = None,
              detail: bool = False) -> Dict[str, Any]:
    c = m.calls
    q = sa.select(c).where(c.c.tenant_id == tenant_id, c.c.state == "ended", c.c.started_at >= start,
                           c.c.started_at < end)
    for k in ("queue", "branch", "agent_email", "direction"):
        if filters.get(k):
            q = q.where(getattr(c.c, k) == filters[k])
    rows = [dict(r._mapping) for r in conn.execute(q).fetchall()]
    groups: Dict[str, List[Dict[str, Any]]] = {"total": rows}
    if group_by in ("queue", "branch", "agent_email", "direction"):
        for r in rows:
            groups.setdefault("%s=%s" % (group_by, r.get(group_by) or "-"), []).append(r)
    elif group_by == "day":
        for r in rows:
            groups.setdefault("day=%s" % r["started_at"].date().isoformat(), []).append(r)
    out = {k: _tel(v, sl_threshold_s, short_abandon_s, detail) for k, v in groups.items()}
    cb = m.callback_tasks
    cbq = sa.select(cb.c.status, sa.func.count()).where(cb.c.tenant_id == tenant_id, cb.c.created_at >= start,
                                                        cb.c.created_at < end).group_by(cb.c.status)
    cbs = {s: n for s, n in conn.execute(cbq)}
    overdue = conn.execute(sa.select(sa.func.count()).select_from(cb).where(
        cb.c.tenant_id == tenant_id, cb.c.status == "pending", cb.c.due_at < db.utcnow())).scalar()
    return {"from": db.iso(start), "to": db.iso(end), "sl_threshold_s": sl_threshold_s,
            "short_abandon_s": short_abandon_s, "groups": out,
            "callbacks": {"criados": sum(cbs.values()), "concluidos": cbs.get("done", 0),
                          "pendentes": cbs.get("pending", 0), "cancelados": cbs.get("cancelled", 0),
                          "vencidos_agora": overdue},
            "fonte": "ops.calls (webhook tempo real + reconciliação Report02)"}


def _tel(rows: List[Dict[str, Any]], T: int, short: int, detail: bool) -> Dict[str, Any]:
    inb = [r for r in rows if r["direction"] == "receptivo"]
    outb = [r for r in rows if r["direction"] == "ativo"]
    answered = [r for r in inb if r.get("answered_at") or (r.get("talk_s") or 0) > 0]
    aband = [r for r in inb if r.get("outcome") in ABANDON]
    lost = [r for r in inb if r.get("outcome") in LOST]
    out_ans = [r for r in outb if (r.get("talk_s") or 0) > 0]
    within = [r for r in answered if (r.get("wait_s") or 0) <= T]
    aband_long = [r for r in aband if (r.get("wait_s") or 0) > short]
    res = {
        "recebidas": len(inb), "atendidas": len(answered), "abandonadas": len(aband), "perdidas": len(lost),
        "efetuadas": len(outb), "efetuadas_atendidas": len(out_ans),
        "tma_receptivo_s": _avg([r["talk_s"] for r in answered if r.get("talk_s") is not None]),
        "tma_ativo_s": _avg([r["talk_s"] for r in out_ans]),
        "tme_s": _avg([r["wait_s"] for r in answered if r.get("wait_s") is not None]),
        "tme_abandono_s": _avg([r["wait_s"] for r in aband if r.get("wait_s") is not None]),
        "nivel_servico": _ratio(len(within), len(answered) + len(aband_long)),
        "taxa_abandono": _ratio(len(aband), len(inb)),
        "transferidas": len([r for r in rows if (r.get("legs_count") or 1) > 1]),
        "por_resultado": {},
    }
    for r in rows:
        k = r.get("outcome") or "unknown"
        res["por_resultado"][k] = res["por_resultado"].get(k, 0) + 1
    if detail:
        res["ids"] = {"atendidas": [r["id"] for r in answered], "abandonadas": [r["id"] for r in aband],
                      "perdidas": [r["id"] for r in lost]}
    return res


def ticket_metrics(conn: Connection, tenant_id: str, start: dt.datetime, end: dt.datetime,
                   group_by: Optional[str] = None, detail: bool = False) -> Dict[str, Any]:
    t = m.support_tickets
    base = sa.select(t).where(t.c.tenant_id == tenant_id, t.c.deleted_at.is_(None))
    created = [dict(r._mapping) for r in conn.execute(base.where(t.c.created_at >= start, t.c.created_at < end))]
    resolved = [dict(r._mapping) for r in conn.execute(base.where(t.c.resolved_at >= start, t.c.resolved_at < end))]
    backlog = conn.execute(sa.select(sa.func.count()).select_from(t).where(
        t.c.tenant_id == tenant_id, t.c.deleted_at.is_(None),
        t.c.status.in_(("novo", "triagem", "em_atendimento", "aguardando_cliente", "aguardando_terceiro")))).scalar()
    reopen = conn.execute(sa.select(sa.func.count()).select_from(m.ticket_events).where(
        m.ticket_events.c.tenant_id == tenant_id, m.ticket_events.c.kind == "reopened",
        m.ticket_events.c.created_at >= start, m.ticket_events.c.created_at < end)).scalar()
    si = m.sla_instances
    sla_rows = conn.execute(sa.select(si.c.metric, si.c.breached, si.c.status, si.c.due_at, si.c.stopped_at).where(
        si.c.tenant_id == tenant_id, si.c.started_at >= start, si.c.started_at < end)).fetchall()
    sla_out: Dict[str, Any] = {}
    now = db.utcnow()
    for metric in ("first_response", "resolution"):
        rs = [r for r in sla_rows if r.metric == metric]
        stopped = [r for r in rs if r.status == "stopped"]
        ok = [r for r in stopped if not r.breached and r.stopped_at <= r.due_at]
        sla_out[metric] = {"instancias": len(rs), "paradas": len(stopped), "cumpridas": len(ok),
                           "cumprimento": _ratio(len(ok), len(stopped)),
                           "vencidas": len([r for r in rs if r.breached or (r.status != "stopped" and r.due_at < now)])}
    durs = [(r["resolved_at"] - r["created_at"]).total_seconds() for r in resolved if r.get("resolved_at")]
    contacts = {}
    if resolved:
        ids = [r["id"] for r in resolved]
        for tid, n in conn.execute(sa.select(m.ticket_calls.c.ticket_id, sa.func.count()).where(
                m.ticket_calls.c.ticket_id.in_(ids)).group_by(m.ticket_calls.c.ticket_id)):
            contacts[tid] = contacts.get(tid, 0) + n
        for tid, n in conn.execute(sa.select(m.ticket_conversations.c.ticket_id, sa.func.count()).where(
                m.ticket_conversations.c.ticket_id.in_(ids)).group_by(m.ticket_conversations.c.ticket_id)):
            # a conversa criada pela própria chamada não é um contato a mais
            contacts[tid] = max(contacts.get(tid, 0), n)
    fcr = [r["id"] for r in resolved if r["reopen_count"] == 0 and contacts.get(r["id"], 0) <= 1]
    out = {
        "from": db.iso(start), "to": db.iso(end), "criados": len(created), "resolvidos": len(resolved),
        "backlog_agora": backlog, "reaberturas": reopen,
        "tempo_resolucao_medio_s": round(sum(durs) / len(durs)) if durs else None,
        "tempo_resolucao_mediana_s": round(statistics.median(durs)) if durs else None,
        "sla": sla_out, "fcr": _ratio(len(fcr), len(resolved)),
        "por_canal": _count(created, "channel"), "por_prioridade": _count(created, "priority"),
        "por_equipe": _count(created, "team_name"), "por_status": _count(created, "status"),
        "por_categoria": _count(created, "category"),
    }
    if group_by in ("channel", "priority", "team_name", "category"):
        out["grupo"] = _count(created, group_by)
    if detail:
        out["ids"] = {"criados": [r["id"] for r in created], "resolvidos": [r["id"] for r in resolved], "fcr": fcr}
    return out


def _count(rows: List[Dict[str, Any]], k: str) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for r in rows:
        key = str(r.get(k) or "-")
        out[key] = out.get(key, 0) + 1
    return out
