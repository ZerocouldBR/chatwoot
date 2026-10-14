"""API REST /sd-ops/api/v1 + webhooks + URA. Contratos: docs/integrations/WEBHOOK_CONTRACTS.md §8."""
from __future__ import annotations

import base64
import datetime as dt
import hmac
import ipaddress
import json
import logging
import time
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Body, Depends, Query, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert as pg_insert

from pbx_bridge.normalize import mask, to_e164

from . import db, obs, reports, sla, tickets, views
from . import models as m
from .auth import COOKIE, AuthError, Principal
from .storage import parse_range
from .tickets import TicketError
from .worker import accept

log = logging.getLogger("sd_ops.api")
PREFIX = "/sd-ops/api/v1"


class ApiError(Exception):
    def __init__(self, code: str, message: str, http: int = 400, extra: Optional[dict] = None):
        super().__init__(message)
        self.code, self.message, self.http, self.extra = code, message, http, extra or {}


def err(code: str, message: str, http: int, **extra: Any) -> JSONResponse:
    return JSONResponse(dict({"error": code, "message": message}, **extra), status_code=http)


# ------------------------------------------------------------------ corpos (OpenAPI)
class SessionIn(BaseModel):
    chatwoot_token: str = Field(..., description="Token de acesso pessoal do agente no Chatwoot (não é guardado)")
    account_id: int


class DialIn(BaseModel):
    phone: str = Field(..., description="Número em E.164, ex. +5511999990001")
    ticket_id: Optional[str] = None
    conversation_id: Optional[int] = None
    contact_id: Optional[int] = None
    agent_email: Optional[str] = Field(None, description="Só para token de serviço")


class TicketIn(BaseModel):
    subject: str
    description: Optional[str] = None
    contact_id: Optional[int] = None
    contact_e164: Optional[str] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    organization: Optional[str] = None
    conversation_id: Optional[int] = None
    call_id: Optional[str] = None
    channel: str = "phone"
    origin: str = "manual"
    priority: str = "normal"
    severity: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    type: Optional[str] = None
    department: Optional[str] = None
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    assignee_id: Optional[int] = None


class TicketPatch(BaseModel):
    version: Optional[int] = Field(None, description="Controle de concorrência otimista")
    subject: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    type: Optional[str] = None
    priority: Optional[str] = None
    severity: Optional[str] = None
    department: Optional[str] = None
    team_id: Optional[int] = None
    team_name: Optional[str] = None
    assignee_id: Optional[int] = None
    organization: Optional[str] = None
    contact_id: Optional[int] = None
    contact_email: Optional[str] = None
    contact_name: Optional[str] = None
    needs_identification: Optional[bool] = None


class TransitionIn(BaseModel):
    to: str
    reason: Optional[str] = ""


class EscalateIn(BaseModel):
    reason: str
    priority: Optional[str] = None
    team_id: Optional[int] = None
    team_name: Optional[str] = None


class NoteIn(BaseModel):
    kind: str = Field("nota_interna", description="registro | disposicao | nota_interna")
    body: Optional[str] = None
    disposition: Dict[str, Any] = Field(default_factory=dict,
                                        description="categoria, motivo, resultado, pendencias, agendamento, acoes")
    call_id: Optional[str] = None
    post_to_chatwoot: bool = True


class LinkIn(BaseModel):
    conversation_id: Optional[int] = None
    call_id: Optional[str] = None


class CallbackIn(BaseModel):
    number_e164: str
    reason: str = "manual"
    ticket_id: Optional[str] = None
    call_id: Optional[str] = None
    due_at: Optional[str] = None
    assigned_to: Optional[int] = None


class CallbackPatch(BaseModel):
    status: Optional[str] = Field(None, description="done | cancelled | pending")
    result: Optional[str] = None
    assigned_to: Optional[int] = None


class AnalysisIn(BaseModel):
    kind: str
    status: str
    external_id: str
    call_id: Optional[str] = None
    recording_id: Optional[str] = None
    score: Optional[float] = None
    completed_at: Optional[str] = None
    data: Dict[str, Any] = Field(default_factory=dict)


class ReconcileIn(BaseModel):
    from_: str = Field(..., alias="from")
    to: str


class NotificationLogIn(BaseModel):
    channel: str
    template: Optional[str] = None
    ticket_id: Optional[str] = None
    call_id: Optional[str] = None
    status: str = "sent"
    opt_out: bool = False
    detail: Dict[str, Any] = Field(default_factory=dict)


class MappingIn(BaseModel):
    branch: str
    agent_email: str
    pbx_email: Optional[str] = None
    chatwoot_user_id: Optional[int] = None
    active: bool = True


class RuleIn(BaseModel):
    name: str
    sort: int = 100
    direction: Optional[str] = None
    queue_pattern: Optional[str] = None
    mode: str
    reuse: str
    reuse_window_hours: int = 24
    default_priority: str = "normal"
    active: bool = True


class RoleIn(BaseModel):
    chatwoot_user_id: int
    role: str


class RouteIn(BaseModel):
    name: str
    event_types: List[str]
    url: str
    token_ref: Optional[str] = None
    secret_ref: Optional[str] = None
    active: bool = True


def _when(v: Optional[str], default: dt.datetime) -> dt.datetime:
    if not v:
        return default
    try:
        d = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError("invalid_date", "data inválida: %s" % v, 422)
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def _client_ip(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[-1].strip()
    return request.client.host if request.client else ""


def _ip_ok(ip: str, allowed: List[str]) -> bool:
    if not allowed:
        return True
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for n in allowed:
        try:
            if a in ipaddress.ip_network(n, strict=False):
                return True
        except ValueError:
            continue
    return False


async def _read_limited(request: Request, limit: int) -> Optional[bytes]:
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > limit:
        return None
    buf = bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf) > limit:
            return None
    return bytes(buf)


