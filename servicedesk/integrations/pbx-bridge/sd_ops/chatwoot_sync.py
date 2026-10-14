"""Sincronização com o Chatwoot SÓ pela API pública.

- chamada -> conversa + notas no formato do Zendesk: reaproveita o Processor da pbx-bridge (testado), com o
  estado em Postgres (ops.chatwoot_call_projection) e o áudio vindo do storage do sd-ops;
- pernas de transferência -> nota "Transferência 55PBX" na conversa da chamada;
- ticket -> atributos sd_* + zd_status/zd_status_sistema + status nativo do ticket (open/waiting_on_customer/on_hold/resolved);
- eventos do Chatwoot -> primeira resposta (SLA), status da conversa -> estado do ticket (sem eco).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from pbx_bridge.audio import AudioError, mp3_name, to_mp3
from pbx_bridge.chatwoot import Chatwoot, ChatwootError
from pbx_bridge.config import Settings as BridgeSettings
from pbx_bridge.normalize import mask, mobile_variants
from pbx_bridge.processor import Processor, source_id

from . import db, tickets
from . import models as m
from .config import OpsSettings

log = logging.getLogger("sd_ops.chatwoot")

BRIDGE_OVERRIDABLE = {f.name for f in dataclasses.fields(BridgeSettings)} - {"chatwoot_api_token", "pbx_api_key",
                                                                               "webhook_secret", "db_path"}


class OpsChatwoot(Chatwoot):
    """Cliente da pbx-bridge + leitura de contato (contexto do CTI)."""

    def get_contact(self, contact_id: int) -> Dict[str, Any]:
        r = self.req("GET", "/contacts/%d" % contact_id) or {}
        return r.get("payload") if isinstance(r, dict) and isinstance(r.get("payload"), dict) else r


class PgProjectionStore:
    """Mesma interface do pbx_bridge.store.Store usada pelo Processor (get_call/save_call), em Postgres."""

    def __init__(self, engine, tenant_id: str):
        self.engine, self.tenant_id = engine, tenant_id

    def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        with self.engine.begin() as conn:
            r = conn.execute(sa.select(m.chatwoot_call_projection).where(
                m.chatwoot_call_projection.c.tenant_id == self.tenant_id,
                m.chatwoot_call_projection.c.call_id == call_id)).first()
        if not r:
            return None
        d = dict(r._mapping)
        d["parts"] = set(d["parts"] or [])
        d["created_at"] = d["created_at"].timestamp()
        return d

    def save_call(self, call: Dict[str, Any]) -> None:
        vals = dict(tenant_id=self.tenant_id, call_id=call["call_id"], data=json.loads(json.dumps(call["data"], default=str)),
                    conversation_id=call.get("conversation_id"), contact_id=call.get("contact_id"),
                    parts=sorted(call.get("parts", set())), audio_status=call.get("audio_status", "none"),
                    audio_attempts=call.get("audio_attempts", 0), audio_next_at=call.get("audio_next_at", 0),
                    updated_at=db.utcnow())
        upd = {k: v for k, v in vals.items() if k not in ("tenant_id", "call_id")}
        with self.engine.begin() as conn:
            conn.execute(pg_insert(m.chatwoot_call_projection).values(**vals).on_conflict_do_update(
                index_elements=["tenant_id", "call_id"], set_=upd))

    def seed(self, call_id: str, conversation_id: Optional[int], contact_id: Optional[int]) -> None:
        """Chamada originada de click-to-call numa conversa existente: as notas vão para ela."""
        if not conversation_id or self.get_call(call_id):
            return
        self.save_call({"call_id": call_id, "data": {}, "conversation_id": conversation_id, "contact_id": contact_id,
                        "parts": set(), "audio_status": "none"})


class OpsProcessor(Processor):
    """Processor da pbx-bridge com identificação sem mesclas e registro do gatilho de encerramento."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.ambiguous = False
        self.closed_by_trigger = False
        self.last_contact: Optional[Dict[str, Any]] = None

    def _resolve_contact(self, d: Dict[str, Any]) -> Dict[str, Any]:
        e164 = d.get("e164")
        if e164 and hasattr(self.cw, "search_contacts"):
            hits: Dict[int, Dict[str, Any]] = {}
            for p in mobile_variants(e164):
                for c in self.cw.search_contacts(p):
                    if (c.get("phone_number") or "") == p:
                        hits[c["id"]] = c
            if len(hits) > 1:
                # nunca escolhe "por semelhança": usa o mais antigo e marca o ticket para identificação humana
                self.ambiguous = True
                log.warning("telefone com %d contatos no Chatwoot: identificação ambígua", len(hits))
                self.last_contact = hits[min(hits)]
                return self.last_contact
            if len(hits) == 1:
                self.last_contact = next(iter(hits.values()))
                return self.last_contact
        self.last_contact = super()._resolve_contact(d)
        return self.last_contact

    def _trigger_close(self, call: Dict[str, Any]) -> None:
        before = self.cw.calls[:] if hasattr(self.cw, "calls") and isinstance(getattr(self.cw, "calls"), list) else None
        had = "trigger_close" in call["parts"]
        super()._trigger_close(call)
        if had or not call.get("conversation_id"):
            return
        if before is not None:
            self.closed_by_trigger = any(c[0] == "toggle_status" for c in self.cw.calls[len(before):])
        else:
            try:
                self.closed_by_trigger = (self.cw.get_conversation(call["conversation_id"]) or {}).get("status") == "resolved"
            except ChatwootError:
                self.closed_by_trigger = False


