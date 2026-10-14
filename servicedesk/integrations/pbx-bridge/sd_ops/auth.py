"""Autenticação do CTI (troca do token pessoal do Chatwoot por sessão curta), tokens de serviço e RBAC.
Ver docs/integrations/CTI_AUTH.md."""
from __future__ import annotations

import datetime as dt
import hmac
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

import httpx
import sqlalchemy as sa

from . import db
from . import models as m
from .config import OpsSettings

COOKIE = "sdops_session"
ROLE_ORDER = ("agente", "qa", "supervisor", "admin")


@dataclass
class Principal:
    kind: str                         # user | service
    tenant_id: str
    roles: Set[str] = field(default_factory=set)
    scopes: Set[str] = field(default_factory=set)
    user_id: Optional[int] = None
    email: Optional[str] = None
    name: Optional[str] = None
    service: Optional[str] = None
    via_cookie: bool = False
    csrf_sha256: Optional[str] = None
    tenants: Set[str] = field(default_factory=set)   # token de serviço: tenants permitidos ("*" = todos)
    caused_by: Optional[str] = None                  # "n8n:WFxx" (anti-loop)

    @property
    def actor(self) -> str:
        return "user:%s" % self.user_id if self.kind == "user" else "service:%s" % self.service

    def has(self, *roles: str) -> bool:
        r = set(self.roles)
        if "admin" in r:
            r |= {"supervisor", "qa", "agente"}
        return bool(r & set(roles))

    def can(self, scope: str, *roles: str) -> bool:
        return (self.kind == "service" and scope in self.scopes) or (self.kind == "user" and self.has(*roles))


class AuthError(Exception):
    def __init__(self, code: str, message: str, http: int = 401):
        super().__init__(message)
        self.code, self.message, self.http = code, message, http


class RateLimiter:
    def __init__(self) -> None:
        self.hits: Dict[str, List[float]] = {}
        self.lock = threading.Lock()

    def allow(self, key: str, per_min: int) -> bool:
        now = time.time()
        with self.lock:
            h = [t for t in self.hits.get(key, []) if now - t < 60]
            if len(h) >= per_min:
                self.hits[key] = h
                return False
            h.append(now)
            self.hits[key] = h
            return True


def chatwoot_profile(base_url: str, token: str, client: Optional[httpx.Client] = None) -> Dict[str, Any]:
    """GET /api/v1/profile (API pública do Chatwoot) com o token pessoal do agente."""
    c = client or httpx.Client(timeout=10.0, follow_redirects=False)
    try:
        r = c.get(base_url.rstrip("/") + "/api/v1/profile", headers={"api_access_token": token})
    except httpx.TransportError:
        raise AuthError("chatwoot_unavailable", "Chatwoot indisponível para validar o token", 503)
    if r.status_code in (401, 403):
        raise AuthError("invalid_chatwoot_token", "token do Chatwoot inválido", 401)
    if r.status_code != 200:
        raise AuthError("chatwoot_error", "Chatwoot respondeu HTTP %d" % r.status_code, 502)
    return r.json()