def build(svc) -> APIRouter:
    s, engine, auth = svc.s, svc.engine, svc.auth
    r = APIRouter()

    # ============================================================== autenticação
    def _principal(request: Request) -> Principal:
        authz = request.headers.get("authorization", "")
        tok = authz[7:].strip() if authz.lower().startswith("bearer ") else ""
        try:
            if tok.startswith("sdsvc_"):
                p = auth.service(tok, request.headers.get("x-sd-tenant"))
            elif tok:
                p = auth.session(tok, via_cookie=False)
            elif request.cookies.get(COOKIE):
                p = auth.session(request.cookies[COOKIE], via_cookie=True)
            else:
                raise AuthError("unauthenticated", "autenticação necessária", 401)
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                auth.check_csrf(p, request.headers.get("x-sd-csrf"))
                origin = request.headers.get("origin")
                if origin and p.via_cookie and s.allowed_origins and origin not in s.allowed_origins:
                    raise AuthError("origin", "origem não permitida", 403)
        except AuthError as e:
            raise ApiError(e.code, e.message, e.http)
        if request.headers.get("x-sd-origin", "").lower() == "n8n":
            p.caused_by = "n8n:%s" % (request.headers.get("x-sd-workflow") or "?")
        return p

    async def principal(p: Principal = Depends(_principal)) -> Principal:
        # dependência assíncrona: o contexto (tenant, ator, caused_by) chega ao endpoint e aos eventos gerados
        obs.bind(tenant=p.tenant_id, actor=p.actor, caused_by=p.caused_by)
        return p

    def need(p: Principal, scope: str, *roles: str) -> None:
        if not p.can(scope, *roles):
            raise ApiError("forbidden", "sem permissão", 403)

    def idem_get(request: Request, p: Principal):
        key = request.headers.get("idempotency-key")
        if not key or p.kind != "service":
            return None, None
        k = "%s:%s:%s" % (p.actor, p.tenant_id, key)
        with engine.begin() as conn:
            r = conn.execute(sa.select(m.idempotency_keys).where(m.idempotency_keys.c.key == k)).first()
        if r is not None:
            return k, JSONResponse(r.response, status_code=r.status_code, headers={"Idempotent-Replay": "true"})
        return k, None

    def idem_put(k: Optional[str], p: Principal, request: Request, code: int, body: Any) -> JSONResponse:
        body = json.loads(json.dumps(body, default=str))
        if k:
            with engine.begin() as conn:
                conn.execute(pg_insert(m.idempotency_keys).values(
                    key=k, tenant_id=p.tenant_id, method=request.method, path=request.url.path, status_code=code,
                    response=body).on_conflict_do_nothing())
        return JSONResponse(body, status_code=code)

    @r.post(PREFIX + "/auth/session", tags=["auth"])
    def create_session(body: SessionIn, request: Request, response: Response):
        try:
            out = auth.create_session(body.chatwoot_token, body.account_id, _client_ip(request, s.bridge.trust_proxy))
        except AuthError as e:
            raise ApiError(e.code, e.message, e.http)
        resp = JSONResponse(out)
        resp.set_cookie(COOKIE, out["session_token"], max_age=s.session_idle_min * 60, httponly=True,
                        secure=s.cookie_secure, samesite="none" if s.cookie_secure else "lax", path="/sd-ops")
        return resp

    @r.get(PREFIX + "/auth/me", tags=["auth"])
    def me(p: Principal = Depends(principal)):
        return {"kind": p.kind, "tenant_id": p.tenant_id, "user_id": p.user_id, "email": p.email, "name": p.name,
                "roles": sorted(p.roles), "scopes": sorted(p.scopes), "service": p.service}

    @r.post(PREFIX + "/auth/logout", tags=["auth"])
    def logout(request: Request, p: Principal = Depends(principal)):
        authz = request.headers.get("authorization", "")
        tok = authz[7:].strip() if authz.lower().startswith("bearer ") else request.cookies.get(COOKIE, "")
        if tok and not tok.startswith("sdsvc_"):
            auth.revoke(tok)
        resp = JSONResponse({"ok": True})
        resp.delete_cookie(COOKIE, path="/sd-ops")
        return resp

    # ============================================================== saúde
    @r.get(PREFIX + "/health", tags=["operação"])
    def health():
        return svc.health(full=False)

    @r.get(PREFIX + "/ready", tags=["operação"])
    def ready():
        h = svc.health(full=True)
        return JSONResponse(h, status_code=200 if h["status"] == "ok" else 503)

    # ============================================================== contexto
    @r.get(PREFIX + "/context", tags=["cti"])
    def context(conversation_id: Optional[int] = None, contact_id: Optional[int] = None, phone: Optional[str] = None,
                p: Principal = Depends(principal)):
        need(p, "calls:read", "agente")
        contact = None
        cw = None
        try:
            cw = svc.sync.tenant(p.tenant_id).cw
        except Exception:  # noqa: BLE001
            cw = None
        if conversation_id and not contact_id and cw is not None:
            try:
                conv = cw.get_conversation(conversation_id) or {}
                contact_id = ((conv.get("meta") or {}).get("sender") or {}).get("id") or conv.get("contact_id")
            except Exception:  # noqa: BLE001
                pass
        if contact_id and cw is not None and hasattr(cw, "get_contact"):
            try:
                c = cw.get_contact(int(contact_id)) or {}
                contact = {k: c.get(k) for k in ("id", "name", "phone_number", "email", "identifier")}
            except Exception:  # noqa: BLE001
                contact = {"id": contact_id}
        e164 = to_e164(phone) if phone else ((contact or {}).get("phone_number") or None)
        with engine.begin() as conn:
            t = m.support_tickets
            conds = []
            if contact_id:
                conds.append(t.c.contact_id == int(contact_id))
            if e164:
                from pbx_bridge.normalize import mobile_variants
                conds.append(t.c.contact_e164.in_(mobile_variants(e164)))
            if conversation_id:
                conds.append(t.c.id.in_(sa.select(m.ticket_conversations.c.ticket_id).where(
                    m.ticket_conversations.c.conversation_id == conversation_id)))
            open_t = []
            if conds:
                open_t = [views.ticket_view(conn, dict(x._mapping)) for x in conn.execute(sa.select(t).where(
                    t.c.tenant_id == p.tenant_id, t.c.deleted_at.is_(None), t.c.status.in_(tickets.OPEN_STATES),
                    sa.or_(*conds)).order_by(t.c.updated_at.desc()).limit(20))]
            cq = None
            if conversation_id or contact_id or e164:
                c = m.calls
                cconds = []
                if conversation_id:
                    cconds.append(c.c.conversation_id == conversation_id)
                if contact_id:
                    cconds.append(c.c.contact_id == int(contact_id))
                if e164:
                    from pbx_bridge.normalize import mobile_variants
                    cconds.append(c.c.number_e164.in_(mobile_variants(e164)))
                cq = sa.select(c).where(c.c.tenant_id == p.tenant_id, c.c.state != "merged", sa.or_(*cconds)).order_by(
                    c.c.started_at.desc().nullslast()).limit(10)
            calls = [views.call_view(conn, dict(x._mapping)) for x in conn.execute(cq)] if cq is not None else []
            active = next((x for x in calls if x["state"] == "active"), None)
            cbs = []
            if e164:
                from pbx_bridge.normalize import mobile_variants
                cbs = [{"id": x.id, "reason": x.reason, "status": x.status, "due_at": db.iso(x.due_at), "call_id": x.call_id}
                       for x in conn.execute(sa.select(m.callback_tasks).where(
                           m.callback_tasks.c.tenant_id == p.tenant_id, m.callback_tasks.c.status == "pending",
                           m.callback_tasks.c.number_e164.in_(mobile_variants(e164))))]
        ident = "none"
        if contact or e164:
            ident = "ambiguous" if any(x.get("needs_identification") for x in open_t) else ("unique" if contact else "none")
        return {"contact": contact, "phone_e164": e164, "identification": ident, "open_tickets": open_t,
                "recent_calls": calls, "active_call": active, "callbacks_pending": cbs,
                "dial": {"available": svc.dial.available() is None, "reason": svc.dial.available()}}

    # ============================================================== chamadas
    @r.get(PREFIX + "/calls", tags=["chamadas"])
    def list_calls(conversation_id: Optional[int] = None, contact_id: Optional[int] = None,
                   ticket_id: Optional[str] = None, phone: Optional[str] = None,
                   needs_classification: Optional[bool] = None, limit: int = Query(50, le=200),
                   p: Principal = Depends(principal)):
        need(p, "calls:read", "agente", "qa")
        e164 = to_e164(phone) if phone else None
        with engine.begin() as conn:
            q = views.calls_query(p.tenant_id, conversation_id, contact_id, ticket_id, e164, needs_classification)
            return {"items": [views.call_view(conn, dict(x._mapping)) for x in conn.execute(q.limit(limit))]}

    @r.get(PREFIX + "/calls/{call_id}", tags=["chamadas"])
    def get_call(call_id: str, p: Principal = Depends(principal)):
        need(p, "calls:read", "agente", "qa")
        with engine.begin() as conn:
            c = _call_or_404(conn, p.tenant_id, call_id)
            return views.call_view(conn, c, full=True)

    def _call_or_404(conn, tenant_id: str, call_id: str) -> Dict[str, Any]:
        try:
            q = sa.select(m.calls).where(m.calls.c.tenant_id == tenant_id)
            q = q.where(m.calls.c.id == call_id) if len(call_id) == 36 else q.where(
                m.calls.c.root_provider_call_id == call_id)
            c = conn.execute(q).first()
        except Exception:  # noqa: BLE001
            c = None
        if c is None:
            raise ApiError("not_found", "chamada não encontrada", 404)
        c = dict(c._mapping)
        if c["state"] == "merged" and c["merged_into"]:
            c = dict(conn.execute(sa.select(m.calls).where(m.calls.c.id == c["merged_into"])).first()._mapping)
        return c

    # ============================================================== discagem
    @r.post(PREFIX + "/dial", tags=["cti"])
    def dial(body: DialIn, p: Principal = Depends(principal)):
        if p.kind == "user":
            need(p, "-", "agente", "supervisor", "admin")
        else:
            need(p, "dial:write")
        why = svc.dial.available()
        if why:
            return err("dial_disabled", why, 503)
        phone = (body.phone or "").strip()
        if not phone.startswith("+"):
            phone = to_e164(phone) or ""
        from .dial import E164
        if not E164.match(phone):
            return err("invalid_phone", "número inválido: use E.164 (+5511999990001)", 422)
        with engine.begin() as conn:
            apm = m.agent_phone_mappings
            q = sa.select(apm).where(apm.c.tenant_id == p.tenant_id, apm.c.active.is_(True))
            if p.kind == "user":
                q = q.where(sa.or_(apm.c.chatwoot_user_id == p.user_id, sa.func.lower(apm.c.agent_email) == (p.email or "").lower()))
            else:
                if not body.agent_email:
                    return err("agent_required", "informe agent_email", 422)
                q = q.where(sa.func.lower(apm.c.agent_email) == body.agent_email.lower())
            mp = conn.execute(q).first()
            if mp is None:
                return err("no_branch_mapping", "usuário sem ramal mapeado (admin: /admin/agent-phone-mappings)", 403)
            if body.ticket_id and tickets.get(conn, p.tenant_id, body.ticket_id) is None:
                return err("not_found", "ticket não encontrado", 404)
            uid = p.user_id or 0
            recent = conn.execute(sa.select(sa.func.count()).select_from(m.dial_requests).where(
                m.dial_requests.c.tenant_id == p.tenant_id, m.dial_requests.c.chatwoot_user_id == uid,
                m.dial_requests.c.status.in_(("pending", "accepted", "mock")),
                m.dial_requests.c.created_at > db.utcnow() - dt.timedelta(seconds=s.dial_pending_s))).scalar()
            if recent:
                return err("dial_pending", "há uma discagem em andamento; aguarde", 409)
            did = conn.execute(m.dial_requests.insert().values(
                tenant_id=p.tenant_id, chatwoot_user_id=uid, branch=mp.branch, pbx_email=mp.pbx_email or mp.agent_email,
                number_e164=phone, ticket_id=body.ticket_id, conversation_id=body.conversation_id,
                contact_id=body.contact_id, status="pending").returning(m.dial_requests.c.id)).scalar()
            pbx_email = mp.pbx_email or mp.agent_email
        res = svc.dial.dial(pbx_email, phone)
        with engine.begin() as conn:
            conn.execute(m.dial_requests.update().where(m.dial_requests.c.id == did).values(
                status=res.status, provider_http_status=res.http_status, provider_call_id=res.provider_call_id,
                message=res.message, finished_at=db.utcnow()))
            db.audit(conn, p.tenant_id, "dial.requested", "dial", did,
                     {"status": res.status, "http": res.http_status, "number": views.masked(phone)},
                     actor_type=p.kind, actor_id=str(p.user_id or p.service))
            if res.provider_call_id:
                # a chamada pode ter chegado pelo webhook antes da resposta da API
                conn.execute(m.calls.update().where(m.calls.c.tenant_id == p.tenant_id,
                                                    m.calls.c.root_provider_call_id == res.provider_call_id,
                                                    m.calls.c.dial_request_id.is_(None)).values(dial_request_id=did))
        out = {"dial_id": did, "status": res.status, "provider_call_id": res.provider_call_id,
               "provider_http_status": res.http_status, "message": res.message}
        if res.simulated:
            out["simulated"] = True
        code = 200 if res.status in ("accepted", "mock") else (503 if res.status == "disabled" else 502)
        return JSONResponse(out, status_code=code)

    @r.get(PREFIX + "/dial/{dial_id}", tags=["cti"])
    def get_dial(dial_id: str, p: Principal = Depends(principal)):
        need(p, "calls:read", "agente")
        with engine.begin() as conn:
            d = conn.execute(sa.select(m.dial_requests).where(m.dial_requests.c.tenant_id == p.tenant_id,
                                                              m.dial_requests.c.id == dial_id)).first()
            if d is None:
                raise ApiError("not_found", "discagem não encontrada", 404)
            call = conn.execute(sa.select(m.calls.c.id, m.calls.c.state, m.calls.c.outcome).where(
                m.calls.c.dial_request_id == dial_id)).first()
        return {"dial_id": d.id, "status": d.status, "provider_call_id": d.provider_call_id, "message": d.message,
                "created_at": db.iso(d.created_at), "call": dict(call._mapping) if call else None}

    # ============================================================== tickets
    def _t404(conn, p, ref):
        t = tickets.get(conn, p.tenant_id, ref)
        if t is None:
            raise ApiError("not_found", "ticket não encontrado", 404)
        return t

    @r.get(PREFIX + "/tickets", tags=["tickets"])
    def list_tickets(status: Optional[str] = None, protocolo: Optional[str] = None, contact_id: Optional[int] = None,
                     conversation_id: Optional[int] = None, assignee_id: Optional[int] = None,
                     limit: int = Query(50, le=200), p: Principal = Depends(principal)):
        need(p, "tickets:read", "agente", "qa")
        t = m.support_tickets
        q = sa.select(t).where(t.c.tenant_id == p.tenant_id, t.c.deleted_at.is_(None))
        if status:
            q = q.where(t.c.status.in_(status.split(",")))
        if protocolo:
            pr = protocolo.strip().upper()
            q = q.where(sa.or_(t.c.protocol == pr, t.c.protocol_numeric == pr))
        if contact_id:
            q = q.where(t.c.contact_id == contact_id)
        if assignee_id:
            q = q.where(t.c.assignee_id == assignee_id)
        if conversation_id:
            q = q.where(t.c.id.in_(sa.select(m.ticket_conversations.c.ticket_id).where(
                m.ticket_conversations.c.conversation_id == conversation_id)))
        with engine.begin() as conn:
            return {"items": [views.ticket_view(conn, dict(x._mapping)) for x in
                              conn.execute(q.order_by(t.c.updated_at.desc()).limit(limit))]}

    @r.post(PREFIX + "/tickets", tags=["tickets"], status_code=201)
    def create_ticket(body: TicketIn, request: Request, p: Principal = Depends(principal)):
        need(p, "tickets:write", "agente", "supervisor")
        k, replay = idem_get(request, p)
        if replay:
            return replay
        fields = body.model_dump(exclude={"conversation_id", "call_id"})
        if fields.get("contact_e164"):
            fields["contact_e164"] = to_e164(fields["contact_e164"]) or fields["contact_e164"]
        with engine.begin() as conn:
            if body.call_id:
                _call_or_404(conn, p.tenant_id, body.call_id)
            t = tickets.create(conn, p.tenant_id, fields, p.actor, call_id=body.call_id,
                               call_relation="origin", conversation_id=body.conversation_id)
            if body.call_id:
                conn.execute(m.calls.update().where(m.calls.c.id == body.call_id).values(
                    needs_classification=False, ticket_policy="manual:%s" % t["protocol"]))
            out = views.ticket_view(conn, t, full=True)
        return idem_put(k, p, request, 201, out)

    @r.get(PREFIX + "/tickets/{ref}", tags=["tickets"])
    def get_ticket(ref: str, p: Principal = Depends(principal)):
        need(p, "tickets:read", "agente", "qa")
        with engine.begin() as conn:
            return views.ticket_view(conn, _t404(conn, p, ref), full=True)

    @r.patch(PREFIX + "/tickets/{ref}", tags=["tickets"])
    def patch_ticket(ref: str, body: TicketPatch, p: Principal = Depends(principal)):
        need(p, "tickets:write", "agente", "supervisor")
        ch = body.model_dump(exclude_unset=True)
        ver = ch.pop("version", None)
        with engine.begin() as conn:
            t = tickets.update(conn, p.tenant_id, ref, ch, p.actor, expected_version=ver)
            return views.ticket_view(conn, t, full=True)

    def _roles(p: Principal) -> List[str]:
        roles = set(p.roles) | ({"admin", "supervisor"} if "admin" in p.roles else set())
        return sorted(roles | ({"tickets:close"} if "tickets:close" in p.scopes else set()))

    @r.post(PREFIX + "/tickets/{ref}/transitions", tags=["tickets"])
    def transition(ref: str, body: TransitionIn, request: Request, p: Principal = Depends(principal)):
        need(p, "tickets:write", "agente", "supervisor")
        k, replay = idem_get(request, p)
        if replay:
            return replay
        with engine.begin() as conn:
            t = tickets.transition(conn, p.tenant_id, ref, body.to, p.actor, body.reason or "", roles=_roles(p),
                                   approved_by=p.user_id if body.to == "encerrado" else None)
            out = views.ticket_view(conn, t, full=True)
        return idem_put(k, p, request, 200, out)

    @r.post(PREFIX + "/tickets/{ref}/escalate", tags=["tickets"])
    def escalate(ref: str, body: EscalateIn, p: Principal = Depends(principal)):
        need(p, "tickets:write", "agente", "supervisor")
        with engine.begin() as conn:
            t = tickets.escalate(conn, p.tenant_id, ref, p.actor, body.reason, body.priority, body.team_id, body.team_name)
            return views.ticket_view(conn, t, full=True)

    @r.post(PREFIX + "/tickets/{ref}/reopen", tags=["tickets"])
    def reopen(ref: str, body: TransitionIn = Body(default=None), p: Principal = Depends(principal)):
        need(p, "tickets:write", "agente", "supervisor")
        reason = (body.reason if body else "") or "reabertura"
        with engine.begin() as conn:
            t, new = tickets.reopen(conn, p.tenant_id, ref, p.actor, reason, roles=_roles(p))
            out = views.ticket_view(conn, t, full=True)
            out["followup_created"] = new
            return out

    @r.post(PREFIX + "/tickets/{ref}/notes", tags=["tickets"], status_code=201)
    def add_note(ref: str, body: NoteIn, p: Principal = Depends(principal)):
        need(p, "tickets:write", "agente", "supervisor")
        if body.kind not in ("registro", "disposicao", "nota_interna"):
            raise ApiError("invalid_kind", "kind deve ser registro, disposicao ou nota_interna", 422)
        if not body.body and not body.disposition:
            raise ApiError("empty", "informe body ou disposition", 422)
        with engine.begin() as conn:
            t = _t404(conn, p, ref)
            if body.call_id:
                _call_or_404(conn, p.tenant_id, body.call_id)
            a = tickets.add_activity(conn, t, body.kind, body.body, body.disposition, p.actor, p.name or p.service,
                                     body.call_id, mirror_to_chatwoot=body.post_to_chatwoot)
            db.audit(conn, p.tenant_id, "ticket.note_added", "ticket", t["id"], {"kind": body.kind},
                     actor_type=p.kind, actor_id=str(p.user_id or p.service))
        return JSONResponse({"id": a["id"], "kind": a["kind"], "created_at": db.iso(a["created_at"]),
                             "mirrored_to_chatwoot": body.post_to_chatwoot}, status_code=201)

    @r.post(PREFIX + "/tickets/{ref}/links", tags=["tickets"])
    def add_link(ref: str, body: LinkIn, p: Principal = Depends(principal)):
        need(p, "tickets:write", "agente", "supervisor")
        with engine.begin() as conn:
            t = _t404(conn, p, ref)
            if body.call_id:
                c = _call_or_404(conn, p.tenant_id, body.call_id)
                tickets.link_call(conn, t, c["id"], "related", p.actor)
                conn.execute(m.calls.update().where(m.calls.c.id == c["id"]).values(needs_classification=False))
                if c.get("conversation_id"):
                    tickets.link_conversation(conn, t, c["conversation_id"], p.actor)
            if body.conversation_id:
                tickets.link_conversation(conn, t, body.conversation_id, p.actor)
            return views.ticket_view(conn, t)

    @r.get(PREFIX + "/tickets/{ref}/events", tags=["tickets"])
    def ticket_events(ref: str, p: Principal = Depends(principal)):
        need(p, "tickets:read", "agente", "qa")
        with engine.begin() as conn:
            t = _t404(conn, p, ref)
            rows = conn.execute(sa.select(m.ticket_events).where(m.ticket_events.c.ticket_id == t["id"]).order_by(
                m.ticket_events.c.id)).fetchall()
            sl = conn.execute(sa.select(m.sla_events).where(m.sla_events.c.ticket_id == t["id"]).order_by(
                m.sla_events.c.id)).fetchall()
        return {"events": [{"id": e.id, "kind": e.kind, "from": e.from_status, "to": e.to_status, "field": e.field,
                            "old": e.old_value, "new": e.new_value, "reason": e.reason, "actor_type": e.actor_type,
                            "actor_id": e.actor_id, "at": db.iso(e.created_at)} for e in rows],
                "sla_events": [{"kind": e.kind, "at": db.iso(e.at), "data": e.data} for e in sl]}

    # ============================================================== retornos
    @r.get(PREFIX + "/callbacks", tags=["retornos"])
    def list_callbacks(status: str = "pending", limit: int = Query(100, le=200), p: Principal = Depends(principal)):
        need(p, "calls:read", "agente")
        cb = m.callback_tasks
        with engine.begin() as conn:
            rows = conn.execute(sa.select(cb).where(cb.c.tenant_id == p.tenant_id, cb.c.status.in_(status.split(",")))
                                .order_by(cb.c.due_at.nullslast()).limit(limit)).fetchall()
        return {"items": [{"id": x.id, "call_id": x.call_id, "ticket_id": x.ticket_id, "number_e164": x.number_e164,
                           "reason": x.reason, "status": x.status, "due_at": db.iso(x.due_at),
                           "assigned_to": x.assigned_to, "result": x.result} for x in rows]}

    @r.post(PREFIX + "/callbacks", tags=["retornos"], status_code=201)
    def create_callback(body: CallbackIn, request: Request, p: Principal = Depends(principal)):
        need(p, "callbacks:write", "agente", "supervisor")
        k, replay = idem_get(request, p)
        if replay:
            return replay
        num = to_e164(body.number_e164) if not body.number_e164.startswith("+") else body.number_e164
        with engine.begin() as conn:
            due = _when(body.due_at, sla.tenant_bh(conn, p.tenant_id).add(db.utcnow(), s.callback_due_min))
            cid = conn.execute(m.callback_tasks.insert().values(
                tenant_id=p.tenant_id, call_id=body.call_id, ticket_id=body.ticket_id, number_e164=num,
                reason=body.reason, status="pending", due_at=due, assigned_to=body.assigned_to)
                .returning(m.callback_tasks.c.id)).scalar()
            db.publish(conn, p.tenant_id, "callback.created", cid, {"callback_task_id": cid, "call_id": body.call_id,
                                                                    "ticket_id": body.ticket_id, "reason": body.reason,
                                                                    "due_at": db.iso(due)})
            db.audit(conn, p.tenant_id, "callback.created", "callback_task", cid, {"reason": body.reason},
                     actor_type=p.kind, actor_id=str(p.user_id or p.service))
        return idem_put(k, p, request, 201, {"id": cid, "status": "pending", "due_at": db.iso(due)})

    @r.patch(PREFIX + "/callbacks/{cb_id}", tags=["retornos"])
    def patch_callback(cb_id: str, body: CallbackPatch, p: Principal = Depends(principal)):
        need(p, "callbacks:write", "agente", "supervisor")
        if body.assigned_to is not None and p.kind == "user" and not p.has("supervisor"):
            raise ApiError("forbidden", "só supervisor atribui retornos", 403)
        with engine.begin() as conn:
            x = conn.execute(sa.select(m.callback_tasks).where(m.callback_tasks.c.tenant_id == p.tenant_id,
                                                               m.callback_tasks.c.id == cb_id).with_for_update()).first()
            if x is None:
                raise ApiError("not_found", "retorno não encontrado", 404)
            ch: Dict[str, Any] = {"updated_at": db.utcnow()}
            if body.status:
                if body.status not in ("done", "cancelled", "pending"):
                    raise ApiError("invalid_status", "status inválido", 422)
                ch["status"] = body.status
                if body.status == "done":
                    ch.update(completed_at=db.utcnow(), completed_by=p.user_id)
            if body.result is not None:
                ch["result"] = body.result
            if body.assigned_to is not None:
                ch["assigned_to"] = body.assigned_to
            conn.execute(m.callback_tasks.update().where(m.callback_tasks.c.id == cb_id).values(**ch))
            db.audit(conn, p.tenant_id, "callback.updated", "callback_task", cb_id,
                     {k: v for k, v in ch.items() if k != "updated_at"}, actor_type=p.kind,
                     actor_id=str(p.user_id or p.service))
        return {"id": cb_id, **{k: (db.iso(v) if isinstance(v, dt.datetime) else v) for k, v in ch.items()}}

    # ============================================================== gravações
    def _rec(conn, p, rid):
        rec = conn.execute(sa.select(m.call_recordings).where(m.call_recordings.c.tenant_id == p.tenant_id,
                                                              m.call_recordings.c.id == rid)).first()
        if rec is None:
            raise ApiError("not_found", "gravação não encontrada", 404)
        if not views.can_hear(conn, p, rec):
            raise ApiError("forbidden", "sem permissão para esta gravação", 403)
        return rec

    @r.get(PREFIX + "/recordings/{rid}", tags=["gravações"])
    def get_recording(rid: str, p: Principal = Depends(principal)):
        with engine.begin() as conn:
            rec = _rec(conn, p, rid)
        out = {"id": rec.id, "call_id": rec.call_id, "leg_id": rec.leg_id, "status": rec.status, "mime": rec.mime,
               "size_bytes": rec.size_bytes, "duration_s": rec.duration_s, "sha256": rec.sha256,
               "integrity": rec.integrity, "attempts": rec.attempts, "stored_at": db.iso(rec.stored_at),
               "last_error": rec.last_error if rec.status != "stored" else None}
        if p.kind == "service":
            out["storage_key"] = rec.storage_key
        return out

    @r.get(PREFIX + "/recordings/{rid}/url", tags=["gravações"])
    def recording_url(rid: str, request: Request, p: Principal = Depends(principal)):
        with engine.begin() as conn:
            rec = _rec(conn, p, rid)
            if rec.status != "stored":
                raise ApiError("not_available", "gravação ainda não disponível (%s)" % rec.status, 409)
            exp = int(time.time()) + s.recording_url_ttl_s
            claims = {"r": rec.id, "u": str(p.user_id or p.service), "t": p.tenant_id, "e": exp}
            raw = base64.urlsafe_b64encode(json.dumps(claims, separators=(",", ":")).encode()).decode().rstrip("=")
            sig = hmac.new(s.recording_url_secret.encode(), raw.encode(), "sha256").hexdigest()
            db.audit(conn, p.tenant_id, "recording.url_issued", "recording", rec.id, {"exp": exp},
                     actor_type=p.kind, actor_id=str(p.user_id or p.service), ip=_client_ip(request, s.bridge.trust_proxy))
        return {"url": "%s/recordings/stream/%s.%s" % (PREFIX, raw, sig),
                "expires_at": db.iso(dt.datetime.fromtimestamp(exp, dt.timezone.utc)), "expires_in": s.recording_url_ttl_s}

    @r.get(PREFIX + "/recordings/stream/{token}", tags=["gravações"])
    def recording_stream(token: str, request: Request):
        raw, _, sig = token.rpartition(".")
        good = hmac.new(s.recording_url_secret.encode(), raw.encode(), "sha256").hexdigest()
        if not raw or not hmac.compare_digest(sig, good):
            return err("invalid_token", "link inválido", 403)
        claims = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        if claims["e"] < time.time():
            return err("expired", "link expirado", 410)
        with engine.begin() as conn:
            rec = conn.execute(sa.select(m.call_recordings).where(m.call_recordings.c.id == claims["r"],
                                                                  m.call_recordings.c.tenant_id == claims["t"])).first()
            if rec is None or rec.status != "stored":
                return err("not_found", "gravação não encontrada", 404)
            rng_h = request.headers.get("range")
            if not rng_h or rng_h.startswith("bytes=0-"):
                db.audit(conn, claims["t"], "recording.accessed", "recording", rec.id, {"range": rng_h or "all"},
                         actor_type="user", actor_id=claims["u"], ip=_client_ip(request, s.bridge.trust_proxy))
        size = svc.storage.size(rec.storage_key)
        rg = parse_range(request.headers.get("range"), size)
        headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-store",
                   "Content-Disposition": 'inline; filename="gravacao-%s.%s"' % (rec.id[:8], (rec.storage_key or "x").rsplit(".", 1)[-1])}
        if rg:
            a, b = rg
            headers.update({"Content-Range": "bytes %d-%d/%d" % (a, b, size), "Content-Length": str(b - a + 1)})
            return StreamingResponse(svc.storage.iter_range(rec.storage_key, a, b), status_code=206,
                                     media_type=rec.mime, headers=headers)
        headers["Content-Length"] = str(size)
        return StreamingResponse(svc.storage.iter_range(rec.storage_key), media_type=rec.mime, headers=headers)

    # ============================================================== métricas / dashboards
    def _period(frm: Optional[str], to: Optional[str]):
        end = _when(to, db.utcnow())
        return _when(frm, end - dt.timedelta(days=7)), end

    @r.get(PREFIX + "/metrics/telephony", tags=["dashboards"])
    def m_tel(from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None, queue: Optional[str] = None,
              branch: Optional[str] = None, agent_email: Optional[str] = None, direction: Optional[str] = None,
              group_by: Optional[str] = None, detail: bool = False, p: Principal = Depends(principal)):
        need(p, "reports:read", "supervisor", "qa")
        a, b = _period(from_, to)
        with engine.begin() as conn:
            return reports.telephony(conn, p.tenant_id, a, b, s.sl_threshold_s, s.short_abandon_s,
                                     {"queue": queue, "branch": branch, "agent_email": agent_email,
                                      "direction": direction}, group_by, detail)

    @r.get(PREFIX + "/metrics/tickets", tags=["dashboards"])
    def m_tk(from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None, group_by: Optional[str] = None,
             detail: bool = False, p: Principal = Depends(principal)):
        need(p, "reports:read", "supervisor", "qa")
        a, b = _period(from_, to)
        with engine.begin() as conn:
            return reports.ticket_metrics(conn, p.tenant_id, a, b, group_by, detail)

    @r.get(PREFIX + "/reports/summary", tags=["dashboards"])
    def summary(from_: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
                p: Principal = Depends(principal)):
        need(p, "reports:read", "supervisor", "qa")
        a, b = _period(from_, to)
        with engine.begin() as conn:
            tel = reports.telephony(conn, p.tenant_id, a, b, s.sl_threshold_s, s.short_abandon_s, {})
            tk = reports.ticket_metrics(conn, p.tenant_id, a, b)
        return {"from": db.iso(a), "to": db.iso(b), "telefonia": tel["groups"]["total"], "retornos": tel["callbacks"],
                "tickets": tk}

    @r.get(PREFIX + "/sla/at-risk", tags=["dashboards"])
    def at_risk(within: int = 60, p: Principal = Depends(principal)):
        need(p, "tickets:read", "supervisor")
        now = db.utcnow()
        si, t = m.sla_instances, m.support_tickets
        with engine.begin() as conn:
            rows = conn.execute(sa.select(si.c.metric, si.c.due_at, si.c.breached, t.c.id, t.c.protocol, t.c.priority,
                                          t.c.assignee_id, t.c.team_name).join(t, t.c.id == si.c.ticket_id).where(
                si.c.tenant_id == p.tenant_id, si.c.status == "running",
                si.c.due_at <= now + dt.timedelta(minutes=within)).order_by(si.c.due_at)).fetchall()
        return {"items": [{"ticket_id": x.id, "protocol": x.protocol, "metric": x.metric, "due_at": db.iso(x.due_at),
                           "breached": bool(x.breached or x.due_at < now), "priority": x.priority,
                           "assignee_id": x.assignee_id, "team_name": x.team_name} for x in rows]}

    @r.post(PREFIX + "/reconciliations", tags=["operação"], status_code=202)
    def reconciliations(body: ReconcileIn, p: Principal = Depends(principal)):
        need(p, "reconcile:run", "admin")
        a, b = _when(body.from_, db.utcnow()), _when(body.to, db.utcnow())
        if b <= a or b - a > dt.timedelta(days=31):
            raise ApiError("invalid_period", "período inválido (máximo 31 dias)", 422)
        res = svc.worker.reconcile(p.tenant_id, a, b, "historical")
        with engine.begin() as conn:
            db.audit(conn, p.tenant_id, "reconciliation.requested", data={"from": db.iso(a), "to": db.iso(b), "result": res},
                     actor_type=p.kind, actor_id=str(p.user_id or p.service))
        return JSONResponse(res, status_code=202 if "error" not in res else 502)

    @r.post(PREFIX + "/notifications/log", tags=["operação"], status_code=201)
    def notif_log(body: NotificationLogIn, p: Principal = Depends(principal)):
        need(p, "notify:send", "admin")
        with engine.begin() as conn:
            db.audit(conn, p.tenant_id, "notification.%s" % body.status, "ticket" if body.ticket_id else "call",
                     body.ticket_id or body.call_id, body.model_dump(), actor_type=p.kind, actor_id=str(p.service or p.user_id))
        return JSONResponse({"ok": True}, status_code=201)

    # ============================================================== resultados do A3
    @r.post(PREFIX + "/analysis-results", tags=["qa"])
    def analysis(body: AnalysisIn, p: Principal = Depends(principal)):
        need(p, "analysis:write")
        if body.kind not in ("transcription", "summary", "qa") or body.status not in ("completed", "partial", "failed"):
            raise ApiError("invalid", "kind/status inválidos", 422)
        if body.score is not None and not 0 <= body.score <= 100:
            raise ApiError("invalid_score", "score fora de 0..100", 422)
        with engine.begin() as conn:
            call_id = body.call_id
            if body.recording_id:
                rec = conn.execute(sa.select(m.call_recordings).where(m.call_recordings.c.tenant_id == p.tenant_id,
                                                                      m.call_recordings.c.id == body.recording_id)).first()
                if rec is None:
                    raise ApiError("not_found", "gravação não encontrada", 404)
                call_id = call_id or rec.call_id
            if call_id:
                call_id = _call_or_404(conn, p.tenant_id, call_id)["id"]
            r0 = conn.execute(pg_insert(m.analysis_refs).values(
                tenant_id=p.tenant_id, kind=body.kind, external_id=body.external_id, status=body.status,
                call_id=call_id, recording_id=body.recording_id, score=body.score, data=body.data,
                completed_at=_when(body.completed_at, db.utcnow())).on_conflict_do_nothing().returning(
                m.analysis_refs.c.id)).first()
            if r0 is None:
                return {"duplicate": True}
            for t in (tickets.tickets_of_call(conn, call_id) if call_id else []):
                tickets.add_activity(conn, t, "analise", None, {"kind": body.kind, "status": body.status,
                                                                 "score": body.score, "external_id": body.external_id},
                                     p.actor, p.service, call_id, dedup_key="analise:%s:%s:%s" % (body.kind, body.external_id, t["id"]))
            db.audit(conn, p.tenant_id, "analysis.%s" % body.kind, "call", call_id,
                     {"status": body.status, "external_id": body.external_id}, actor_type="service", actor_id=p.service)
        return {"id": r0[0], "duplicate": False}

    # ============================================================== admin
    def admin(p: Principal):
        if not (p.kind == "user" and p.has("admin")):
            raise ApiError("forbidden", "só admin", 403)

    @r.get(PREFIX + "/admin/agent-phone-mappings", tags=["admin"])
    def get_maps(p: Principal = Depends(principal)):
        admin(p)
        with engine.begin() as conn:
            return {"items": [dict(x._mapping) for x in conn.execute(sa.select(
                m.agent_phone_mappings).where(m.agent_phone_mappings.c.tenant_id == p.tenant_id))]}

    @r.put(PREFIX + "/admin/agent-phone-mappings", tags=["admin"])
    def put_maps(items: List[MappingIn], p: Principal = Depends(principal)):
        admin(p)
        apm = m.agent_phone_mappings
        with engine.begin() as conn:
            for it in items:
                conn.execute(apm.update().where(apm.c.tenant_id == p.tenant_id, apm.c.branch == it.branch,
                                                apm.c.active.is_(True)).values(active=False, updated_at=db.utcnow()))
                if it.active:
                    conn.execute(apm.insert().values(tenant_id=p.tenant_id, **it.model_dump()))
            db.audit(conn, p.tenant_id, "admin.mappings_updated", data={"n": len(items)}, actor_type="user",
                     actor_id=str(p.user_id))
        return get_maps(p)

    @r.get(PREFIX + "/admin/ticket-open-rules", tags=["admin"])
    def get_rules(p: Principal = Depends(principal)):
        admin(p)
        with engine.begin() as conn:
            return {"items": [dict(x._mapping) for x in conn.execute(sa.select(m.ticket_open_rules).where(
                m.ticket_open_rules.c.tenant_id == p.tenant_id).order_by(m.ticket_open_rules.c.sort))]}

    @r.post(PREFIX + "/admin/ticket-open-rules", tags=["admin"], status_code=201)
    def add_rule(body: RuleIn, p: Principal = Depends(principal)):
        admin(p)
        if body.mode not in ("all", "answered", "missed", "none") or body.reuse not in ("reuse_open", "new", "ask"):
            raise ApiError("invalid_rule", "mode/reuse inválidos", 422)
        with engine.begin() as conn:
            rid = conn.execute(m.ticket_open_rules.insert().values(tenant_id=p.tenant_id, **body.model_dump())
                               .returning(m.ticket_open_rules.c.id)).scalar()
            db.audit(conn, p.tenant_id, "admin.rule_created", "ticket_open_rule", rid, body.model_dump(),
                     actor_type="user", actor_id=str(p.user_id))
        return JSONResponse({"id": rid}, status_code=201)

    @r.get(PREFIX + "/admin/user-roles", tags=["admin"])
    def get_roles(p: Principal = Depends(principal)):
        admin(p)
        with engine.begin() as conn:
            return {"items": [dict(x._mapping) for x in conn.execute(sa.select(m.user_roles).where(
                m.user_roles.c.tenant_id == p.tenant_id))]}

    @r.post(PREFIX + "/admin/user-roles", tags=["admin"], status_code=201)
    def add_role(body: RoleIn, p: Principal = Depends(principal)):
        admin(p)
        if body.role not in ("supervisor", "qa", "admin", "agente"):
            raise ApiError("invalid_role", "papel inválido", 422)
        with engine.begin() as conn:
            conn.execute(pg_insert(m.user_roles).values(tenant_id=p.tenant_id, chatwoot_user_id=body.chatwoot_user_id,
                                                        role=body.role, granted_by=p.user_id).on_conflict_do_nothing())
            db.audit(conn, p.tenant_id, "admin.role_granted", "user", body.chatwoot_user_id, {"role": body.role},
                     actor_type="user", actor_id=str(p.user_id))
        return JSONResponse({"ok": True}, status_code=201)

    @r.delete(PREFIX + "/admin/user-roles", tags=["admin"])
    def del_role(chatwoot_user_id: int, role: str, p: Principal = Depends(principal)):
        admin(p)
        with engine.begin() as conn:
            n = conn.execute(m.user_roles.delete().where(m.user_roles.c.tenant_id == p.tenant_id,
                                                         m.user_roles.c.chatwoot_user_id == chatwoot_user_id,
                                                         m.user_roles.c.role == role)).rowcount
            db.audit(conn, p.tenant_id, "admin.role_revoked", "user", chatwoot_user_id, {"role": role},
                     actor_type="user", actor_id=str(p.user_id))
        return {"removed": n}

    @r.get(PREFIX + "/admin/automation-routes", tags=["admin"])
    def get_routes(p: Principal = Depends(principal)):
        admin(p)
        with engine.begin() as conn:
            return {"items": [dict(x._mapping) for x in conn.execute(sa.select(m.automation_routes).where(
                sa.or_(m.automation_routes.c.tenant_id == p.tenant_id, m.automation_routes.c.tenant_id.is_(None))))]}

    @r.post(PREFIX + "/admin/automation-routes", tags=["admin"], status_code=201)
    def add_route(body: RouteIn, p: Principal = Depends(principal)):
        admin(p)
        if not body.url.startswith(("https://", "http://")):
            raise ApiError("invalid_url", "URL inválida", 422)
        with engine.begin() as conn:
            rid = conn.execute(m.automation_routes.insert().values(tenant_id=p.tenant_id, **body.model_dump())
                               .returning(m.automation_routes.c.id)).scalar()
            db.audit(conn, p.tenant_id, "admin.route_created", "automation_route", rid,
                     {"name": body.name, "types": body.event_types}, actor_type="user", actor_id=str(p.user_id))
        return JSONResponse({"id": rid}, status_code=201)

    @r.get(PREFIX + "/admin/dlq", tags=["admin"])
    def dlq(p: Principal = Depends(principal)):
        admin(p)
        with engine.begin() as conn:
            ib = conn.execute(sa.select(m.webhook_inbox.c.id, m.webhook_inbox.c.source, m.webhook_inbox.c.attempts,
                                        m.webhook_inbox.c.last_error, m.webhook_inbox.c.received_at).where(
                m.webhook_inbox.c.status == "dead", sa.or_(m.webhook_inbox.c.tenant_id == p.tenant_id,
                                                           m.webhook_inbox.c.tenant_id.is_(None))).limit(200)).fetchall()
            ob = conn.execute(sa.select(m.outbox.c.id, m.outbox.c.kind, m.outbox.c.attempts, m.outbox.c.last_error,
                                        m.outbox.c.created_at).where(
                m.outbox.c.status == "dead", m.outbox.c.tenant_id == p.tenant_id).limit(200)).fetchall()
        return {"inbox": [{**dict(x._mapping), "received_at": db.iso(x.received_at)} for x in ib],
                "outbox": [{**dict(x._mapping), "created_at": db.iso(x.created_at)} for x in ob]}

    @r.post(PREFIX + "/admin/dlq/{queue}/{item_id}/retry", tags=["admin"])
    def dlq_retry(queue: str, item_id: int, p: Principal = Depends(principal)):
        admin(p)
        tbl = {"inbox": m.webhook_inbox, "outbox": m.outbox}.get(queue)
        if tbl is None:
            raise ApiError("invalid_queue", "fila deve ser inbox ou outbox", 422)
        with engine.begin() as conn:
            n = conn.execute(tbl.update().where(tbl.c.id == item_id, tbl.c.status == "dead").values(
                status="pending", attempts=0, next_attempt_at=db.utcnow(), last_error=None)).rowcount
            db.audit(conn, p.tenant_id, "admin.dlq_retry", queue, item_id, {}, actor_type="user", actor_id=str(p.user_id))
        svc.worker.wake.set()
        return {"requeued": n}

    @r.delete(PREFIX + "/admin/sessions", tags=["admin"])
    def kill_sessions(user_id: int, p: Principal = Depends(principal)):
        admin(p)
        n = auth.revoke_user(p.tenant_id, user_id)
        with engine.begin() as conn:
            db.audit(conn, p.tenant_id, "admin.sessions_revoked", "user", user_id, {"n": n}, actor_type="user",
                     actor_id=str(p.user_id))
        return {"revoked": n}

    # ============================================================== webhooks recebidos
    def _account_by_secret(secret: str):
        with engine.begin() as conn:
            a = conn.execute(sa.select(m.integration_accounts).where(
                m.integration_accounts.c.webhook_secret_sha256 == db.sha256(secret),
                m.integration_accounts.c.active.is_(True))).first()
        if a is not None:
            return a.tenant_id, a
        if s.bridge.webhook_secret and hmac.compare_digest(secret.encode(), s.bridge.webhook_secret.encode()):
            return s.default_tenant, None
        return None, None

    async def pbx_webhook(secret: str, request: Request) -> JSONResponse:
        try:
            tenant_id, acc = _account_by_secret(secret)
        except sa.exc.OperationalError:
            # banco fora: 503 (nada foi aceito; o Report02 recupera o que a 55PBX não reenviar)
            obs.METRICS.inc("sdops_webhook_received_total", source="55pbx", result="db_unavailable")
            log.error("webhook recusado: banco indisponível")
            return err("unavailable", "temporariamente indisponível", 503)
        if tenant_id is None:
            obs.METRICS.inc("sdops_webhook_received_total", source="55pbx", result="bad_secret")
            return err("not_found", "not found", 404)
        ip = _client_ip(request, s.bridge.trust_proxy)
        allowed = list(acc.allowed_ips) if acc is not None and acc.allowed_ips else s.bridge.allowed_ips
        if not _ip_ok(ip, allowed):
            obs.METRICS.inc("sdops_webhook_received_total", source="55pbx", result="ip_forbidden")
            log.warning("webhook recusado: IP fora da lista (%s)", mask(ip))
            return err("forbidden", "forbidden", 403)
        if acc is not None and acc.webhook_token_ref:
            want = s.cred(acc.webhook_token_ref)
            got = request.headers.get("token", "")
            if not want or not hmac.compare_digest(got.encode(), want.encode()):
                obs.METRICS.inc("sdops_webhook_received_total", source="55pbx", result="bad_token")
                return err("unauthorized", "token inválido", 401)
        if not s.enabled:
            return err("disabled", "integração desativada (ENABLED=false)", 503)
        body = await _read_limited(request, s.bridge.max_body_bytes)
        if body is None:
            return err("too_large", "payload grande demais", 413)
        with obs.context(tenant=tenant_id):
            try:
                with engine.begin() as conn:
                    res = accept(conn, tenant_id, "webhook", body, request.headers.get("content-type", ""),
                                 {"ip": mask(ip), "method": request.method})
            except sa.exc.OperationalError:
                log.error("webhook recusado: banco indisponível")
                return err("unavailable", "temporariamente indisponível", 503)
            obs.METRICS.inc("sdops_webhook_received_total", source="55pbx",
                            result="duplicate" if res["duplicate"] else "accepted")
            svc.worker.wake.set()
            return JSONResponse({"accepted": True, "id": res["id"], "duplicate": res["duplicate"],
                                 "correlation_id": obs.correlation_id()}, status_code=200 if res["duplicate"] else 202)

    for path in ("/integracoes/55pbx/webhook/{secret}", PREFIX + "/webhooks/55pbx/{secret}"):
        r.add_api_route(path, pbx_webhook, methods=["POST", "PUT"], tags=["webhooks"], include_in_schema=True)

    async def chatwoot_webhook(secret: str, request: Request, legacy: bool) -> Response:
        tenant_id, _ = _account_by_secret(secret)
        if tenant_id is None:
            return err("not_found", "not found", 404)
        if not s.enabled:
            return err("disabled", "integração desativada (ENABLED=false)", 503)
        body = await _read_limited(request, 1024 * 1024)
        if body is None:
            return err("too_large", "payload grande demais", 413)
        from pbx_bridge.app import verify_chatwoot_signature
        if s.bridge.chatwoot_webhook_hmac_secret and not verify_chatwoot_signature(
                s.bridge.chatwoot_webhook_hmac_secret, body, request.headers.get("x-chatwoot-timestamp", ""),
                request.headers.get("x-chatwoot-signature", "")):
            return err("bad_signature", "assinatura inválida", 401)
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            return err("bad_json", "json inválido", 400)
        acc_id = (payload.get("account") or {}).get("id")
        with engine.begin() as conn:
            if acc_id:
                t2 = conn.execute(sa.select(m.tenants.c.id).where(m.tenants.c.chatwoot_account_id == int(acc_id))).scalar()
                if t2 is None:
                    return err("unknown_account", "conta sem tenant", 404)
                tenant_id = t2
            accept(conn, tenant_id, "chatwoot", body, "application/json")
        svc.worker.wake.set()
        return JSONResponse({"ok": True}) if legacy else Response(status_code=204)

    async def cw_legacy(secret: str, request: Request):
        return await chatwoot_webhook(secret, request, True)

    async def cw_new(secret: str, request: Request):
        return await chatwoot_webhook(secret, request, False)

    r.add_api_route("/integracoes/55pbx/servicedesk-events/{secret}", cw_legacy, methods=["POST"], tags=["webhooks"])
    r.add_api_route(PREFIX + "/webhooks/chatwoot/{secret}", cw_new, methods=["POST"], tags=["webhooks"])

    # ============================================================== URA / menu dinâmico
    def _ura_tenant(request: Request) -> Optional[str]:
        with engine.begin() as conn:
            accs = conn.execute(sa.select(m.integration_accounts).where(m.integration_accounts.c.active.is_(True))).fetchall()
        authz = request.headers.get("authorization", "")
        for a in accs:
            cfg = a.ura_auth or {}
            typ = cfg.get("type")
            if typ == "token":
                want = s.cred(cfg.get("ref"))
                got = request.headers.get(cfg.get("header") or "x-sd-ura-token", "")
                if want and got and hmac.compare_digest(got.encode(), want.encode()):
                    return a.tenant_id
            elif typ == "bearer" and authz.lower().startswith("bearer "):
                want = s.cred(cfg.get("ref"))
                if want and hmac.compare_digest(authz[7:].strip().encode(), want.encode()):
                    return a.tenant_id
            elif typ == "basic" and authz.lower().startswith("basic "):
                try:
                    user, _, pw = base64.b64decode(authz[6:].strip()).decode().partition(":")
                except Exception:  # noqa: BLE001
                    continue
                wu, wp = s.cred(cfg.get("user_ref")), s.cred(cfg.get("pass_ref"))
                if wu and wp and hmac.compare_digest(user.encode(), wu.encode()) and hmac.compare_digest(pw.encode(), wp.encode()):
                    return a.tenant_id
        return None

    async def ura_lookup(protocolo: str, request: Request):
        tenant_id = _ura_tenant(request)
        if tenant_id is None:
            return err("unauthorized", "credencial inválida", 401)
        ani = request.query_params.get("ani") or request.query_params.get("telefone")
        if request.method == "POST" and not ani:
            body = await _read_limited(request, 8192) or b""
            try:
                ani = (json.loads(body) or {}).get("ani") if body.strip().startswith(b"{") else None
            except ValueError:
                ani = None
            if not ani and body:
                from urllib.parse import parse_qs
                ani = (parse_qs(body.decode(errors="ignore")).get("ani") or [None])[0]
        ip = _client_ip(request, s.bridge.trust_proxy)
        key = "ura:%s:%s" % (tenant_id, to_e164(ani) if ani else ip)
        if not auth.limiter.allow(key, s.ura_rate_limit_per_min):
            return err("rate_limited", "muitas consultas", 429)
        num = "".join(ch for ch in protocolo if ch.isdigit())
        ref = num if num and len(num) == len(protocolo.strip()) else protocolo
        with engine.begin() as conn:
            t = None
            if num and len(num) == 11 and not tickets.luhn_ok(num):
                t = None
            else:
                t = tickets.get(conn, tenant_id, ref)
            caller = to_e164(ani) if ani else None
            verified = False
            if t is not None and caller:
                from pbx_bridge.normalize import mobile_variants
                verified = (t.get("contact_e164") or "") in mobile_variants(caller)
            db.audit(conn, tenant_id, "ura.lookup", "ticket", t["id"] if t else None,
                     {"protocolo": mask(protocolo), "found": t is not None, "verified": verified,
                      "ani": views.masked(caller)}, actor_type="provider", actor_id="55pbx-ura", ip=mask(ip))
        if t is None:
            return {"encontrado": "nao", "proxima_acao": "repetir"}
        if not verified and s.ura_require_caller_match:
            return {"encontrado": "sim", "verificado": "nao",
                    "situacao_fala": "localizado; para detalhes fale com um atendente", "proxima_acao": "transferir"}
        with engine.begin() as conn:
            fila = conn.execute(sa.select(m.calls.c.queue).join(m.ticket_calls, m.ticket_calls.c.call_id == m.calls.c.id)
                                .where(m.ticket_calls.c.ticket_id == t["id"], m.calls.c.queue.isnot(None))
                                .order_by(m.calls.c.started_at.desc()).limit(1)).scalar()
        return {"encontrado": "sim", "verificado": "sim", "protocolo": t["protocol"], "situacao": t["status"],
                "situacao_fala": tickets.SPOKEN[t["status"]], "proxima_acao": tickets.NEXT_ACTION[t["status"]],
                "fila": fila or ""}

    r.add_api_route(PREFIX + "/ura/tickets/{protocolo}", ura_lookup, methods=["GET", "POST"], tags=["ura"])
    return r
