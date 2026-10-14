"""Máquina de estados da chamada: call (lógica) -> call_legs (uma por call_id da 55PBX) -> call_events.

Cada evento é uma "fotografia" da perna. O estado da perna é recalculado do zero a partir de todos os seus
eventos, ordenados por (rank, id): o evento inicial (rank 1) nunca sobrescreve o final (rank 2), seja qual for
a ordem de chegada. Duplicados exatos são descartados pela chave única (call_events.dedup_key). Transferências
ligam pernas da mesma chamada lógica (call_transfer_id no 3º envio; call_id_origin no Report02); se a perna
nova chegou antes e virou outra chamada, as duas são mescladas.

Tudo aqui roda numa transação, sem I/O externo; os efeitos (Chatwoot, gravação, stream) vão para a outbox.
"""
from __future__ import annotations

import datetime as dt
import fnmatch
import logging
from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection

from pbx_bridge import notes
from pbx_bridge.normalize import merge, mobile_variants, queue_key

from . import db, sla, tickets
from . import models as m
from . import obs
from .config import OpsSettings
from .normalize55 import RANK, branch_digits, e164, mask_e164, phase, started_at

log = logging.getLogger("sd_ops.calls")

LEG_FIELDS = ("direction", "branch", "agent_email", "agent_name", "queue", "ura", "started_at", "answered_at",
              "ended_at", "talk_s", "wait_s", "total_s", "disconnection", "status_raw", "has_audio_url",
              "transfer_to_provider_call_id", "state")


