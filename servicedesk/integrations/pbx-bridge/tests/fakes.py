"""ServiceDesk falso em memória (mesma interface de pbx_bridge.chatwoot.Chatwoot)."""
from __future__ import annotations

import itertools

from pbx_bridge.chatwoot import ChatwootError
from pbx_bridge.normalize import slug

# Dados FICTÍCIOS.
AGENTS = [
    {"id": 11, "name": "Ana Teste", "email": "ana.teste@exemplo.test"},
    {"id": 12, "name": "Bruno Ficticio", "email": "bruno.ficticio@exemplo.test"},
]
TEAMS = [{"id": 1, "name": "Suporte"}, {"id": 2, "name": "Novos Negócios"}]
MEMBERS = {1: [11], 2: [12]}


class FakeCW:
    def __init__(self):
        self.ids = itertools.count(100)
        self.contacts = []
        self.convs = {}
        self.msgs = {}
        self.calls = []

    def _log(self, *a):
        self.calls.append(a)

    def agents(self):
        return AGENTS

    def teams(self):
        return TEAMS

    def find_agent(self, email=None, name=None):
        for a in AGENTS:
            if email and a["email"] == email.lower():
                return a
        if name:
            hits = [a for a in AGENTS if slug(a["name"]) == slug(name)]
            return hits[0] if len(hits) == 1 else None
        return None

    def find_team(self, name):
        for t in TEAMS:
            if slug(t["name"]) == slug(name):
                return t
        return None

    def teams_of_agent(self, agent_id):
        return [t for t in TEAMS if agent_id in MEMBERS[t["id"]]]

    def find_contact_by_phone(self, phones):
        for p in phones:
            for c in self.contacts:
                if c.get("phone_number") == p:
                    return c
        return None

    def find_contact_by_identifier(self, ident):
        for c in self.contacts:
            if c.get("identifier") == ident:
                return c
        return None

    def create_contact(self, payload):
        if payload.get("phone_number") and self.find_contact_by_phone([payload["phone_number"]]):
            raise ChatwootError(422, "phone taken")
        c = dict(payload, id=next(self.ids))
        self.contacts.append(c)
        self._log("create_contact", c["id"])
        return c

    def find_conversation_by_attr(self, key, value):
        for c in self.convs.values():
            if str(c["custom_attributes"].get(key)) == str(value):
                return c
        return None

    def create_conversation(self, payload):
        cid = next(self.ids)
        team = next((t for t in TEAMS if t["id"] == payload.get("team_id")), None)
        agent = next((a for a in AGENTS if a["id"] == payload.get("assignee_id")), None)
        c = {"id": cid, "inbox_id": payload["inbox_id"], "contact_id": payload["contact_id"],
             "custom_attributes": dict(payload.get("custom_attributes") or {}),
             "additional_attributes": payload.get("additional_attributes"), "status": payload.get("status", "open"),
             "labels": [], "meta": {"team": team, "assignee": agent}}
        self.convs[cid] = c
        self.msgs[cid] = []
        self._log("create_conversation", cid)
        return c

    def get_conversation(self, cid):
        return self.convs[cid]

    def messages(self, cid):
        self._log("messages", cid)
        return list(self.msgs[cid])

    def create_message(self, cid, content, private=True, source_id=None, attachment=None, content_attributes=None):
        m = {"id": next(self.ids), "content": content, "private": private, "source_id": source_id,
             "attachments": [attachment[0]] if attachment else [], "content_attributes": content_attributes or {},
             "audio_bytes": len(attachment[1]) if attachment else 0}
        self.msgs[cid].append(m)
        self._log("create_message", cid, source_id)
        return m

    def set_custom_attributes(self, cid, attrs):
        self.convs[cid]["custom_attributes"].update(attrs)
        self._log("set_custom_attributes", cid)

    def add_labels(self, cid, labels):
        self.convs[cid]["labels"] = sorted(set(self.convs[cid]["labels"]) | set(labels))
        return self.convs[cid]["labels"]

    def assign_agent(self, cid, agent_id):
        self.convs[cid]["meta"]["assignee"] = next(a for a in AGENTS if a["id"] == agent_id)
        self._log("assign_agent", cid, agent_id)

    def toggle_status(self, cid, status):
        self.convs[cid]["status"] = status
        self._log("toggle_status", cid, status)

    def filter_conversations(self, payload, page):
        label = payload[0]["values"][0]
        items = [c for c in self.convs.values() if label in c["labels"]]
        return {"payload": items[(page - 1) * 25: page * 25]}