class TenantContext:
    def __init__(self, row: Dict[str, Any], bridge: BridgeSettings, cw):
        self.row, self.bridge, self.cw = row, bridge, cw
        self.id = row["id"]


class ChatwootSync:
    def __init__(self, s: OpsSettings, engine, storage, cw_factory: Optional[Callable] = None, settings=None):
        self.s, self.engine, self.storage = s, engine, storage
        self.cw_factory = cw_factory or self._default_cw
        self._ctx: Dict[str, TenantContext] = {}
        self._cws: Dict[tuple, Any] = {}
        self.settings = settings     # configuração por tenant (tela > ambiente)
        if settings is not None:
            settings.listeners.append(self.invalidate)

    def invalidate(self, tenant_id: Optional[str] = None) -> None:
        if tenant_id is None:
            self._ctx.clear()
        else:
            self._ctx.pop(tenant_id, None)

    # ------------------------------------------------------------------ tenant
    def _default_cw(self, b: BridgeSettings):
        return OpsChatwoot(b.chatwoot_url, b.chatwoot_api_token, b.chatwoot_account_id, b.http_timeout)

    def tenant(self, tenant_id: str) -> TenantContext:
        eff = self.settings.effective(tenant_id) if self.settings is not None else self.s
        c = self._ctx.get(tenant_id)
        ttl = min(300, max(1, self.s.settings_ttl_s)) if self.settings is not None else 300
        if c and time.time() - getattr(c, "_at", 0) < ttl and getattr(c, "_ver", 0) == eff.settings_version:
            return c
        with self.engine.begin() as conn:
            r = conn.execute(sa.select(m.tenants).where(m.tenants.c.id == tenant_id)).first()
            if r is None:
                raise LookupError("tenant %s inexistente" % tenant_id)
            row = dict(r._mapping)
            ref = conn.execute(sa.select(m.integration_credentials_refs.c.env_var).where(
                m.integration_credentials_refs.c.tenant_id == tenant_id,
                m.integration_credentials_refs.c.name == "chatwoot_api_token")).scalar()
        # precedência: tela (ops.tenant_settings) > tenants.settings (legado) > ambiente
        panel_keys = set()
        if self.settings is not None:
            try:
                r_ = self.settings.row(tenant_id) or {}
            except sa.exc.SQLAlchemyError:
                r_ = {}
            from .settings_store import BY_KEY
            panel_keys = {BY_KEY[k].target.split(".", 1)[1] for k in list(r_.get("values") or {}) + list(r_.get("secrets") or {})
                          if k in BY_KEY and BY_KEY[k].target.startswith("bridge.")}
        over = {k: v for k, v in (row.get("settings") or {}).items() if k in BRIDGE_OVERRIDABLE and k not in panel_keys}
        with self.engine.begin() as conn:
            maps = {r.branch: r.agent_email for r in conn.execute(sa.select(m.agent_phone_mappings).where(
                m.agent_phone_mappings.c.tenant_id == tenant_id, m.agent_phone_mappings.c.active.is_(True)))}
        if maps:  # ops.agent_phone_mappings (admin / tela) vence o BRANCH_AGENT_MAP do ambiente
            over["branch_agent_map"] = dict(over.get("branch_agent_map") or eff.bridge.branch_agent_map, **maps)
        token = self.settings.chatwoot_token(tenant_id, ref) if self.settings is not None else \
            ((self.s.cred(ref) if ref else "") or self.s.bridge.chatwoot_api_token)
        b = dataclasses.replace(eff.bridge, chatwoot_account_id=row["chatwoot_account_id"],
                                pbx_inbox_id=row.get("pbx_inbox_id") or self.s.bridge.pbx_inbox_id,
                                integration_user_id=row.get("integration_user_id") or self.s.bridge.integration_user_id,
                                chatwoot_api_token=token, **over)
        # o cliente do Chatwoot só é recriado se URL/token/conta mudarem (os testes injetam uma fábrica com estado)
        ck = (b.chatwoot_url, b.chatwoot_api_token, b.chatwoot_account_id, b.http_timeout)
        old = self._ctx.get(tenant_id)
        cw = old.cw if old is not None and getattr(old, "_ck", None) == ck else self.cw_factory(b)
        c = TenantContext(row, b, cw)
        c._at = time.time()  # type: ignore[attr-defined]
        c._ver = eff.settings_version  # type: ignore[attr-defined]
        c._ck = ck  # type: ignore[attr-defined]
        self._ctx[tenant_id] = c
        return c

    def audio_fetcher(self, tenant_id: str) -> Callable:
        def fetch(url, allowed, max_mb, ffmpeg, bitrate, headers):
            with self.engine.begin() as conn:
                r = conn.execute(sa.select(m.call_recordings).where(
                    m.call_recordings.c.tenant_id == tenant_id, m.call_recordings.c.source_url == url)
                    .order_by(m.call_recordings.c.created_at.desc()).limit(1)).first()
            if r is None or r.status == "pending":
                raise AudioError("gravação ainda não armazenada pelo sd-ops")
            if r.status != "stored":
                raise AudioError("gravação indisponível (%s)" % r.status, permanent=True)
            raw = self.storage.get(r.storage_key)
            return to_mp3(raw, ffmpeg, bitrate), len(raw)
        return fetch

    def processor(self, ctx: TenantContext) -> OpsProcessor:
        return OpsProcessor(ctx.bridge, PgProjectionStore(self.engine, ctx.id), ctx.cw,
                            audio_fetcher=self.audio_fetcher(ctx.id))

    # ------------------------------------------------------------------ chamada
    def sync_call(self, payload: Dict[str, Any]) -> str:
        with self.engine.begin() as conn:
            call = conn.execute(sa.select(m.calls).where(m.calls.c.id == payload["call_id"])).first()
            if call is None:
                return "skip"
            if call.state == "merged" and call.merged_into:
                call = conn.execute(sa.select(m.calls).where(m.calls.c.id == call.merged_into)).first()
            call = dict(call._mapping)
            legs = [dict(r._mapping) for r in conn.execute(sa.select(m.call_legs).where(
                m.call_legs.c.call_id == call["id"]).order_by(m.call_legs.c.seq)).fetchall()]
        real = [lg for lg in legs if lg["state"] != "pending"]
        if not real:
            return "skip"
        root = real[0]
        ctx = self.tenant(call["tenant_id"])
        if not ctx.bridge.pbx_inbox_id or not ctx.bridge.chatwoot_api_token:
            raise RuntimeError("tenant %s sem PBX_INBOX_ID/token do Chatwoot" % ctx.id)
        proc = self.processor(ctx)
        store: PgProjectionStore = proc.store  # type: ignore[assignment]
        root_pcid = root["provider_call_id"]
        store.seed(root_pcid, call.get("conversation_id"), call.get("contact_id"))
        if payload.get("recording_id") and payload.get("leg_id") == root["id"]:
            pj = store.get_call(root_pcid)
            if pj and pj["audio_status"] in ("pending", "failed", "none", "absent") and "gravacao" not in pj["parts"]:
                pj["audio_status"], pj["audio_next_at"] = "pending", 0
                store.save_call(pj)
        data = dict(root["data"] or {})
        data["call_id"] = root_pcid
        proj = proc.handle(data)
        conv = proj["conversation_id"]
        for lg in real[1:]:
            self._leg_note(ctx, call, root_pcid, conv, lg)
        with self.engine.begin() as conn:
            upd = {}
            if call.get("conversation_id") != conv:
                upd["conversation_id"] = conv
            if proj.get("contact_id") and call.get("contact_id") != proj.get("contact_id"):
                upd["contact_id"] = proj["contact_id"]
            if upd:
                conn.execute(m.calls.update().where(m.calls.c.id == call["id"]).values(**upd))
            contact = proc.last_contact or {}
            for t in tickets.tickets_of_call(conn, call["id"]):
                tickets.link_conversation(conn, t, conv)
                ch: Dict[str, Any] = {}
                if not t.get("contact_id") and proj.get("contact_id"):
                    ch["contact_id"] = proj["contact_id"]
                if contact.get("email") and not t.get("contact_email"):
                    ch["contact_email"] = contact["email"]
                if contact.get("name") and not t.get("contact_name") and contact.get("name") != call.get("number_e164"):
                    ch["contact_name"] = contact["name"]
                if proc.ambiguous and not t.get("needs_identification"):
                    ch["needs_identification"] = True
                if ch:
                    t = tickets.update(conn, call["tenant_id"], t["id"], ch, "system")
                if proc.closed_by_trigger and t["status"] in tickets.OPEN_STATES:
                    tickets.transition(conn, call["tenant_id"], t["id"], "resolvido", "system",
                                       "gatilho: encerra ativos de Novos Negócios", roles=("system",))
            db.sync_log(conn, call["tenant_id"], "chatwoot", "sync_call", "ok", "call", call["id"])
        return "ok"

    def _leg_note(self, ctx: TenantContext, call: Dict, root_pcid: str, conv: int, lg: Dict) -> None:
        cw = ctx.cw
        existing = {mm.get("source_id"): mm for mm in cw.messages(conv) if mm.get("source_id")}
        sid = source_id(root_pcid, "perna:%s" % lg["provider_call_id"])
        d = lg.get("data") or {}
        if sid not in existing and lg["state"] in ("ended", "transferred"):
            lines = ["**Transferência 55PBX** (perna %d)" % lg["seq"], "",
                     "Call ID da perna: %s" % lg["provider_call_id"],
                     "Ramal: %s" % (lg.get("branch") or "-"), "Agente: %s" % (lg.get("agent_name") or "-"),
                     "Fila: %s" % (lg.get("queue") or "-"),
                     "Tempo falado (s): %s" % (lg.get("talk_s") if lg.get("talk_s") is not None else "-"),
                     "Tempo total (s): %s" % (lg.get("total_s") if lg.get("total_s") is not None else "-")]
            if lg.get("transfer_to_provider_call_id"):
                lines.append("Transferida para: %s" % lg["transfer_to_provider_call_id"])
            if d.get("audio_url"):
                lines.append("URL do Áudio: %s" % d["audio_url"])
            cw.create_message(conv, "\n".join(lines), True, sid)
        if not self.s.chatwoot_attach_recording:
            return
        sid_rec = source_id(root_pcid, "gravacao:%s" % lg["provider_call_id"])
        if sid_rec in existing:
            return
        with self.engine.begin() as conn:
            rec = conn.execute(sa.select(m.call_recordings).where(m.call_recordings.c.leg_id == lg["id"])).first()
        if rec is None or rec.status != "stored":
            return
        raw = self.storage.get(rec.storage_key)
        mp3 = to_mp3(raw, ctx.bridge.ffmpeg_bin, ctx.bridge.audio_bitrate)
        cw.create_message(conv, "**Gravação da ligação 55PBX** (perna %d, Call ID %s)" % (lg["seq"], lg["provider_call_id"]),
                          True, sid_rec, attachment=(mp3_name(lg["provider_call_id"]), mp3, "audio/mpeg"))

    # ------------------------------------------------------------------ ticket
    def sync_ticket(self, payload: Dict[str, Any]) -> str:
        with self.engine.begin() as conn:
            t = conn.execute(sa.select(m.support_tickets).where(m.support_tickets.c.id == payload["ticket_id"])).first()
            if t is None:
                return "skip"
            t = dict(t._mapping)
            convs = [dict(r._mapping) for r in conn.execute(sa.select(m.ticket_conversations).where(
                m.ticket_conversations.c.ticket_id == t["id"])).fetchall()]
        if not convs:
            return "no_conversation"
        ctx = self.tenant(t["tenant_id"])
        status, zd, zds = tickets.CHATWOOT_MAP[t["status"]]
        attrs = {"sd_ticket_id": t["id"], "sd_protocolo": t["protocol"], "sd_protocolo_numerico": t["protocol_numeric"],
                 "sd_ticket_status": t["status"], "zd_status": zd, "zd_status_sistema": zds}
        for c in convs:
            conv_id = c["conversation_id"]
            ctx.cw.set_custom_attributes(conv_id, attrs)
            cur = (ctx.cw.get_conversation(conv_id) or {}).get("status")
            # anti-eco: grava o status esperado ANTES de mudar; o webhook que voltar com ele é ignorado
            with self.engine.begin() as conn:
                conn.execute(m.ticket_conversations.update().where(
                    m.ticket_conversations.c.ticket_id == t["id"],
                    m.ticket_conversations.c.conversation_id == conv_id).values(
                    last_synced_status=status, last_synced_at=db.utcnow()))
            if cur != status:
                ctx.cw.toggle_status(conv_id, status)
        with self.engine.begin() as conn:
            db.sync_log(conn, t["tenant_id"], "chatwoot", "sync_ticket", "ok", "ticket", t["id"])
        return "ok"

    def post_note(self, payload: Dict[str, Any]) -> str:
        with self.engine.begin() as conn:
            a = conn.execute(sa.select(m.ticket_activities).where(m.ticket_activities.c.id == payload["activity_id"])).first()
            if a is None:
                return "skip"
            a = dict(a._mapping)
            t = dict(conn.execute(sa.select(m.support_tickets).where(m.support_tickets.c.id == a["ticket_id"])).first()._mapping)
            conv = conn.execute(sa.select(m.ticket_conversations.c.conversation_id).where(
                m.ticket_conversations.c.ticket_id == t["id"]).order_by(
                m.ticket_conversations.c.is_primary.desc(), m.ticket_conversations.c.created_at).limit(1)).scalar()
        if conv is None:
            return "no_conversation"
        ctx = self.tenant(t["tenant_id"])
        sid = "sdops:%s:atividade:%s" % (t["id"], a["id"])
        if any(mm.get("source_id") == sid for mm in ctx.cw.messages(conv)):
            return "dup"
        title = {"registro": "Registro de atendimento", "disposicao": "Disposição da ligação",
                 "nota_interna": "Nota interna"}.get(a["kind"], a["kind"])
        lines = ["**%s** — protocolo %s" % (title, t["protocol"]), ""]
        if a.get("body"):
            lines.append(a["body"])
        for k, v in (a.get("data") or {}).items():
            if v not in (None, "", [], {}):
                lines.append("%s: %s" % (k.replace("_", " ").capitalize(), v))
        if a.get("author_name"):
            lines.append("")
            lines.append("Por: %s" % a["author_name"])
        msg = ctx.cw.create_message(conv, "\n".join(lines), True, sid,
                                    content_attributes={"sd_origin": "sd-ops"})
        with self.engine.begin() as conn:
            conn.execute(m.ticket_activities.update().where(m.ticket_activities.c.id == a["id"]).values(
                chatwoot_message_id=(msg or {}).get("id")))
        return "ok"

    # ------------------------------------------------------------------ eventos do Chatwoot
    def handle_event(self, tenant_id: str, p: Dict[str, Any]) -> str:
        ev = p.get("event")
        if ev == "message_created":
            return self._on_message(tenant_id, p)
        if ev == "conversation_status_changed":
            return self._on_status(tenant_id, p)
        return "ignored:%s" % ev

    def _tickets_of_conv(self, conn, tenant_id: str, conv_id: int) -> List[Dict[str, Any]]:
        rows = conn.execute(sa.select(m.support_tickets).join(
            m.ticket_conversations, m.ticket_conversations.c.ticket_id == m.support_tickets.c.id).where(
            m.ticket_conversations.c.tenant_id == tenant_id,
            m.ticket_conversations.c.conversation_id == conv_id)).fetchall()
        return [dict(r._mapping) for r in rows]

    def _on_message(self, tenant_id: str, p: Dict[str, Any]) -> str:
        ctx = self.tenant(tenant_id)
        res = []
        try:  # gatilho legado de atribuição (nota/resposta de agente em conversa 55PBX sem responsável)
            res.append(self.processor(ctx).handle_chatwoot_event(p))
        except ChatwootError as e:
            raise RuntimeError("gatilho de atribuição: %s" % e)
        conv = (p.get("conversation") or {}).get("id")
        if not conv:
            return ",".join(res)
        sender = p.get("sender") or {}
        mtype = p.get("message_type")
        private = bool(p.get("private"))
        attrs = p.get("content_attributes") or {}
        at = p.get("created_at")
        when = dt.datetime.fromisoformat(at.replace("Z", "+00:00")) if isinstance(at, str) else db.utcnow()
        with self.engine.begin() as conn:
            for t in self._tickets_of_conv(conn, tenant_id, int(conv)):
                if mtype in ("outgoing", 1) and not private and (sender.get("type") or "").lower() == "user" \
                        and int(sender.get("id") or 0) != ctx.bridge.integration_user_id and not attrs.get("sd_origin"):
                    if tickets.record_first_response(conn, tenant_id, t["id"], when, "resposta pública no Chatwoot"):
                        res.append("first_response")
                if mtype in ("incoming", 0) and t["status"] == "aguardando_cliente":
                    tickets.transition(conn, tenant_id, t["id"], "em_atendimento", "system", "resposta do cliente",
                                       roles=("system",))
                    res.append("cliente_respondeu")
        return ",".join(res) or "ok"

    def _on_status(self, tenant_id: str, p: Dict[str, Any]) -> str:
        conv = p.get("id") or (p.get("conversation") or {}).get("id")
        status = p.get("status") or (p.get("conversation") or {}).get("status")
        if not conv or not status:
            return "ignored"
        out = []
        with self.engine.begin() as conn:
            for t in self._tickets_of_conv(conn, tenant_id, int(conv)):
                last = conn.execute(sa.select(m.ticket_conversations.c.last_synced_status).where(
                    m.ticket_conversations.c.ticket_id == t["id"],
                    m.ticket_conversations.c.conversation_id == int(conv))).scalar()
                if last == status:
                    out.append("eco")
                    continue
                want = None
                if status == "resolved" and t["status"] in tickets.OPEN_STATES:
                    want = "resolvido"
                elif status == "open" and t["status"] == "resolvido":
                    want = "em_atendimento"
                elif status == "open" and t["status"] in tickets.WAITING:
                    want = "em_atendimento"
                elif status == "waiting_on_customer" and t["status"] in ("novo", "triagem", "em_atendimento"):
                    want = "aguardando_cliente"
                elif status == "on_hold" and t["status"] in ("novo", "triagem", "em_atendimento"):
                    want = "aguardando_terceiro"
                if want:
                    tickets.transition(conn, tenant_id, t["id"], want, "chatwoot", "status da conversa: %s" % status,
                                       roles=("system",))
                    out.append(want)
                conn.execute(m.ticket_conversations.update().where(
                    m.ticket_conversations.c.ticket_id == t["id"],
                    m.ticket_conversations.c.conversation_id == int(conv)).values(last_synced_status=status))
        return ",".join(out) or "ok"
