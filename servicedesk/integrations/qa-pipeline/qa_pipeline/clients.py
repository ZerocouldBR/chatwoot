"""Clientes HTTP: Chatwoot (API pública, nota privada) e sd-ops (dados da ligação).

Chatwoot: POST /api/v1/accounts/{account_id}/conversations/{conversation_id}/messages com
{"content", "message_type": "outgoing", "private": true, "source_id"} e header `api_access_token`
(documentação oficial "Create New Message"). Idempotência: antes de criar, procuramos nas
mensagens da conversa o `source_id` `qa:<recording_id>:<run>` (preservado em inbox API, como a
"Telefone (55PBX)") ou a mesma referência na última linha do texto (demais inboxes, onde o
Chatwoot limpa o source_id).
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx

log = logging.getLogger(__name__)


class ClientError(RuntimeError):
    def __init__(self, message: str, permanent: bool = False):
        super().__init__(message)
        self.permanent = permanent


class ChatwootClient:
    def __init__(self, base_url: str, token: str, account_id: str, timeout_s: float = 15.0,
                 transport: Optional[httpx.BaseTransport] = None):
        if not (base_url and token and account_id):
            raise ClientError("Chatwoot não configurado (CHATWOOT_URL/CHATWOOT_API_TOKEN/CHATWOOT_ACCOUNT_ID)", True)
        self.base = base_url.rstrip("/")
        self.account_id = account_id
        self.http = httpx.Client(timeout=timeout_s, headers={"api_access_token": token}, transport=transport)

    def _url(self, conversation_id: str, suffix: str = "") -> str:
        return f"{self.base}/api/v1/accounts/{self.account_id}/conversations/{conversation_id}{suffix}"

    def find_marker(self, conversation_id: str, marker: str) -> Optional[str]:
        try:
            r = self.http.get(self._url(conversation_id, "/messages"))
        except httpx.HTTPError as exc:
            raise ClientError(f"Chatwoot indisponível: {type(exc).__name__}") from exc
        if r.status_code == 404:
            raise ClientError("conversa não encontrada no Chatwoot", True)
        if r.status_code >= 300:
            raise ClientError(f"Chatwoot HTTP {r.status_code}", r.status_code in (401, 403))
        for m in (r.json() or {}).get("payload", []):
            if m.get("source_id") == marker or marker in (m.get("content") or ""):
                return str(m.get("id"))
        return None

    def post_private_note(self, conversation_id: str, content: str, marker: str) -> str:
        existing = self.find_marker(conversation_id, marker)
        if existing:
            return existing
        body = {"content": f"{content}\n\nRef.: {marker}", "message_type": "outgoing", "private": True,
                "source_id": marker}
        try:
            r = self.http.post(self._url(conversation_id, "/messages"), json=body)
        except httpx.HTTPError as exc:
            raise ClientError(f"Chatwoot indisponível: {type(exc).__name__}") from exc
        if r.status_code >= 300:
            raise ClientError(f"Chatwoot recusou a nota (HTTP {r.status_code})", r.status_code in (400, 401, 403, 404, 422))
        return str(r.json().get("id"))


class SdOpsClient:
    """Cliente do sd-ops (A2) com token de serviço `sdsvc_...` (CTI_AUTH.md §3).

    - GET /calls/{call_id} (escopo calls:read): agente/time quando o evento não traz. Falha aqui não
      bloqueia o QA: o agente fica "não identificado".
    - POST /analysis-results (escopo analysis:write, WEBHOOK_CONTRACTS.md §8.8): devolve transcrição,
      resumo e QA ao sd-ops; idempotente por (kind, external_id).
    """

    def __init__(self, base_url: str, token: str, transport: Optional[httpx.BaseTransport] = None):
        self.base = (base_url or "").rstrip("/")
        self.http = httpx.Client(timeout=10.0, transport=transport,
                                 headers={"Authorization": f"Bearer {token}"} if token else {})

    def call_info(self, call_id: str) -> dict:
        if not (self.base and call_id):
            return {}
        try:
            r = self.http.get(f"{self.base}/calls/{call_id}")
            if r.status_code != 200:
                return {}
            data = r.json()
        except Exception:  # sd-ops fora do ar/resposta inesperada: segue sem agente
            log.warning("sd-ops: não foi possível consultar a ligação")
            return {}
        data = data.get("data", data) if isinstance(data, dict) else {}
        agent = data.get("agent") if isinstance(data.get("agent"), dict) else {}
        legs = [lg for lg in (data.get("legs") or []) if isinstance(lg, dict)]
        last_leg = next((lg for lg in reversed(legs) if lg.get("agent_email")), {})
        return {"agent_ref": agent.get("email") or data.get("agent_email") or last_leg.get("agent_email"),
                "agent_name": agent.get("name") or data.get("agent_name") or last_leg.get("agent_name"),
                "team": data.get("team") or data.get("queue") or last_leg.get("queue")}

    def post_analysis_result(self, body: dict) -> str:
        if not self.base:
            raise ClientError("SD_OPS_URL não configurado", True)
        try:
            r = self.http.post(f"{self.base}/analysis-results", json=body,
                               headers={"Idempotency-Key": f"{body['kind']}:{body['external_id']}"})
        except httpx.HTTPError as exc:
            raise ClientError(f"sd-ops indisponível: {type(exc).__name__}") from exc
        if r.status_code in (200, 201, 202):
            return "duplicate" if (r.json() or {}).get("duplicate") else "delivered"
        if r.status_code in (400, 401, 403, 404, 422):
            raise ClientError(f"sd-ops recusou o resultado (HTTP {r.status_code})", True)
        raise ClientError(f"sd-ops HTTP {r.status_code}")
