"""Processamento idempotente de uma ligação (por call_id) no ServiceDesk."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Callable, Dict, Optional

from . import notes
from .audio import AudioError, fetch_mp3, mp3_name
from .chatwoot import Chatwoot, ChatwootError
from .config import Settings
from .normalize import digits, has_end_data, mask, merge, mobile_variants, queue_key, slug, to_e164
from .store import Store

log = logging.getLogger("pbx_bridge.processor")

PART_ORDER = ["registro", "atualizacao", "acao_desconexao", "acao_humor", "gravacao"]


def source_id(call_id: str, part: str) -> str:
    return "55pbx:%s:%s" % (call_id, part)


class Processor:
    def __init__(self, s: Settings, store: Store, cw: Chatwoot, audio_fetcher: Callable = fetch_mp3,
                 now: Callable[[], float] = time.time):
        self.s = s
        self.store = store
        self.cw = cw
        self.audio_fetcher = audio_fetcher
        self.now = now
        self.queue_map = {queue_key(k): v for k, v in s.queue_team_map.items()}
        self.area_map = {slug(k): v for k, v in s.team_area_map.items()}

    # ================================================================ entrada
    def handle(self, new: Dict[str, Any]) -> Dict[str, Any]:
        call_id = new.get("call_id")
        if not call_id:
            raise ValueError("registro sem call_id")
        call = self.store.get_call(call_id) or {
            "call_id": call_id, "data": {}, "parts": set(), "audio_status": "none", "audio_attempts": 0,
            "audio_next_at": 0, "created_at": self.now()}
        call["data"] = merge(call["data"], new)
        self._enrich(call["data"])
        if call["audio_status"] in ("none", "absent") and call["data"].get("audio_url"):
            call["audio_status"] = "pending" if self.s.download_recordings else "disabled"
        self._sync(call)
        return call

    def retry_audio(self, call_id: str) -> None:
        call = self.store.get_call(call_id)
        if call and call["audio_status"] == "pending":
            self._sync(call)

    # ================================================================ núcleo
    def _enrich(self, d: Dict[str, Any]) -> None:
        if d.get("type") == "interno":
            d.pop("e164", None)
            return
        e = to_e164(d.get("number"), d.get("area_code"), d.get("country_code"))
        if e:
            d["e164"] = e

    def _save(self, call: Dict[str, Any]) -> None:
        self.store.save_call(call)

    def _sync(self, call: Dict[str, Any]) -> None:
        d = call["data"]
        cid = call["call_id"]
        created = self._ensure_conversation(call)
        self._save(call)
        conv = call["conversation_id"]
        existing: Optional[Dict[str, Any]] = {} if created else None

        def already(part: str) -> bool:
            nonlocal existing
            if part in call["parts"]:
                return True
            if existing is None:  # confere no ServiceDesk (proteção contra duplicar após falha parcial)
                existing = {m["source_id"]: m for m in self.cw.messages(conv) if m.get("source_id")}
            m = existing.get(source_id(cid, part))
            if m is not None:
                call["parts"].add(part)
                if part in ("atualizacao", "gravacao") and m.get("attachments"):
                    call["parts"].add("gravacao")
                    call["audio_status"] = "done"
                return True
            return False

        # 1) ficha da ligação
        if not already("registro"):
            self.cw.create_message(conv, notes.registro(d, self.s.tz_offset_hours), True, source_id(cid, "registro"))
            call["parts"].add("registro")
            self._save(call)

        # 2) atributos da ligação (sempre que mudarem)
        attrs = notes.call_attributes(d)
        sig = json.dumps(attrs, sort_keys=True, ensure_ascii=False)
        if d.get("_attrs_sig") != sig:
            self.cw.set_custom_attributes(conv, attrs)
            d["_attrs_sig"] = sig
            self._save(call)

        # 3) fim da ligação: atualização (+ gravação, quando der)
        if has_end_data(d) and not already("atualizacao"):
            attachment = self._try_audio(call) if call["audio_status"] == "pending" else None
            if not d.get("audio_url") and call["audio_status"] == "none":
                call["audio_status"] = "absent"
            self.cw.create_message(conv, notes.atualizacao(d, attachment is not None), True,
                                   source_id(cid, "atualizacao"), attachment=attachment)
            if attachment is not None:
                call["audio_status"] = "done"
                call["parts"].add("gravacao")
            call["parts"].add("atualizacao")
            self._save(call)
            self._trigger_close(call)

        # 4) ações (desconexão, humor)
        txt = notes.acao_desconexao(d)
        if txt and not already("acao_desconexao"):
            self.cw.create_message(conv, txt, True, source_id(cid, "acao_desconexao"))
            call["parts"].add("acao_desconexao")
            self._save(call)
        txt = notes.acao_humor(d)
        if txt and not already("acao_humor"):
            self.cw.create_message(conv, txt, True, source_id(cid, "acao_humor"))
            call["parts"].add("acao_humor")
            self._save(call)

        # 5) gravação que não estava pronta na hora da atualização
        if ("atualizacao" in call["parts"] and call["audio_status"] == "pending"
                and call.get("audio_next_at", 0) <= self.now() and not already("gravacao")):
            attachment = self._try_audio(call)
            if attachment is not None:
                self.cw.create_message(conv, notes.gravacao(d), True, source_id(cid, "gravacao"), attachment=attachment)
                call["audio_status"] = "done"
                call["parts"].add("gravacao")
            self._save(call)
        elif "gravacao" in call["parts"]:
            call["audio_status"] = "done"
            self._save(call)

    # ---------------------------------------------------------------- gravação
    def _try_audio(self, call: Dict[str, Any]):
        url = call["data"].get("audio_url")
        if not url:
            return None
        headers = {self.s.pbx_api_key_header: self.s.pbx_api_key} if (self.s.audio_send_api_key and self.s.pbx_api_key) else None
        try:
            mp3, size = self.audio_fetcher(url, self.s.audio_allowed_hosts, self.s.audio_max_mb, self.s.ffmpeg_bin,
                                           self.s.audio_bitrate, headers)
        except AudioError as e:
            call["audio_attempts"] = call.get("audio_attempts", 0) + 1
            if e.permanent or call["audio_attempts"] >= self.s.audio_max_attempts:
                call["audio_status"] = "failed"
            else:
                call["audio_next_at"] = self.now() + min(300 * 2 ** (call["audio_attempts"] - 1), 6 * 3600)
            log.warning("gravação da ligação %s não anexada (%s), tentativa %d", call["call_id"], e, call["audio_attempts"])
            return None
        log.info("gravação da ligação %s convertida: %d -> %d bytes", call["call_id"], size, len(mp3))
        call["data"]["_audio_bytes"] = [size, len(mp3)]
        return (mp3_name(call["call_id"]), mp3, "audio/mpeg")

    # ---------------------------------------------------------------- conversa
    def _ensure_conversation(self, call: Dict[str, Any]) -> bool:
        """Devolve True quando a conversa acabou de ser criada."""
        if call.get("conversation_id"):
            return False
        cid = call["call_id"]
        found = self.cw.find_conversation_by_attr("pbx_call_id", cid)
        if found:
            call["conversation_id"] = found["id"]
            log.info("ligação %s já tinha conversa #%s (recuperada)", cid, found["id"])
            return False
        d = call["data"]
        contact = self._resolve_contact(d)
        call["contact_id"] = contact["id"]
        agent = self._resolve_agent(d)
        team = self._resolve_team(d, agent)
        attrs = notes.call_attributes(d)
        area = self._area(team)
        if area:
            attrs["zd_area_interna"] = area
        if self.s.onboarding_value:
            attrs["zd_onboarding_relacionamento"] = self.s.onboarding_value
        if self.s.open_status_label:
            attrs["zd_status"] = self.s.open_status_label
        payload: Dict[str, Any] = {
            "inbox_id": self.s.pbx_inbox_id,
            "contact_id": contact["id"],
            "source_id": "55pbx-contact-%s" % contact["id"],
            "status": "open",
            "additional_attributes": {"pbx_call_id": cid, "mail_subject": notes.subject(d), "origem": "55pbx"},
            "custom_attributes": attrs,
        }
        if agent:
            payload["assignee_id"] = agent["id"]
        if team:
            payload["team_id"] = team["id"]
        conv = self.cw.create_conversation(payload)
        call["conversation_id"] = conv["id"]
        d["_attrs_sig"] = json.dumps(notes.call_attributes(d), sort_keys=True, ensure_ascii=False)
        labels = ["55pbx"] + (["55pbx_" + d["type"]] if d.get("type") else [])
        self.cw.add_labels(conv["id"], labels)
        log.info("ligação %s -> conversa #%s (contato %s, agente %s, time %s)", cid, conv["id"], contact["id"],
                 agent and agent["id"], team and team.get("name"))
        return True

    def _resolve_contact(self, d: Dict[str, Any]) -> Dict[str, Any]:
        e164 = d.get("e164")
        if e164:
            c = self.cw.find_contact_by_phone(mobile_variants(e164))
            if c:
                return c
            payload = {"name": d.get("client_name") or e164, "phone_number": e164,
                       "additional_attributes": {"origem": "55pbx"}}
            try:
                return self.cw.create_contact(payload)
            except ChatwootError as e:
                if e.status == 422:  # criado em paralelo / validação: tenta achar de novo
                    c = self.cw.find_contact_by_phone(mobile_variants(e164))
                    if c:
                        return c
                raise
        n = digits(d.get("number"))
        if n:
            ident, name = "55pbx-ramal-%s" % n, "Ramal %s (ligação interna)" % n
        else:
            ident, name = "55pbx-desconhecido", "Número não identificado (55PBX)"
        c = self.cw.find_contact_by_identifier(ident)
        if c:
            return c
        return self.cw.create_contact({"name": name, "identifier": ident, "additional_attributes": {"origem": "55pbx"}})

    def _resolve_agent(self, d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        br = digits(d.get("branch"))
        email = self.s.branch_agent_map.get(br) if br else None
        a = self.cw.find_agent(email=email) if email else None
        if a is None and self.s.agent_match_by_name and d.get("agent_name"):
            a = self.cw.find_agent(name=d["agent_name"])
        if a is None and (email or d.get("agent_name")):
            log.warning("agente da ligação %s não encontrado (ramal %s)", d.get("call_id"), br or "-")
        return a

    def _resolve_team(self, d: Dict[str, Any], agent: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Igual ao Zendesk: receptiva por fila conhecida -> time da fila; senão o time do agente (ramal);
        senão DEFAULT_TEAM."""
        name = None
        q = queue_key(d.get("queue") or "")
        if d.get("type") == "receptivo" and q in self.queue_map:
            name = self.queue_map[q]
        br = digits(d.get("branch"))
        if not name and br and br in self.s.branch_team_map:
            name = self.s.branch_team_map[br]
        if not name and agent:
            ts = self.cw.teams_of_agent(agent["id"])
            if len(ts) >= 1:
                return sorted(ts, key=lambda t: t["id"])[0]
        if not name and q in self.queue_map:
            name = self.queue_map[q]
        name = name or self.s.default_team
        t = self.cw.find_team(name) if name else None
        if name and t is None:
            log.warning("time '%s' não existe no ServiceDesk", name)
        return t

    def _area(self, team: Optional[Dict[str, Any]]) -> Optional[str]:
        if team and slug(team.get("name") or "") in self.area_map:
            return self.area_map[slug(team["name"])]
        return self.area_map.get(slug(self.s.default_team))

    # ---------------------------------------------------------------- gatilho 2
    def _trigger_close(self, call: Dict[str, Any]) -> None:
        """Zendesk 'Encerra os tickets da 55PABX ATIVOS do grupo Novos Negócios'."""
        if not self.s.trigger_close_enabled or "trigger_close" in call["parts"]:
            return
        d = call["data"]
        call["parts"].add("trigger_close")
        types = {slug(t) for t in self.s.trigger_close_types}
        if slug(d.get("type") or "") not in types:
            self._save(call)
            return
        conv = self.cw.get_conversation(call["conversation_id"])
        meta = conv.get("meta") or {}
        team = meta.get("team") or {}
        teams = {slug(t) for t in self.s.trigger_close_teams}
        if slug(team.get("name") or "") in teams and meta.get("assignee"):
            if self.s.trigger_close_attrs:
                self.cw.set_custom_attributes(call["conversation_id"], dict(self.s.trigger_close_attrs))
            if self.s.trigger_close_status:
                self.cw.toggle_status(call["conversation_id"], self.s.trigger_close_status)
            log.info("gatilho de encerramento aplicado na conversa #%s", call["conversation_id"])
        self._save(call)

    # ---------------------------------------------------------------- gatilho 1
    def handle_chatwoot_event(self, p: Dict[str, Any]) -> str:
        """Zendesk 'Atribui o usuário responsável pela ligação': agente atualiza ticket 55pbx sem responsável."""
        if not self.s.trigger_assign_on_agent_update:
            return "desligado"
        if p.get("event") != "message_created":
            return "ignorado: evento"
        sender = p.get("sender") or {}
        if (sender.get("type") or "").lower() != "user" or not sender.get("id"):
            return "ignorado: remetente"
        if self.s.integration_user_id and int(sender["id"]) == self.s.integration_user_id:
            return "ignorado: integração"
        conv = p.get("conversation") or {}
        inbox_id = conv.get("inbox_id") or (p.get("inbox") or {}).get("id")
        if int(inbox_id or 0) != self.s.pbx_inbox_id:
            return "ignorado: inbox"
        if "55pbx" not in (conv.get("labels") or []):
            return "ignorado: sem etiqueta"
        if (conv.get("meta") or {}).get("assignee"):
            return "ignorado: já tem responsável"
        self.cw.assign_agent(int(conv["id"]), int(sender["id"]))
        log.info("conversa #%s atribuída ao agente %s (gatilho de atribuição)", conv["id"], sender["id"])
        return "atribuído"


def describe(d: Dict[str, Any]) -> str:
    return mask(json.dumps({k: v for k, v in d.items() if not k.startswith("_")}, ensure_ascii=False))
