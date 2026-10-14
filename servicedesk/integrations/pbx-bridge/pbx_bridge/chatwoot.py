"""Cliente mínimo da API do Chatwoot (ServiceDesk), com retentativa e backoff."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .normalize import slug

log = logging.getLogger("pbx_bridge.chatwoot")


class ChatwootError(Exception):
    def __init__(self, status: int, msg: str):
        super().__init__("Chatwoot HTTP %s: %s" % (status, msg[:300]))
        self.status = status


RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}


class Chatwoot:
    def __init__(self, base_url: str, token: str, account_id: int, timeout: float = 60.0,
                 retries: int = 4, client: Optional[httpx.Client] = None, sleep=time.sleep):
        self.base = "%s/api/v1/accounts/%d" % (base_url.rstrip("/"), account_id)
        self.http = client or httpx.Client(timeout=timeout, headers={"api_access_token": token})
        if client is not None:
            self.http.headers["api_access_token"] = token
        self.retries = retries
        self.sleep = sleep
        self._agents: Tuple[float, List[Dict[str, Any]]] = (0.0, [])
        self._teams: Tuple[float, List[Dict[str, Any]]] = (0.0, [])
        self._team_members: Dict[int, Tuple[float, List[int]]] = {}

    # ------------------------------------------------------------------ http
    def req(self, method: str, path: str, retry: bool = True, **kw: Any) -> Any:
        """retry=False em criações não idempotentes: a retentativa fica com a fila de eventos, que confere
        antes (source_id da mensagem, pbx_call_id da conversa) para não duplicar."""
        url = self.base + path
        last: Optional[Exception] = None
        tries = self.retries + 1 if retry else 1
        for attempt in range(tries):
            try:
                r = self.http.request(method, url, **kw)
            except (httpx.TransportError,) as e:
                last = e
                log.warning("chatwoot %s %s falhou (%s), tentativa %d", method, path.split("?")[0], type(e).__name__, attempt + 1)
            else:
                if r.status_code < 400:
                    if not r.content:
                        return None
                    try:
                        return r.json()
                    except ValueError:
                        return r.text
                if r.status_code not in RETRY_STATUS:
                    raise ChatwootError(r.status_code, r.text)
                last = ChatwootError(r.status_code, r.text)
                log.warning("chatwoot %s %s -> %s, tentativa %d", method, path.split("?")[0], r.status_code, attempt + 1)
            if attempt < tries - 1:
                self.sleep(min(2 ** attempt, 30))
        assert last is not None
        raise last

    # ------------------------------------------------------------------ cadastros
    def agents(self, ttl: int = 600) -> List[Dict[str, Any]]:
        if time.time() - self._agents[0] > ttl:
            self._agents = (time.time(), self.req("GET", "/agents") or [])
        return self._agents[1]

    def teams(self, ttl: int = 600) -> List[Dict[str, Any]]:
        if time.time() - self._teams[0] > ttl:
            self._teams = (time.time(), self.req("GET", "/teams") or [])
        return self._teams[1]

    def team_member_ids(self, team_id: int, ttl: int = 600) -> List[int]:
        t = self._team_members.get(team_id)
        if not t or time.time() - t[0] > ttl:
            ids = [m["id"] for m in (self.req("GET", "/teams/%d/team_members" % team_id) or [])]
            self._team_members[team_id] = (time.time(), ids)
        return self._team_members[team_id][1]

    def find_agent(self, email: Optional[str] = None, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
        ags = self.agents()
        if email:
            for a in ags:
                if (a.get("email") or "").lower() == email.lower():
                    return a
        if name:
            n = slug(name)
            hits = [a for a in ags if slug(a.get("name") or "") == n or slug(a.get("available_name") or "") == n]
            if len(hits) == 1:
                return hits[0]
        return None

    def find_team(self, name: str) -> Optional[Dict[str, Any]]:
        n = slug(name)
        for t in self.teams():
            if slug(t.get("name") or "") == n:
                return t
        return None

    def teams_of_agent(self, agent_id: int) -> List[Dict[str, Any]]:
        return [t for t in self.teams() if agent_id in self.team_member_ids(t["id"])]

    # ------------------------------------------------------------------ contatos
    def search_contacts(self, q: str) -> List[Dict[str, Any]]:
        r = self.req("GET", "/contacts/search", params={"q": q, "include_contact_inboxes": "false"})
        return (r or {}).get("payload", []) if isinstance(r, dict) else []

    def find_contact_by_phone(self, phones: List[str]) -> Optional[Dict[str, Any]]:
        for p in phones:
            for c in self.search_contacts(p):
                if (c.get("phone_number") or "") == p:
                    return c
        return None

    def find_contact_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        for c in self.search_contacts(identifier):
            if c.get("identifier") == identifier:
                return c
        return None

    def create_contact(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        r = self.req("POST", "/contacts", retry=False, json=payload)
        return (r.get("payload") or {}).get("contact") or r.get("payload") or r

    # ------------------------------------------------------------------ conversas
    def find_conversation_by_attr(self, key: str, value: str) -> Optional[Dict[str, Any]]:
        body = {"payload": [{"attribute_key": key, "attribute_model": "customAttributes",
                             "custom_attribute_type": "conversation_attribute",
                             "filter_operator": "equal_to", "values": [value], "query_operator": None}]}
        r = self.req("POST", "/conversations/filter?page=1", json=body)
        items = (r or {}).get("payload", []) if isinstance(r, dict) else []
        for it in items:
            if str((it.get("custom_attributes") or {}).get(key)) == str(value):
                return it
        return None

    def create_conversation(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self.req("POST", "/conversations", retry=False, json=payload)

    def get_conversation(self, display_id: int) -> Dict[str, Any]:
        return self.req("GET", "/conversations/%d" % display_id)

    def messages(self, display_id: int) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        before = None
        for _ in range(50):
            params = {"before": before} if before else {}
            r = self.req("GET", "/conversations/%d/messages" % display_id, params=params) or {}
            page = r.get("payload", [])
            if not page:
                break
            out = page + out
            if len(page) < 20:
                break
            before = min(m["id"] for m in page)
        return out

    def create_message(self, display_id: int, content: str, private: bool = True, source_id: Optional[str] = None,
                       attachment: Optional[Tuple[str, bytes, str]] = None,
                       content_attributes: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        path = "/conversations/%d/messages" % display_id
        if attachment is None:
            body: Dict[str, Any] = {"content": content, "private": private, "message_type": "outgoing"}
            if source_id:
                body["source_id"] = source_id
            if content_attributes:
                body["content_attributes"] = content_attributes
            return self.req("POST", path, retry=False, json=body)
        data = {"content": content, "private": "true" if private else "false", "message_type": "outgoing"}
        if source_id:
            data["source_id"] = source_id
        if content_attributes:
            data["content_attributes"] = json.dumps(content_attributes)
        name, blob, ctype = attachment
        return self.req("POST", path, retry=False, data=data, files=[("attachments[]", (name, blob, ctype))])

    def set_custom_attributes(self, display_id: int, attrs: Dict[str, Any]) -> Any:
        return self.req("POST", "/conversations/%d/custom_attributes" % display_id,
                        json={"custom_attributes": attrs, "merge": True})

    def add_labels(self, display_id: int, labels: List[str]) -> List[str]:
        cur = (self.req("GET", "/conversations/%d/labels" % display_id) or {}).get("payload", [])
        want = sorted(set(cur) | set(labels))
        if set(want) != set(cur):
            self.req("POST", "/conversations/%d/labels" % display_id, json={"labels": want})
        return want

    def assign_agent(self, display_id: int, agent_id: int) -> Any:
        return self.req("POST", "/conversations/%d/assignments" % display_id, json={"assignee_id": agent_id})

    def assign_team(self, display_id: int, team_id: int) -> Any:
        return self.req("POST", "/conversations/%d/assignments" % display_id, json={"team_id": team_id})

    def toggle_status(self, display_id: int, status: str) -> Any:
        return self.req("POST", "/conversations/%d/toggle_status" % display_id, json={"status": status})

    def filter_conversations(self, payload: List[Dict[str, Any]], page: int) -> Dict[str, Any]:
        return self.req("POST", "/conversations/filter?page=%d" % page, json={"payload": payload}) or {}
