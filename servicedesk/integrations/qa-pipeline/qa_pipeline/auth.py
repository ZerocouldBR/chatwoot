"""Autenticação da API de QA, alinhada ao CTI_AUTH.md do sd-ops (A2).

- Usuário (sd-console): a MESMA sessão do sd-ops (Bearer `session_token` ou cookie `sdops_session`).
  Validamos no servidor com `GET {SD_OPS_URL}/auth/me` (cache de 60 s pelo SHA-256 do token). Nunca
  confiamos no `currentAgent` do postMessage do Chatwoot.
- Serviço (n8n WF11, integrações): `Authorization: Bearer sdqa_<aleatório>`; `QA_SERVICE_TOKENS`
  guarda só o SHA-256, com tenants e escopos (qa:read, qa:write, csat:write).
- Modo `dev` (somente APP_ENV=dev): header `X-Dev-User: email;papeis;tenant` para testes locais.
Papéis: agente, supervisor, qa, admin (admin inclui supervisor e qa).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

import httpx
from fastapi import HTTPException, Request

from .config import Settings

ROLE_ALIASES = {"agent": "agente", "administrator": "admin", "agente": "agente", "admin": "admin",
                "supervisor": "supervisor", "qa": "qa"}


@dataclass
class Principal:
    ref: str              # e-mail do usuário ou "svc:<nome>"
    name: str
    tenant: str
    roles: Set[str] = field(default_factory=set)
    scopes: Set[str] = field(default_factory=set)
    is_service: bool = False
    user_id: Optional[str] = None

    @property
    def is_manager(self) -> bool:
        return bool(self.roles & {"supervisor", "qa", "admin"}) or "qa:read" in self.scopes

    def has(self, *roles: str) -> bool:
        return "admin" in self.roles or bool(self.roles & set(roles))


_cache: Dict[str, Tuple[float, Principal]] = {}


def _hash(tok: str) -> str:
    return hashlib.sha256(tok.encode()).hexdigest()


def _parse_me(data: dict, fallback_tenant: str) -> Principal:
    data = data.get("data", data) if isinstance(data, dict) else {}
    user = data.get("user") if isinstance(data.get("user"), dict) else data
    tenant = data.get("tenant")
    if isinstance(tenant, dict):
        tenant = tenant.get("slug") or tenant.get("id")
    roles = {ROLE_ALIASES.get(str(r).lower(), str(r).lower()) for r in (data.get("roles") or user.get("roles") or [])}
    email = user.get("email") or user.get("uid")
    if not email:
        raise HTTPException(401, detail={"error": "invalid_session", "message": "sessão sem usuário"})
    return Principal(ref=str(email).lower(), name=user.get("name") or email, tenant=str(tenant or fallback_tenant),
                     roles=roles, user_id=str(user.get("id")) if user.get("id") is not None else None)


class Authenticator:
    def __init__(self, settings: Settings, transport: Optional[httpx.BaseTransport] = None):
        self.s = settings
        self.transport = transport
        try:
            self.service_tokens = json.loads(settings_service_tokens()) if settings_service_tokens() else {}
        except json.JSONDecodeError:
            self.service_tokens = {}

    def _service(self, token: str) -> Optional[Principal]:
        h = _hash(token)
        for name, cfg in self.service_tokens.items():
            if hmac.compare_digest(h, str(cfg.get("sha256", ""))):
                tenants = cfg.get("tenants") or []
                tenant = tenants[0] if tenants and tenants[0] != "*" else self.s.tenant_default
                return Principal(ref=f"svc:{name}", name=name, tenant=tenant, scopes=set(cfg.get("scopes") or []),
                                 is_service=True)
        return None

    def _sdops_me(self, token: Optional[str], cookie: Optional[str]) -> Principal:
        key = _hash((token or "") + "|" + (cookie or ""))
        hit = _cache.get(key)
        if hit and hit[0] > time.time():
            return hit[1]
        if not self.s.sd_ops_url:
            raise HTTPException(503, detail={"error": "auth_unavailable", "message": "SD_OPS_URL não configurado"})
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        cookies = {"sdops_session": cookie} if cookie else None
        try:
            with httpx.Client(timeout=5.0, transport=self.transport) as c:
                r = c.get(f"{self.s.sd_ops_url.rstrip('/')}/auth/me", headers=headers, cookies=cookies)
        except httpx.HTTPError:
            raise HTTPException(503, detail={"error": "auth_unavailable", "message": "sd-ops indisponível para validar a sessão"})
        if r.status_code in (401, 403):
            raise HTTPException(401, detail={"error": "invalid_session", "message": "sessão inválida ou expirada"})
        if r.status_code != 200:
            raise HTTPException(503, detail={"error": "auth_unavailable", "message": f"sd-ops HTTP {r.status_code}"})
        p = _parse_me(r.json(), self.s.tenant_default)
        _cache[key] = (time.time() + 60, p)
        return p

    def __call__(self, request: Request) -> Principal:
        auth = request.headers.get("authorization", "")
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else None
        if token and token.startswith("sdqa_"):
            p = self._service(token)
            if p is None:
                raise HTTPException(401, detail={"error": "invalid_token", "message": "token de serviço inválido"})
            return p
        if self.s.auth_mode == "dev" and self.s.env == "dev" and request.headers.get("x-dev-user"):
            email, _, rest = request.headers["x-dev-user"].partition(";")
            roles, _, tenant = rest.partition(";")
            return Principal(ref=email.lower(), name=email, tenant=tenant or self.s.tenant_default,
                             roles={r for r in roles.split(",") if r})
        cookie = request.cookies.get("sdops_session")
        if not token and not cookie:
            raise HTTPException(401, detail={"error": "unauthenticated", "message": "faça login no CTI (sessão do sd-ops)"})
        return self._sdops_me(token, cookie)


def settings_service_tokens() -> str:
    import os
    return os.environ.get("QA_SERVICE_TOKENS", "").strip()


def require(p: Principal, *roles: str, scope: Optional[str] = None) -> None:
    if p.is_service:
        if scope and scope in p.scopes:
            return
        raise HTTPException(403, detail={"error": "forbidden", "message": "escopo insuficiente"})
    if roles and not p.has(*roles):
        raise HTTPException(403, detail={"error": "forbidden", "message": "permissão insuficiente"})


def new_service_token(name: str, tenants: List[str], scopes: List[str]) -> Tuple[str, str]:
    import secrets
    tok = "sdqa_" + secrets.token_urlsafe(32)
    line = json.dumps({name: {"sha256": _hash(tok), "tenants": tenants, "scopes": scopes}})
    return tok, line