def _ts(v: Optional[str]) -> Optional[dt.datetime]:
    if not v:
        return None
    try:
        return dt.datetime.fromisoformat(str(v).replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    except ValueError:
        return None


class CallEngine:
    def __init__(self, s: OpsSettings):
        self.s = s
        self.queue_team = {queue_key(k): v for k, v in s.bridge.queue_team_map.items()}

    # ================================================================== entrada
    def ingest(self, conn: Connection, tenant_id: str, d: Dict[str, Any], anomalies: List[str], source: str,
               inbox_id: Optional[int], now: Optional[dt.datetime] = None) -> Dict[str, Any]:
        now = now or db.utcnow()
        pcid = d["call_id"]
        if d.get("type") == "sms":
            return {"result": "ignored_sms", "provider_call_id": pcid}
        kind = phase(d, source)
        canon = {k: v for k, v in d.items() if not k.startswith("_")}
        dedup = db.sha256("v1|%s|%s|%s|%s" % (tenant_id, pcid, kind, db.jdump(canon)))
        # serializa o processamento de chamadas do tenant (transações curtas, sem I/O externo)
        conn.execute(sa.text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": "sdops-calls:" + tenant_id})
        ev = conn.execute(pg_insert(m.call_events).values(
            tenant_id=tenant_id, inbox_id=inbox_id, provider_call_id=pcid, kind=kind, rank=RANK[kind], source=source,
            dedup_key=dedup, normalized=canon, anomalies=anomalies, received_at=now,
        ).on_conflict_do_nothing(index_elements=["dedup_key"]).returning(m.call_events.c.id)).first()
        if ev is None:
            return {"result": "duplicate", "provider_call_id": pcid, "kind": kind}
        event_id = ev[0]
        obs.bind(provider_call_id=pcid)

        leg, call, created = self._leg_for(conn, tenant_id, pcid, d, now)
        conn.execute(m.call_events.update().where(m.call_events.c.id == event_id).values(
            call_id=call["id"], leg_id=leg["id"]))
        obs.bind(call_id=call["id"])
        before_state = call["state"]
        before_legs = call["legs_count"]

        leg = self._recompute_leg(conn, tenant_id, leg, now)
        if leg.get("transfer_to_provider_call_id"):
            call = self._handle_transfer(conn, tenant_id, call, leg, now)
        origin = (leg["data"] or {}).get("origin_call_id")
        if origin and not leg.get("transferred_from_leg_id"):
            call = self._link_origin(conn, tenant_id, call, leg, origin, now)
        call = self._recompute_call(conn, call["id"], now)

        self._effects(conn, call, leg, kind, created, before_state, before_legs, now)
        db.enqueue(conn, tenant_id, "chatwoot.sync_call", "sync_call:%s" % event_id,
                   {"call_id": call["id"], "leg_id": leg["id"]}, ordering_key="call:" + call["id"])
        return {"result": "ok", "kind": kind, "call_id": call["id"], "leg_id": leg["id"], "state": call["state"],
                "outcome": call["outcome"], "event_id": event_id}

    # ================================================================== pernas
    def _leg_by_pcid(self, conn, tenant_id: str, pcid: str) -> Optional[Dict[str, Any]]:
        r = conn.execute(sa.select(m.call_legs).where(m.call_legs.c.tenant_id == tenant_id,
                                                      m.call_legs.c.provider_call_id == pcid).with_for_update()).first()
        return dict(r._mapping) if r else None

    def _call(self, conn, call_id: str) -> Dict[str, Any]:
        r = conn.execute(sa.select(m.calls).where(m.calls.c.id == call_id).with_for_update()).first()
        return dict(r._mapping)

    def _new_call(self, conn, tenant_id: str, pcid: str, d: Dict[str, Any], now) -> Dict[str, Any]:
        dial = conn.execute(sa.select(m.dial_requests).where(m.dial_requests.c.tenant_id == tenant_id,
                                                             m.dial_requests.c.provider_call_id == pcid)).first()
        r = conn.execute(m.calls.insert().values(
            tenant_id=tenant_id, root_provider_call_id=pcid, direction=d.get("type"), state="active",
            number_e164=e164(d), central_id=d.get("central_id") or d.get("central"),
            dial_request_id=dial.id if dial else None,
            conversation_id=dial.conversation_id if dial else None,
            contact_id=dial.contact_id if dial else None, created_at=now, updated_at=now,
        ).returning(m.calls)).first()
        return dict(r._mapping)

    def _leg_for(self, conn, tenant_id: str, pcid: str, d: Dict[str, Any], now) -> Tuple[Dict, Dict, bool]:
        leg = self._leg_by_pcid(conn, tenant_id, pcid)
        if leg is not None:
            call = self._call(conn, leg["call_id"])
            if call["state"] == "merged" and call["merged_into"]:
                call = self._call(conn, call["merged_into"])
            return leg, call, False
        call = None
        origin_leg = None
        if d.get("origin_call_id"):
            origin_leg = self._leg_by_pcid(conn, tenant_id, d["origin_call_id"])
            if origin_leg:
                call = self._call(conn, origin_leg["call_id"])
        created = call is None
        if call is None:
            call = self._new_call(conn, tenant_id, pcid, d, now)
        seq = conn.execute(sa.select(sa.func.coalesce(sa.func.max(m.call_legs.c.seq), 0)).where(
            m.call_legs.c.call_id == call["id"])).scalar() + 1
        r = conn.execute(m.call_legs.insert().values(
            tenant_id=tenant_id, call_id=call["id"], seq=seq, provider_call_id=pcid, state="started",
            created_at=now, updated_at=now,
        ).returning(m.call_legs)).first()
        return dict(r._mapping), call, created

    def _agent_email(self, conn, tenant_id: str, branch: Optional[str], d: Dict[str, Any]) -> Optional[str]:
        if d.get("branch_email"):
            pass  # e-mail do ramal na 55PBX (pode diferir do e-mail do agente)
        if branch:
            r = conn.execute(sa.select(m.agent_phone_mappings.c.agent_email).where(
                m.agent_phone_mappings.c.tenant_id == tenant_id, m.agent_phone_mappings.c.branch == branch,
                m.agent_phone_mappings.c.active.is_(True))).first()
            if r:
                return r[0]
            if branch in self.s.bridge.branch_agent_map:
                return self.s.bridge.branch_agent_map[branch]
        return None

    def _recompute_leg(self, conn, tenant_id: str, leg: Dict[str, Any], now) -> Dict[str, Any]:
        evs = conn.execute(sa.select(m.call_events.c.normalized, m.call_events.c.kind, m.call_events.c.received_at)
                           .where(m.call_events.c.tenant_id == tenant_id,
                                  m.call_events.c.provider_call_id == leg["provider_call_id"])
                           .order_by(m.call_events.c.rank, m.call_events.c.id)).fetchall()
        merged: Dict[str, Any] = {}
        kinds = set()
        first_rx = None
        end_rx = None
        for e in evs:
            merged = merge(merged, e.normalized)
            kinds.add(e.kind)
            first_rx = e.received_at if first_rx is None or e.received_at < first_rx else first_rx
            if e.kind != "start" and (end_rx is None or e.received_at < end_rx):
                end_rx = e.received_at
        tz = self.s.bridge.tz_offset_hours
        st = started_at(merged, tz, first_rx or now)
        talk = merged.get("spoken")
        wait = merged.get("waiting")
        total = merged.get("total_duration")
        answered = _ts(merged.get("attended_at"))
        if answered is None and talk:
            answered = st + dt.timedelta(seconds=wait or 0)
        ended = kinds & {"end", "transfer", "report"}
        ended_at = None
        if ended:
            ended_at = st + dt.timedelta(seconds=total) if total is not None else end_rx
        branch = branch_digits(merged)
        vals = {
            "direction": merged.get("type"), "branch": branch,
            "agent_email": self._agent_email(conn, tenant_id, branch, merged),
            "agent_name": merged.get("agent_name"), "queue": merged.get("queue"),
            "ura": merged.get("ura") or merged.get("ivr"), "started_at": st, "answered_at": answered,
            "ended_at": ended_at, "talk_s": talk, "wait_s": wait, "total_s": total,
            "disconnection": merged.get("disconnection"), "status_raw": merged.get("status_raw"),
            "has_audio_url": bool(merged.get("audio_url")),
            "transfer_to_provider_call_id": merged.get("transfer_id"),
            "state": ("transferred" if merged.get("transfer_id") else "ended") if ended else "started",
            "data": merged, "updated_at": now,
        }
        r = conn.execute(m.call_legs.update().where(m.call_legs.c.id == leg["id"]).values(**vals)
                         .returning(m.call_legs)).first()
        return dict(r._mapping)

    # ================================================================== transferências
    def _handle_transfer(self, conn, tenant_id: str, call: Dict, leg: Dict, now) -> Dict:
        target = leg["transfer_to_provider_call_id"]
        tl = self._leg_by_pcid(conn, tenant_id, target)
        if tl is None:
            seq = conn.execute(sa.select(sa.func.coalesce(sa.func.max(m.call_legs.c.seq), 0)).where(
                m.call_legs.c.call_id == call["id"])).scalar() + 1
            conn.execute(m.call_legs.insert().values(
                tenant_id=tenant_id, call_id=call["id"], seq=seq, provider_call_id=target, state="pending",
                transferred_from_leg_id=leg["id"], created_at=now, updated_at=now))
        else:
            if tl["call_id"] != call["id"]:
                self._merge_calls(conn, tenant_id, keep_id=call["id"], drop_id=tl["call_id"], now=now)
            if not tl.get("transferred_from_leg_id"):
                conn.execute(m.call_legs.update().where(m.call_legs.c.id == tl["id"]).values(
                    transferred_from_leg_id=leg["id"]))
        n = conn.execute(sa.select(sa.func.count()).select_from(m.call_legs).where(
            m.call_legs.c.call_id == call["id"], m.call_legs.c.transfer_to_provider_call_id.isnot(None))).scalar()
        db.publish(conn, tenant_id, "call.transferred", "%s:%s" % (leg["id"], target),
                   dict(self._common(conn, call, leg), from_leg_id=leg["id"], to_provider_call_id=target,
                        from_branch=leg.get("branch"), from_queue=leg.get("queue"), transfer_seq=n),
                   occurred_at=leg.get("ended_at"), subject=self._subject(call, leg))
        return self._call(conn, call["id"])

    def _link_origin(self, conn, tenant_id: str, call: Dict, leg: Dict, origin: str, now) -> Dict:
        ol = self._leg_by_pcid(conn, tenant_id, origin)
        if ol is None:
            return call
        conn.execute(m.call_legs.update().where(m.call_legs.c.id == leg["id"]).values(transferred_from_leg_id=ol["id"]))
        if ol["call_id"] != call["id"]:
            self._merge_calls(conn, tenant_id, keep_id=ol["call_id"], drop_id=call["id"], now=now)
            call = self._call(conn, ol["call_id"])
        n = conn.execute(sa.select(sa.func.count()).select_from(m.call_legs).where(
            m.call_legs.c.call_id == call["id"], m.call_legs.c.transferred_from_leg_id.isnot(None))).scalar()
        # mesma chave natural do 3º envio (perna de origem + call_id novo): não duplica se os dois chegarem
        db.publish(conn, tenant_id, "call.transferred", "%s:%s" % (ol["id"], leg["provider_call_id"]),
                   dict(self._common(conn, call, ol), from_leg_id=ol["id"], to_provider_call_id=leg["provider_call_id"],
                        from_branch=ol.get("branch"), from_queue=ol.get("queue"), transfer_seq=n),
                   occurred_at=ol.get("ended_at"), subject=self._subject(call, ol))
        return call

    def _merge_calls(self, conn, tenant_id: str, keep_id: str, drop_id: str, now) -> None:
        """A perna transferida chegou antes da informação de transferência e virou outra chamada: junta."""
        keep_seq = conn.execute(sa.select(sa.func.coalesce(sa.func.max(m.call_legs.c.seq), 0)).where(
            m.call_legs.c.call_id == keep_id)).scalar()
        for i, lg in enumerate(conn.execute(sa.select(m.call_legs.c.id).where(m.call_legs.c.call_id == drop_id)
                                            .order_by(m.call_legs.c.seq)).fetchall()):
            conn.execute(m.call_legs.update().where(m.call_legs.c.id == lg[0]).values(call_id=keep_id,
                                                                                      seq=keep_seq + i + 1))
        for tbl in (m.call_events, m.call_recordings, m.csat_responses):
            conn.execute(tbl.update().where(tbl.c.call_id == drop_id).values(call_id=keep_id))
        keep_tickets = tickets.tickets_of_call(conn, keep_id)
        drop = self._call(conn, drop_id)
        keep_ids = {t["id"] for t in keep_tickets}
        for t in tickets.tickets_of_call(conn, drop_id):
            conn.execute(m.ticket_calls.delete().where(m.ticket_calls.c.ticket_id == t["id"],
                                                       m.ticket_calls.c.call_id == drop_id))
            if t["id"] in keep_ids:
                continue
            auto = t["created_by"] == "system" and t["status"] == "novo"
            if keep_tickets and auto:
                target = keep_tickets[0]
                for cid in tickets.linked_conversations(conn, t["id"]):
                    tickets.link_conversation(conn, target, cid)
                tickets.transition(conn, tenant_id, t["id"], "cancelado", "system",
                                   "mesclado no protocolo %s (transferência)" % target["protocol"], roles=("system",))
            else:
                tickets.link_call(conn, t, keep_id, "related")
        if not keep_tickets:
            pass
        conn.execute(m.callback_tasks.update().where(m.callback_tasks.c.call_id == drop_id,
                                                     m.callback_tasks.c.status == "pending").values(
            status="cancelled", result="mesclada em outra chamada (transferência)", updated_at=now))
        keep = self._call(conn, keep_id)
        upd = {}
        for k in ("conversation_id", "contact_id"):
            if keep.get(k) is None and drop.get(k) is not None:
                upd[k] = drop[k]
        if upd:
            conn.execute(m.calls.update().where(m.calls.c.id == keep_id).values(**upd))
        conn.execute(m.calls.update().where(m.calls.c.id == drop_id).values(state="merged", merged_into=keep_id,
                                                                            updated_at=now))
        db.audit(conn, tenant_id, "call.merged", "call", drop_id, {"into": keep_id})

    # ================================================================== agregado
    def _recompute_call(self, conn, call_id: str, now) -> Dict[str, Any]:
        call = self._call(conn, call_id)
        legs = [dict(r._mapping) for r in conn.execute(sa.select(m.call_legs).where(
            m.call_legs.c.call_id == call_id).order_by(m.call_legs.c.seq)).fetchall()]
        real = [lg for lg in legs if lg["state"] != "pending"] or legs
        root = real[0]
        data = root.get("data") or {}
        active = any(lg["state"] in ("pending", "started") for lg in legs)
        with_branch = [lg for lg in real if lg.get("branch")]
        last = with_branch[-1] if with_branch else real[-1]
        talks = [lg["talk_s"] for lg in real if lg.get("talk_s") is not None]
        totals = [lg["total_s"] for lg in real if lg.get("total_s") is not None]
        answered = [lg["answered_at"] for lg in real if lg.get("answered_at")]
        ends = [lg["ended_at"] for lg in real if lg.get("ended_at")]
        number = call.get("number_e164")
        if not number:
            for lg in real:
                number = e164(lg.get("data") or {})
                if number:
                    break
        vals = {
            "direction": root.get("direction") or call.get("direction"),
            "number_e164": number,
            "central_id": data.get("central_id") or data.get("central") or call.get("central_id"),
            "queue": next((lg["queue"] for lg in real if lg.get("queue")), None),
            "ura": root.get("ura"),
            "branch": last.get("branch"), "agent_email": last.get("agent_email"),
            "started_at": root.get("started_at"),
            "answered_at": min(answered) if answered else None,
            "ended_at": None if active else (max(ends) if ends else None),
            "talk_s": sum(talks) if talks else None,
            "wait_s": root.get("wait_s"),
            "total_s": sum(totals) if totals else None,
            "disconnection": real[-1].get("disconnection"),
            "status_raw": real[-1].get("status_raw") or root.get("status_raw"),
            "legs_count": len(legs),
            "state": "active" if active else "ended",
            "updated_at": now, "version": call["version"] + 1,
        }
        vals["outcome"] = None if active else self.classify(conn, call["tenant_id"], vals, real)
        r = conn.execute(m.calls.update().where(m.calls.c.id == call_id).values(**vals).returning(m.calls)).first()
        return dict(r._mapping)

    def classify(self, conn, tenant_id: str, c: Dict[str, Any], legs: List[Dict[str, Any]]) -> str:
        """Resultado da chamada lógica. Uma perna recusada por um operador NÃO torna a chamada perdida se
        outra perna foi atendida."""
        if any((lg.get("talk_s") or 0) > 0 or lg.get("answered_at") for lg in legs):
            return "answered"
        smap = self.s.call_status_map
        for lg in reversed(legs):
            key = ((lg.get("data") or {}).get("status_key") or "")
            if key in smap and smap[key] != "answered":
                o = smap[key]
                if o == "rejected" and len(legs) == 1 and c.get("direction") == "receptivo":
                    return "missed"   # recusada pelo único operador chamado: o cliente não foi atendido
                return o
        if c.get("direction") == "ativo":
            return "failed"
        if c.get("direction") == "interno":
            return "missed"
        st = c.get("started_at")
        if st is not None and not sla.tenant_bh(conn, tenant_id).is_open(st):
            return "after_hours"
        if c.get("queue"):
            return "abandoned_queue"
        if c.get("ura"):
            return "abandoned_ura"
        return "missed"

    # ================================================================== efeitos
    def _common(self, conn, call: Dict, leg: Optional[Dict] = None) -> Dict[str, Any]:
        tks = tickets.tickets_of_call(conn, call["id"])
        root = conn.execute(sa.select(m.call_legs.c.id).where(m.call_legs.c.call_id == call["id"]).order_by(
            m.call_legs.c.seq).limit(1)).scalar()
        return {
            "call_id": call["id"], "leg_id": (leg or {}).get("id") or root,
            "provider_call_id": (leg or {}).get("provider_call_id") or call["root_provider_call_id"],
            "root_provider_call_id": call["root_provider_call_id"], "direction": call.get("direction"),
            "number_masked": mask_e164(call.get("number_e164")), "contact_id": call.get("contact_id"),
            "conversation_id": call.get("conversation_id"),
            "ticket_id": tks[0]["id"] if tks else None, "ticket_protocol": tks[0]["protocol"] if tks else None,
            "branch": call.get("branch"), "agent_email": call.get("agent_email"), "queue": call.get("queue"),
            "started_at": db.iso(call.get("started_at")), "answered_at": db.iso(call.get("answered_at")),
            "ended_at": db.iso(call.get("ended_at")),
        }

    def _subject(self, call: Dict, leg: Optional[Dict] = None) -> Dict[str, Any]:
        return {"call_id": call["id"], "provider_call_id": (leg or {}).get("provider_call_id") or call["root_provider_call_id"],
                "conversation_id": call.get("conversation_id")}

    def _effects(self, conn, call: Dict, leg: Dict, kind: str, created: bool, before_state: str, before_legs: int,
                 now) -> None:
        tenant_id = call["tenant_id"]
        if created:
            db.publish(conn, tenant_id, "call.started", call["id"], self._common(conn, call, leg),
                       occurred_at=call.get("started_at"), subject=self._subject(call, leg))
        self._apply_policy(conn, call, now)
        ended_now = call["state"] == "ended" and (before_state != "ended" or before_legs != call["legs_count"])
        if call["state"] == "ended":
            self._recordings(conn, call, now)
            self._csat(conn, call)
        if ended_now:
            missed = call["outcome"] in self.s.callback_outcomes or call["outcome"] in (
                "missed", "abandoned_ura", "abandoned_queue", "after_hours", "dropped")
            cb_id = self._callback(conn, call, now) if missed else None
            payload = dict(self._common(conn, call, leg), outcome=call["outcome"], talk_s=call.get("talk_s"),
                           wait_s=call.get("wait_s"), total_s=call.get("total_s"),
                           disconnection=call.get("disconnection"), legs=call["legs_count"],
                           has_recording_url=self._has_audio(conn, call["id"]))
            db.publish(conn, tenant_id, "call.ended", "%s:%s" % (call["id"], call["legs_count"]), payload,
                       occurred_at=call.get("ended_at"), subject=self._subject(call, leg))
            if missed:
                db.publish(conn, tenant_id, "call.missed", call["id"],
                           dict(payload, callback_task_id=cb_id), occurred_at=call.get("ended_at"),
                           subject=self._subject(call, leg))
            self._classify_ticket(conn, call)
            if call["outcome"] == "answered":
                for t in tickets.tickets_of_call(conn, call["id"]):
                    if call.get("direction") in ("receptivo", "ativo"):
                        tickets.record_first_response(conn, tenant_id, t["id"],
                                                      call.get("answered_at") or now, "ligação atendida")
                if call.get("direction") == "ativo" and call.get("number_e164"):
                    self._complete_callbacks(conn, call, now)

    def _has_audio(self, conn, call_id: str) -> bool:
        return bool(conn.execute(sa.select(sa.func.count()).select_from(m.call_legs).where(
            m.call_legs.c.call_id == call_id, m.call_legs.c.has_audio_url.is_(True))).scalar())

    # ---------------------------------------------------------------- política de abertura de ticket
    def pick_rule(self, conn, tenant_id: str, direction: Optional[str], queue: Optional[str]) -> Dict[str, Any]:
        q = queue_key(queue or "")
        for r in conn.execute(sa.select(m.ticket_open_rules).where(
                m.ticket_open_rules.c.tenant_id == tenant_id, m.ticket_open_rules.c.active.is_(True),
                m.ticket_open_rules.c.channel == "phone").order_by(m.ticket_open_rules.c.sort, m.ticket_open_rules.c.id)):
            if r.direction and r.direction != direction:
                continue
            if r.queue_pattern and not fnmatch.fnmatch(q, r.queue_pattern.lower()):
                continue
            return dict(r._mapping)
        return {"id": None, "name": "padrão", "mode": "all", "reuse": "reuse_open", "reuse_window_hours": 24,
                "default_priority": "normal"}

    def _apply_policy(self, conn, call: Dict, now) -> None:
        if call["state"] == "merged" or tickets.tickets_of_call(conn, call["id"]):
            return
        tenant_id = call["tenant_id"]
        if call.get("dial_request_id"):
            dial = conn.execute(sa.select(m.dial_requests).where(m.dial_requests.c.id == call["dial_request_id"])).first()
            if dial and dial.ticket_id:
                t = tickets.get(conn, tenant_id, dial.ticket_id, lock=True)
                if t:
                    tickets.link_call(conn, t, call["id"], "dial")
                    self._set_policy(conn, call, "dial:%s" % t["protocol"])
                    return
        if not call.get("direction"):
            return
        rule = self.pick_rule(conn, tenant_id, call["direction"], call.get("queue"))
        mode = rule["mode"]
        ended = call["state"] == "ended"
        missed = call.get("outcome") in ("missed", "abandoned_ura", "abandoned_queue", "after_hours", "dropped", "rejected")
        if mode == "none":
            return self._set_policy(conn, call, "none:%s" % rule["name"])
        if mode == "answered" and not (ended and call.get("outcome") == "answered"):
            if ended:
                self._set_policy(conn, call, "none:nao_atendida")
            return
        if mode == "missed" and not (ended and missed):
            if ended:
                self._set_policy(conn, call, "none:nao_perdida")
            return
        if rule["reuse"] == "ask":
            conn.execute(m.calls.update().where(m.calls.c.id == call["id"]).values(
                needs_classification=True, ticket_policy="ask:%s" % rule["name"]))
            return
        if rule["reuse"] == "reuse_open":
            t = tickets.find_reusable(conn, tenant_id, call.get("number_e164"), call.get("contact_id"),
                                      rule["reuse_window_hours"], now)
            if t:
                tickets.link_call(conn, t, call["id"], "related")
                if call.get("conversation_id"):
                    tickets.link_conversation(conn, t, call["conversation_id"])
                return self._set_policy(conn, call, "reused:%s" % t["protocol"])
        root = conn.execute(sa.select(m.call_legs.c.data).where(m.call_legs.c.call_id == call["id"]).order_by(
            m.call_legs.c.seq).limit(1)).scalar() or {}
        origin = {"receptivo": "call_inbound", "ativo": "call_outbound", "interno": "call_internal"}.get(
            call["direction"], "call")
        fields = {"subject": notes.subject(root) if root.get("client_name") else
                  "Ligação %s %s" % (call["direction"], call.get("number_e164") or ""),
                  "channel": "phone", "origin": origin, "priority": rule["default_priority"],
                  "contact_e164": call.get("number_e164"), "contact_id": call.get("contact_id"),
                  "contact_name": root.get("client_name"),
                  "team_name": self.queue_team.get(queue_key(call.get("queue") or "")) if call["direction"] == "receptivo" else None}
        if ended and missed:
            fields.update(origin="call_missed", category="ligacao_perdida", subcategory=call["outcome"])
        t = tickets.create(conn, tenant_id, fields, "system", call_id=call["id"],
                           conversation_id=call.get("conversation_id"), now=now)
        self._set_policy(conn, call, "created:%s" % t["protocol"])

    def _set_policy(self, conn, call: Dict, txt: str) -> None:
        conn.execute(m.calls.update().where(m.calls.c.id == call["id"]).values(ticket_policy=txt))

    def _classify_ticket(self, conn, call: Dict) -> None:
        """Ticket aberto automaticamente no início: no fim, se a chamada foi perdida, classifica."""
        if call.get("outcome") not in ("missed", "abandoned_ura", "abandoned_queue", "after_hours", "dropped"):
            return
        for t in tickets.tickets_of_call(conn, call["id"]):
            if t["created_by"] == "system" and t["status"] in tickets.OPEN_STATES and not t.get("category"):
                tickets.update(conn, call["tenant_id"], t["id"], {"category": "ligacao_perdida",
                                                                   "subcategory": call["outcome"]}, "system")

    # ---------------------------------------------------------------- retorno (callback)
    def _callback(self, conn, call: Dict, now) -> Optional[str]:
        if call.get("direction") != "receptivo" or not call.get("number_e164"):
            return None
        if call["outcome"] not in self.s.callback_outcomes:
            return None
        if call["outcome"] in ("abandoned_queue", "abandoned_ura") and (call.get("wait_s") or 0) < self.s.short_abandon_s \
                and (call.get("total_s") or 0) < self.s.short_abandon_s:
            return None  # abandono curto (engano/desistência imediata): sem retorno
        bh = sla.tenant_bh(conn, call["tenant_id"])
        due = bh.add(now, self.s.callback_due_min)
        tks = tickets.tickets_of_call(conn, call["id"])
        r = conn.execute(pg_insert(m.callback_tasks).values(
            tenant_id=call["tenant_id"], call_id=call["id"], ticket_id=tks[0]["id"] if tks else None,
            number_e164=call["number_e164"], reason=call["outcome"], status="pending", due_at=due,
        ).on_conflict_do_nothing(index_elements=["call_id"]).returning(m.callback_tasks.c.id)).first()
        if r is None:
            return conn.execute(sa.select(m.callback_tasks.c.id).where(m.callback_tasks.c.call_id == call["id"])).scalar()
        db.publish(conn, call["tenant_id"], "callback.created", r[0],
                   {"callback_task_id": r[0], "call_id": call["id"], "ticket_id": tks[0]["id"] if tks else None,
                    "reason": call["outcome"], "due_at": db.iso(due)}, subject={"call_id": call["id"]})
        db.audit(conn, call["tenant_id"], "callback.created", "callback_task", r[0], {"reason": call["outcome"]})
        return r[0]

    def _complete_callbacks(self, conn, call: Dict, now) -> None:
        """Ligação ativa atendida para um número com retorno pendente: retorno feito."""
        res = conn.execute(m.callback_tasks.update().where(
            m.callback_tasks.c.tenant_id == call["tenant_id"], m.callback_tasks.c.status == "pending",
            m.callback_tasks.c.number_e164.in_(mobile_variants(call["number_e164"]))).values(
            status="done", completed_at=now, completion_call_id=call["id"], result="retorno realizado (ligação ativa)",
            updated_at=now).returning(m.callback_tasks.c.id)).fetchall()
        for r in res:
            db.audit(conn, call["tenant_id"], "callback.completed", "callback_task", r[0], {"call_id": call["id"]})

    # ---------------------------------------------------------------- gravação e CSAT
    def _recordings(self, conn, call: Dict, now) -> None:
        legs = conn.execute(sa.select(m.call_legs).where(m.call_legs.c.call_id == call["id"],
                                                         m.call_legs.c.has_audio_url.is_(True),
                                                         m.call_legs.c.state.in_(("ended", "transferred")))).fetchall()
        for lg in legs:
            url = (lg.data or {}).get("audio_url")
            from urllib.parse import urlparse
            host = (urlparse(url).hostname or "") if url else ""
            r = conn.execute(pg_insert(m.call_recordings).values(
                tenant_id=call["tenant_id"], call_id=call["id"], leg_id=lg.id, source_url=url, source_host=host,
                status="pending", expected_talk_s=lg.talk_s,
                next_attempt_at=now + dt.timedelta(seconds=self.s.recording_initial_delay_s),
            ).on_conflict_do_nothing(index_elements=["leg_id"]).returning(m.call_recordings.c.id)).first()
            if r is not None:
                db.enqueue(conn, call["tenant_id"], "recording.fetch", "recfetch:%s" % r[0], {"recording_id": r[0]},
                           ordering_key="rec:" + r[0], delay_s=self.s.recording_initial_delay_s)
            else:
                # a URL pode chegar/mudar num evento posterior (ex.: Report02)
                conn.execute(m.call_recordings.update().where(
                    m.call_recordings.c.leg_id == lg.id, m.call_recordings.c.status == "pending",
                    m.call_recordings.c.source_url.is_distinct_from(url)).values(source_url=url, source_host=host))

    def _csat(self, conn, call: Dict) -> None:
        for lg in conn.execute(sa.select(m.call_legs).where(m.call_legs.c.call_id == call["id"])).fetchall():
            d = lg.data or {}
            if d.get("rating") is None and d.get("humor") is None:
                continue
            tks = tickets.tickets_of_call(conn, call["id"])
            conn.execute(pg_insert(m.csat_responses).values(
                tenant_id=call["tenant_id"], call_id=call["id"], leg_id=lg.id, ticket_id=tks[0]["id"] if tks else None,
                score=d.get("rating") if d.get("rating") is not None else d.get("humor"),
                weight=d.get("rating_weight"), rating_type=d.get("rating_type"), form_id=d.get("rating_form_id"),
                form_name=d.get("rating_name"),
                data={k: d[k] for k in ("rating_yes", "rating_no") if k in d}).on_conflict_do_nothing(
                index_elements=["leg_id"]))

    # ================================================================== manutenção
    def finalize_stale(self, conn, older_than_h: int = 6, now=None) -> int:
        """Chamadas presas em 'active' (ex.: perna de transferência que nunca chegou): encerra pelo que há."""
        now = now or db.utcnow()
        rows = conn.execute(sa.select(m.calls.c.id, m.calls.c.tenant_id).where(
            m.calls.c.state == "active", m.calls.c.updated_at < now - dt.timedelta(hours=older_than_h))
            .limit(100).with_for_update(skip_locked=True)).fetchall()
        for cid, tenant_id in rows:
            conn.execute(sa.text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": "sdops-calls:" + tenant_id})
            conn.execute(m.call_legs.update().where(m.call_legs.c.call_id == cid, m.call_legs.c.state == "pending")
                         .values(state="ended", updated_at=now, data={"anomaly": "leg_never_reported"}))
            conn.execute(m.call_legs.update().where(m.call_legs.c.call_id == cid, m.call_legs.c.state == "started")
                         .values(state="ended", updated_at=now))
            call = self._call(conn, cid)
            before = call["state"]
            call = self._recompute_call(conn, cid, now)
            self._effects(conn, call, None or {"id": None, "provider_call_id": call["root_provider_call_id"]},
                          "end", False, before, call["legs_count"], now)
            db.audit(conn, tenant_id, "call.finalized_stale", "call", cid, {})
        return len(rows)
