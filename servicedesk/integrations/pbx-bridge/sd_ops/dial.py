"""Click-to-call pela API documentada "Discagem automática para ramal" da 55PBX.

POST {PBX_DIAL_URL} (readme: https://ws.55pbx.com:20500/api/webphone/dial; o OpenAPI do mesmo readme mostra
/api/pbx/webphone/dial: por isso é configurável), headers client_code, api_key e Authorization: Bearer <JWT>,
corpo {"email": <e-mail do ramal na 55PBX>, "phone": <E.164>}. Respostas documentadas: 200 {status:"OK", call_id,
message}; 404 {status:"ERROR", email|phone}; 500 {error:"Usuário com requisição pendente."}.

Nunca simula sucesso: o modo mock existe só no DEV e devolve status "mock" + simulated=true.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from .config import OpsSettings

log = logging.getLogger("sd_ops.dial")
E164 = re.compile(r"^\+[1-9]\d{7,14}$")


@dataclass
class DialResult:
    status: str                      # accepted | rejected | error | mock | disabled
    http_status: Optional[int] = None
    provider_call_id: Optional[str] = None
    message: str = ""
    simulated: bool = False


class DialAdapter:
    def __init__(self, s: OpsSettings, client: Optional[httpx.Client] = None):
        self.s = s
        self.http = client or httpx.Client(timeout=s.dial_timeout_s, follow_redirects=False)

    def available(self, cfg: Optional[OpsSettings] = None) -> Optional[str]:
        """None se pode discar; senão o motivo (exibido desabilitado na interface). `cfg` = configuração em vigor
        do tenant (tela > ambiente); sem ela, a do processo."""
        s = cfg or self.s
        if s.dial_mode == "disabled":
            return "click-to-call desativado (PBX_DIAL_MODE=disabled ou modo disabled em Configurações > Telefonia 55PBX)"
        if s.dial_mode == "mock":
            return None if s.env == "dev" else "modo mock só é permitido no DEV"
        if not (s.dial_client_code and s.dial_api_key and s.dial_jwt):
            return "credenciais da API de discagem ausentes (client_code, api_key e JWT, pedidos ao suporte 55PBX)"
        return None

    def dial(self, pbx_email: str, phone: str, cfg: Optional[OpsSettings] = None) -> DialResult:
        s = cfg or self.s
        why = self.available(s)
        if why:
            return DialResult("disabled", message=why)
        if s.dial_mode == "mock":
            return DialResult("mock", message="MODO MOCK (DEV): nenhuma ligação foi feita", simulated=True)
        headers = {"client_code": s.dial_client_code, "api_key": s.dial_api_key,
                   "Authorization": "Bearer " + s.dial_jwt, "Content-Type": "application/json"}
        try:
            r = self.http.post(s.dial_url, json={"email": pbx_email, "phone": phone}, headers=headers,
                               timeout=s.dial_timeout_s)
        except httpx.TransportError as e:
            return DialResult("error", message="55PBX indisponível (%s)" % type(e).__name__)
        body: Dict[str, Any] = {}
        try:
            body = r.json() if r.content else {}
        except ValueError:
            body = {"raw": r.text[:200]}
        if not isinstance(body, dict):
            body = {"raw": str(body)[:200]}
        if r.status_code == 200 and str(body.get("status", "")).upper() == "OK":
            return DialResult("accepted", 200, str(body.get("call_id") or "") or None,
                              str(body.get("message") or "Ligação efetuada com sucesso"))
        msg = body.get("message") or body.get("error") or body.get("email") or body.get("phone") or body.get("raw") \
            or "HTTP %d" % r.status_code
        status = "rejected" if r.status_code in (400, 401, 403, 404, 422) or str(body.get("status", "")).upper() == "ERROR" \
            else "error"
        return DialResult(status, r.status_code, None, str(msg)[:300])