class Auth:
    def __init__(self, s: OpsSettings, engine, profile_fn: Callable[[str], Dict[str, Any]] = None):
        self.s, self.engine = s, engine
        self.profile_fn = profile_fn or (lambda tok: chatwoot_profile(s.bridge.chatwoot_url, tok))
        self.limiter = RateLimiter()

    # ------------------------------------------------------------------ sessão
    def create_session(self, chatwoot_token: str, account_id: int, ip: str = "") -> Dict[str, Any]:
        if not self.limiter.allow("auth:" + ip, self.s.auth_rate_limit_per_min):
            raise AuthError("rate_limited", "muitas tentativas; aguarde um minuto", 429)
        if not chatwoot_token or len(chatwoot_token) > 200:
            raise AuthError("invalid_chatwoot_token", "token do Chatwoot inválido", 401)
        try:
            prof = self.profile_fn(chatwoot_token)
        except AuthError as e:
            with self.engine.begin() as conn:
                db.audit(conn, None, "auth.failed", data={"reason": e.code, "account_id": account_id},
                         actor_type="anonymous", ip=ip)
            raise
        acc = next((a for a in prof.get("accounts") or [] if int(a.get("id") or 0) == int(account_id)), None)
        with self.engine.begin() as conn:
            ten = conn.execute(sa.select(m.tenants).where(m.tenants.c.chatwoot_account_id == int(account_id),
                                                          m.tenants.c.active.is_(True))).first()
            denied = acc is None or ten is None
            if not denied:
                roles = {"admin" if acc.get("role") == "administrator" else "agente"}
                roles |= {r[0] for r in conn.execute(sa.select(m.user_roles.c.role).where(
                    m.user_roles.c.tenant_id == ten.id, m.user_roles.c.chatwoot_user_id == int(prof["id"])))}
                token = secrets.token_urlsafe(32)
                csrf = secrets.token_urlsafe(24)
                now = db.utcnow()
                exp = now + dt.timedelta(minutes=self.s.session_idle_min)
                conn.execute(m.cti_sessions.insert().values(
                    token_sha256=db.sha256(token), csrf_sha256=db.sha256(csrf), tenant_id=ten.id,
                    chatwoot_user_id=int(prof["id"]), email=prof.get("email"), name=prof.get("name"),
                    roles=sorted(roles), ip=ip, created_at=now, last_seen_at=now, expires_at=exp))
                db.audit(conn, ten.id, "auth.session_created", "user", prof["id"], {"roles": sorted(roles)},
                         actor_type="user", actor_id=str(prof["id"]), ip=ip)
        if denied:
            with self.engine.begin() as conn:
                db.audit(conn, ten.id if ten else None, "auth.failed",
                         data={"reason": "account_not_allowed", "account_id": account_id},
                         actor_type="user", actor_id=str(prof.get("id")), ip=ip)
            raise AuthError("account_not_allowed", "usuário sem acesso a esta conta", 403)
        return {"session_token": token, "csrf_token": csrf, "expires_at": db.iso(exp),
                "user": {"id": int(prof["id"]), "name": prof.get("name"), "email": prof.get("email")},
                "tenant": {"id": ten.id, "name": ten.name, "chatwoot_account_id": ten.chatwoot_account_id},
                "roles": sorted(roles)}

    def session(self, token: str, via_cookie: bool) -> Principal:
        now = db.utcnow()
        with self.engine.begin() as conn:
            r = conn.execute(sa.select(m.cti_sessions).where(m.cti_sessions.c.token_sha256 == db.sha256(token))).first()
            if r is None or r.revoked_at is not None or r.expires_at < now or \
                    r.created_at + dt.timedelta(hours=self.s.session_max_hours) < now:
                raise AuthError("session_expired", "sessão inválida ou expirada", 401)
            new_exp = min(now + dt.timedelta(minutes=self.s.session_idle_min),
                          r.created_at + dt.timedelta(hours=self.s.session_max_hours))
            conn.execute(m.cti_sessions.update().where(m.cti_sessions.c.id == r.id).values(
                last_seen_at=now, expires_at=new_exp))
        return Principal("user", r.tenant_id, set(r.roles), set(), r.chatwoot_user_id, r.email, r.name,
                         via_cookie=via_cookie, csrf_sha256=r.csrf_sha256)

    def revoke(self, token: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(m.cti_sessions.update().where(m.cti_sessions.c.token_sha256 == db.sha256(token)).values(
                revoked_at=db.utcnow()))

    def revoke_user(self, tenant_id: str, user_id: int) -> int:
        with self.engine.begin() as conn:
            return conn.execute(m.cti_sessions.update().where(
                m.cti_sessions.c.tenant_id == tenant_id, m.cti_sessions.c.chatwoot_user_id == user_id,
                m.cti_sessions.c.revoked_at.is_(None)).values(revoked_at=db.utcnow())).rowcount

    # ------------------------------------------------------------------ serviço
    def service(self, token: str, tenant_hint: Optional[str]) -> Principal:
        h = db.sha256(token)
        for name, cfg in (self.s.service_tokens or {}).items():
            if hmac.compare_digest(h, str(cfg.get("sha256", ""))):
                allowed = set(cfg.get("tenants") or [])
                tenant = tenant_hint or (sorted(allowed - {"*"})[0] if allowed - {"*"} else self.s.default_tenant)
                if "*" not in allowed and tenant not in allowed:
                    raise AuthError("tenant_forbidden", "token de serviço sem acesso a este tenant", 403)
                scopes = set(cfg.get("scopes") or [])
                return Principal("service", tenant, set(), scopes, service=name, tenants=allowed)
        raise AuthError("invalid_token", "token inválido", 401)

    def check_csrf(self, p: Principal, header: Optional[str]) -> None:
        if p.kind == "user" and p.via_cookie:
            if not header or not hmac.compare_digest(db.sha256(header), p.csrf_sha256 or ""):
                raise AuthError("csrf", "header X-SD-CSRF ausente ou inválido", 403)


def new_service_token() -> Dict[str, str]:
    tok = "sdsvc_" + secrets.token_urlsafe(32)
    return {"token": tok, "sha256": db.sha256(tok)}
