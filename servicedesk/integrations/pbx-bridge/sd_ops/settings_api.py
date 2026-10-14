"""API da tela "Telefonia 55PBX" (Configurações do Chatwoot): /sd-ops/api/v1/admin/settings.

- GET    /admin/settings                 configuração em vigor (segredos mascarados) + checklist D1–D4
- PUT    /admin/settings                 grava (segredo vazio = manter; null = apagar e voltar ao ambiente)
- POST   /admin/settings/test            testa conexão/autenticação (valores salvos ou os do corpo, sem gravar)
- POST   /admin/settings/webhook-secret  gera um segredo novo do webhook: a URL completa aparece UMA vez

Acesso: sessão do sd-ops criada com o token do próprio usuário (validado no GET /api/v1/profile real do Chatwoot,
CTI_AUTH.md) e role **administrator** na conta do tenant. Agente, supervisor/admin só do ops.user_roles e tokens de
serviço recebem 403. Toda gravação/teste vai para ops.audit_events com quem e o quê, nunca valores secretos.
"""
from __future__ import annotations

import datetime as dt
import re
import secrets as pysecrets
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Body, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field as PField

from . import db, sla
from . import models as m
from .settings_check import host_of, latest_recording, run_all
from .settings_store import (BY_KEY, FIELDS, SECTIONS, WEBHOOK_PATH, SettingsError, apply, clean, clean_secret,
                             current_value, mask)

PREFIX = "/sd-ops/api/v1"
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
DIRECTIONS = (None, "receptivo", "ativo", "interno")
PRIORITIES = (None, "urgente", "alta", "normal", "baixa")
# chaves internas em tenant_settings.values (não são campos da tela)
WH_LAST4, WH_AT, WH_PREV = "webhook_secret_last4", "webhook_secret_rotated_at", "webhook_secret_prev_sha256"


class MappingRow(BaseModel):
    branch: str = PField(..., description="Ramal 55PBX (máscara, ex. 5005)")
    agent_email: str = PField(..., description="E-mail do agente no Chatwoot")
    chatwoot_user_id: Optional[int] = None
    pbx_email: Optional[str] = PField(None, description="E-mail do ramal na 55PBX (API de discagem), se diferente")


class RuleRow(BaseModel):
    id: Optional[int] = None
    name: str
    sort: int = 100
    direction: Optional[str] = None
    queue_pattern: Optional[str] = None
    mode: str
    reuse: str
    reuse_window_hours: int = 24
    default_priority: str = "normal"
    active: bool = True


class BusinessHoursIn(BaseModel):
    timezone: str = "America/Sao_Paulo"
    schedule: Dict[str, List[List[str]]] = PField(..., description='{"0":[["09:00","18:00"]], ...} 0 = segunda')
    holidays: List[str] = PField(default_factory=list)


class SlaRow(BaseModel):
    id: Optional[int] = None
    name: str
    priority: Optional[str] = None
    first_response_min: Optional[int] = None
    resolution_min: Optional[int] = None
    sort: int = 100
    active: bool = True


class SettingsIn(BaseModel):
    version: Optional[int] = PField(None, description="Versão lida no GET (controle de concorrência); omitir = sobrescreve")
    values: Dict[str, Any] = PField(default_factory=dict, description="campo -> valor; null = volta ao ambiente")
    secrets: Dict[str, Optional[str]] = PField(
        default_factory=dict, description='campo -> novo valor; "" = manter; null = apagar (volta ao ambiente)')
    agent_mappings: Optional[List[MappingRow]] = PField(None, description="ramal -> agente (substitui o conjunto)")
    ticket_open_rules: Optional[List[RuleRow]] = None
    business_hours: Optional[BusinessHoursIn] = None
    sla_policies: Optional[List[SlaRow]] = None


def register(r: APIRouter, svc, principal, ApiError) -> None:
    s, engine, prov = svc.s, svc.engine, svc.settings

    def admin_only(p) -> None:
        if not p.account_admin:
            raise ApiError("forbidden", "só o administrador da conta pode ver ou alterar a configuração da 55PBX", 403)

    def fail(e: SettingsError):
        raise ApiError(e.code, e.message, e.http, e.extra)

    # ------------------------------------------------------------------ leitura
    def _base_url(values: Dict[str, Any], request: Optional[Request]) -> str:
        base = values.get("public_base_url") or s.public_url
        if not base and request is not None:
            proto = (request.headers.get("x-forwarded-proto") or request.url.scheme).split(",")[0].strip()
            host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()
            base = "%s://%s" % (proto, host) if host else ""
        return (base or "").rstrip("/")

    def _acc(conn, tenant_id: str):
        return conn.execute(sa.select(m.integration_accounts).where(
            m.integration_accounts.c.tenant_id == tenant_id, m.integration_accounts.c.provider == "55pbx")).first()

    def _webhook(conn, tenant_id: str, values: Dict[str, Any], request: Optional[Request]) -> Dict[str, Any]:
        acc = _acc(conn, tenant_id)
        out: Dict[str, Any] = {"defined": False, "last4": None, "source": "none", "rotated_at": values.get(WH_AT)}
        if values.get(WH_LAST4):
            out.update(defined=True, last4=values[WH_LAST4], source="panel")
        elif acc is not None and acc.webhook_secret_sha256:
            out.update(defined=True, source="seed")      # só o hash no banco (seed-tenant): valor não recuperável
        elif tenant_id == s.default_tenant and s.bridge.webhook_secret:
            out.update(mask(s.bridge.webhook_secret, "env"))
        base = _base_url(values, request)
        out["path_prefix"] = WEBHOOK_PATH
        out["url_masked"] = (base + WEBHOOK_PATH + "••••" + (out["last4"] or "")) if out["defined"] else None
        return out

    def _tables(conn, tenant_id: str) -> Dict[str, Any]:
        apm = m.agent_phone_mappings
        maps = [{"branch": x.branch, "agent_email": x.agent_email, "chatwoot_user_id": x.chatwoot_user_id,
                 "pbx_email": x.pbx_email} for x in conn.execute(sa.select(apm).where(
                     apm.c.tenant_id == tenant_id, apm.c.active.is_(True)).order_by(apm.c.branch))]
        rules = [{k: x._mapping[k] for k in ("id", "name", "sort", "direction", "queue_pattern", "mode", "reuse",
                                            "reuse_window_hours", "default_priority", "active")}
                 for x in conn.execute(sa.select(m.ticket_open_rules).where(
                     m.ticket_open_rules.c.tenant_id == tenant_id).order_by(m.ticket_open_rules.c.sort,
                                                                            m.ticket_open_rules.c.id))]
        bh = sla.tenant_bh(conn, tenant_id)
        pols = [{k: x._mapping[k] for k in ("id", "name", "priority", "first_response_min", "resolution_min", "sort",
                                           "active")}
                for x in conn.execute(sa.select(m.sla_policies).where(m.sla_policies.c.tenant_id == tenant_id)
                                      .order_by(m.sla_policies.c.sort, m.sla_policies.c.id))]
        return {"agent_mappings": maps, "ticket_open_rules": rules,
                "business_hours": {"timezone": bh.tz, "schedule": bh.schedule, "holidays": bh.holidays},
                "sla_policies": pols}

    def describe(tenant_id: str, request: Optional[Request] = None) -> Dict[str, Any]:
        with engine.begin() as conn:
            ten = conn.execute(sa.select(m.tenants).where(m.tenants.c.id == tenant_id)).first()
            row = prov.load(tenant_id, conn)
            values = (row or {}).get("values") or {}
            plain = (row or {}).get("secrets") or {}
            eff = apply(s, values, plain, (row or {}).get("version", 0)) if row else s
            acc = _acc(conn, tenant_id)
            ref = conn.execute(sa.select(m.integration_credentials_refs.c.env_var).where(
                m.integration_credentials_refs.c.tenant_id == tenant_id,
                m.integration_credentials_refs.c.name == "chatwoot_api_token")).scalar()
            webhook = _webhook(conn, tenant_id, values, request)
            tables = _tables(conn, tenant_id)
            last_rx = conn.execute(sa.select(sa.func.max(m.webhook_inbox.c.received_at)).where(
                m.webhook_inbox.c.tenant_id == tenant_id, m.webhook_inbox.c.source == "webhook")).scalar()
            stored = conn.execute(sa.select(sa.func.count()).select_from(m.call_recordings).where(
                m.call_recordings.c.tenant_id == tenant_id, m.call_recordings.c.status == "stored")).scalar()
            last_poll = db.kv_get(conn, "last_poll_ok_at:%s" % tenant_id)
        ura_env = (acc.ura_auth if acc is not None else None) or {}
        ura = prov.ura_config(tenant_id, ura_env)
        fields: Dict[str, Any] = {}
        for f in FIELDS:
            if f.key == "webhook_secret":
                continue
            in_panel = f.key in values or f.key in plain or f.key in ((row or {}).get("undecryptable") or [])
            if f.secret:
                if f.key == "chatwoot_api_token":
                    val = plain.get(f.key) or (s.cred(ref) if ref else "") or s.bridge.chatwoot_api_token
                    env_src = bool((s.cred(ref) if ref else "") or s.bridge.chatwoot_api_token)
                elif f.key == "webhook_token":
                    val = prov.webhook_token(tenant_id, acc.webhook_token_ref if acc is not None else None)
                    env_src = bool(acc is not None and acc.webhook_token_ref and s.cred(acc.webhook_token_ref))
                elif f.key in ("ura_token", "ura_password"):
                    val = ura["token" if f.key == "ura_token" else "password"]
                    env_src = bool(val) and f.key not in plain
                else:
                    val = current_value(eff, f) or ""
                    env_src = prov.env_source(f)
                d = mask(val, "panel" if f.key in plain else ("env" if env_src else "none"))
                if f.key in ((row or {}).get("undecryptable") or []):
                    d["error"] = "não foi possível decifrar (SDOPS_SETTINGS_KEY trocada?)"
            else:
                if f.section == "ura" and f.target.startswith("panel."):
                    val = ura.get({"ura_auth_type": "type", "ura_header": "header", "ura_user": "user"}[f.key])
                    src = "panel" if in_panel else ("env" if ura_env.get("type") else "default")
                    if f.key == "ura_auth_type" and not val:
                        val = f.default
                else:
                    val = current_value(eff, f)
                    src = "panel" if in_panel else ("env" if prov.env_source(f) else "default")
                d = {"value": val, "source": src}
            d.update(section=f.section, kind=f.kind, env=f.env or None)
            if f.choices:
                d["choices"] = [c for c in f.choices if c != "mock" or s.env == "dev"]
            fields[f.key] = d
        dial_ready = bool(eff.dial_client_code and eff.dial_api_key and eff.dial_jwt)
        checklist = [
            {"id": "D1", "done": bool(eff.bridge.pbx_api_key), "info": {"last_poll_ok_at": last_poll}},
            {"id": "D2", "done": bool(webhook["defined"] and last_rx),
             "info": {"secret_defined": webhook["defined"], "last_webhook_at": db.iso(last_rx)}},
            {"id": "D3", "done": bool(stored), "info": {"recordings_stored": int(stored or 0)}},
            {"id": "D4", "done": dial_ready and eff.dial_mode == "live",
             "info": {"credentials": dial_ready, "mode": eff.dial_mode}},
            {"id": "MAPS", "done": bool(tables["agent_mappings"]), "info": {"branches": len(tables["agent_mappings"])}},
            {"id": "ENABLED", "done": bool(eff.enabled), "info": {"force_disabled": s.force_disabled}},
        ]
        return {"tenant": {"id": ten.id, "name": ten.name, "chatwoot_account_id": ten.chatwoot_account_id,
                           "pbx_inbox_id": ten.pbx_inbox_id, "integration_user_id": ten.integration_user_id},
                "version": (row or {}).get("version", 0), "updated_at": db.iso((row or {}).get("updated_at")),
                "updated_by": {"id": (row or {}).get("updated_by"), "email": (row or {}).get("updated_by_email")},
                "vault": {"enabled": prov.vault.enabled, "error": prov.vault.error},
                "env": s.env, "force_disabled": s.force_disabled, "env_enabled": bool(s.bridge.enabled),
                "sections": list(SECTIONS), "fields": fields, "webhook": webhook, "checklist": checklist,
                "ura_ready": ura["ready"], **tables}

    # ------------------------------------------------------------------ gravação
    def _set_webhook(conn, tenant_id: str, secret: str, values: Dict[str, Any]) -> None:
        acc = _acc(conn, tenant_id)
        if WH_PREV not in values:
            values[WH_PREV] = acc.webhook_secret_sha256 if acc is not None else None
        h = db.sha256(secret)
        if acc is None:
            conn.execute(m.integration_accounts.insert().values(tenant_id=tenant_id, provider="55pbx",
                                                                webhook_secret_sha256=h))
        else:
            conn.execute(m.integration_accounts.update().where(m.integration_accounts.c.id == acc.id).values(
                webhook_secret_sha256=h, updated_at=db.utcnow()))
        values[WH_LAST4] = secret[-4:]
        values[WH_AT] = db.iso(db.utcnow())

    def _clear_webhook(conn, tenant_id: str, values: Dict[str, Any]) -> None:
        if WH_LAST4 not in values:
            return
        acc = _acc(conn, tenant_id)
        if acc is not None:
            conn.execute(m.integration_accounts.update().where(m.integration_accounts.c.id == acc.id).values(
                webhook_secret_sha256=values.get(WH_PREV), updated_at=db.utcnow()))
        for k in (WH_LAST4, WH_AT, WH_PREV):
            values.pop(k, None)

    def _save_tables(conn, tenant_id: str, body: SettingsIn, changed: List[str]) -> None:
        now = db.utcnow()
        if body.agent_mappings is not None:
            seen = set()
            for x in body.agent_mappings:
                b = x.branch.strip()
                if not re.match(r"^[0-9A-Za-z_-]{1,20}$", b):
                    raise ApiError("invalid_mapping", "ramal inválido: %s" % b[:20], 422)
                if b in seen:
                    raise ApiError("invalid_mapping", "ramal repetido: %s" % b, 422)
                seen.add(b)
                for e in (x.agent_email, x.pbx_email):
                    if e and not EMAIL.match(e.strip()):
                        raise ApiError("invalid_mapping", "e-mail inválido no ramal %s" % b, 422)
            apm = m.agent_phone_mappings
            conn.execute(apm.update().where(apm.c.tenant_id == tenant_id, apm.c.active.is_(True)).values(
                active=False, updated_at=now))
            for x in body.agent_mappings:
                conn.execute(apm.insert().values(tenant_id=tenant_id, branch=x.branch.strip(),
                                                 agent_email=x.agent_email.strip().lower(),
                                                 pbx_email=(x.pbx_email or "").strip().lower() or None,
                                                 chatwoot_user_id=x.chatwoot_user_id))
            changed.append("agent_mappings")
        if body.ticket_open_rules is not None:
            t = m.ticket_open_rules
            keep = []
            for x in body.ticket_open_rules:
                if x.mode not in ("all", "answered", "missed", "none") or x.reuse not in ("reuse_open", "new", "ask"):
                    raise ApiError("invalid_rule", "mode/reuse inválidos na regra %s" % x.name[:40], 422)
                if (x.direction or None) not in DIRECTIONS or x.default_priority not in PRIORITIES[1:]:
                    raise ApiError("invalid_rule", "direção/prioridade inválida na regra %s" % x.name[:40], 422)
                if not (0 <= x.reuse_window_hours <= 24 * 90):
                    raise ApiError("invalid_rule", "janela de reaproveitamento inválida", 422)
                vals = x.model_dump(exclude={"id"})
                vals["direction"] = vals["direction"] or None
                vals["queue_pattern"] = (vals["queue_pattern"] or "").strip() or None
                if x.id:
                    n = conn.execute(t.update().where(t.c.tenant_id == tenant_id, t.c.id == x.id).values(
                        updated_at=now, **vals)).rowcount
                    if not n:
                        raise ApiError("not_found", "regra %d não encontrada" % x.id, 404)
                    keep.append(x.id)
                else:
                    keep.append(conn.execute(t.insert().values(tenant_id=tenant_id, **vals).returning(t.c.id)).scalar())
            conn.execute(t.update().where(t.c.tenant_id == tenant_id, t.c.id.notin_(keep or [0])).values(
                active=False, updated_at=now))
            changed.append("ticket_open_rules")
        if body.business_hours is not None:
            bh = body.business_hours
            try:
                from zoneinfo import ZoneInfo
                ZoneInfo(bh.timezone)
            except Exception:  # noqa: BLE001
                raise ApiError("invalid_hours", "fuso horário inválido", 422)
            for day, wins in bh.schedule.items():
                if day not in [str(i) for i in range(7)]:
                    raise ApiError("invalid_hours", "dia inválido: %s (0 = segunda ... 6 = domingo)" % day, 422)
                for w in wins:
                    if len(w) != 2 or not all(HHMM.match(x or "") for x in w) or w[0] >= w[1]:
                        raise ApiError("invalid_hours", "intervalo inválido no dia %s" % day, 422)
            for h in bh.holidays:
                try:
                    dt.date.fromisoformat(h)
                except ValueError:
                    raise ApiError("invalid_hours", "feriado inválido: %s (AAAA-MM-DD)" % h[:20], 422)
            ten = conn.execute(sa.select(m.tenants.c.business_hours_id).where(m.tenants.c.id == tenant_id)).scalar()
            own = "tenant:%s" % tenant_id
            cur = conn.execute(sa.select(m.business_hours).where(m.business_hours.c.id == ten)).first() if ten else None
            vals = dict(timezone=bh.timezone, schedule=bh.schedule, holidays=sorted(set(bh.holidays)), updated_at=now)
            if cur is not None and cur.name == own:
                conn.execute(m.business_hours.update().where(m.business_hours.c.id == cur.id).values(**vals))
            else:
                # horário compartilhado ("Padrão B2B"): o tenant ganha o seu, e as políticas dele passam a usá-lo
                new_id = conn.execute(m.business_hours.insert().values(name=own, **vals)
                                      .returning(m.business_hours.c.id)).scalar()
                conn.execute(m.tenants.update().where(m.tenants.c.id == tenant_id).values(business_hours_id=new_id,
                                                                                         updated_at=now))
                conn.execute(m.sla_policies.update().where(
                    m.sla_policies.c.tenant_id == tenant_id,
                    sa.or_(m.sla_policies.c.business_hours_id == ten, m.sla_policies.c.business_hours_id.is_(None))
                    if ten else m.sla_policies.c.business_hours_id.is_(None)).values(business_hours_id=new_id))
            changed.append("business_hours")
        if body.sla_policies is not None:
            t = m.sla_policies
            for x in body.sla_policies:
                if x.priority not in PRIORITIES:
                    raise ApiError("invalid_sla", "prioridade inválida na política %s" % x.name[:40], 422)
                for v in (x.first_response_min, x.resolution_min):
                    if v is not None and not (1 <= v <= 60 * 24 * 90):
                        raise ApiError("invalid_sla", "prazo inválido na política %s" % x.name[:40], 422)
                vals = x.model_dump(exclude={"id"})
                if x.id:
                    if not conn.execute(t.update().where(t.c.tenant_id == tenant_id, t.c.id == x.id).values(
                            updated_at=now, **vals)).rowcount:
                        raise ApiError("not_found", "política %d não encontrada" % x.id, 404)
                else:
                    bh_id = conn.execute(sa.select(m.tenants.c.business_hours_id).where(m.tenants.c.id == tenant_id)).scalar()
                    conn.execute(t.insert().values(tenant_id=tenant_id, business_hours_id=bh_id, **vals))
            changed.append("sla_policies")

    def _store(conn, tenant_id: str, cur, values: Dict[str, Any], enc: Dict[str, str], p) -> int:
        ver = (cur.version if cur is not None else 0) + 1
        vals = {"values": values, "secrets": enc, "version": ver, "updated_by": p.user_id, "updated_by_email": p.email,
                "updated_at": db.utcnow()}
        if cur is None:
            conn.execute(m.tenant_settings.insert().values(tenant_id=tenant_id, **vals))
        else:
            conn.execute(m.tenant_settings.update().where(m.tenant_settings.c.tenant_id == tenant_id).values(**vals))
        return ver

    def _enable_problems(conn, tenant_id: str, values, plain, enc) -> List[str]:
        eff = apply(s, values, plain, 0)
        if not eff.enabled:
            return []
        probs = []
        ref = conn.execute(sa.select(m.integration_credentials_refs.c.env_var).where(
            m.integration_credentials_refs.c.tenant_id == tenant_id,
            m.integration_credentials_refs.c.name == "chatwoot_api_token")).scalar()
        if not (plain.get("chatwoot_api_token") or (s.cred(ref) if ref else "") or s.bridge.chatwoot_api_token):
            probs.append("token do usuário de integração do Chatwoot")
        acc = _acc(conn, tenant_id)
        if not ((acc is not None and acc.webhook_secret_sha256) or values.get(WH_LAST4)
                or (tenant_id == s.default_tenant and s.bridge.webhook_secret)):
            probs.append("segredo do webhook (gere um novo)")
        return probs

    @r.get(PREFIX + "/admin/settings", tags=["admin"])
    def get_settings(request: Request, p=Depends(principal)):
        admin_only(p)
        return describe(p.tenant_id, request)

    @r.put(PREFIX + "/admin/settings", tags=["admin"])
    def put_settings(request: Request, body: SettingsIn = Body(...), p=Depends(principal)):
        admin_only(p)
        tid = p.tenant_id
        changed: List[str] = []
        set_s: List[str] = []
        cleared: List[str] = []
        with engine.begin() as conn:
            cur = conn.execute(sa.select(m.tenant_settings).where(m.tenant_settings.c.tenant_id == tid)
                               .with_for_update()).first()
            if body.version is not None and (cur.version if cur is not None else 0) != body.version:
                raise ApiError("conflict", "a configuração foi alterada por outra pessoa; recarregue a página", 409,
                               {"current_version": cur.version if cur is not None else 0})
            values = dict(cur.values or {}) if cur is not None else {}
            enc = dict(cur.secrets or {}) if cur is not None else {}
            plain = (prov.load(tid, conn) or {}).get("secrets", {}) if cur is not None else {}
            errors: Dict[str, str] = {}
            for k, v in body.values.items():
                f = BY_KEY.get(k)
                if f is None or f.secret:
                    errors[k] = "campo desconhecido" if f is None else "segredo deve ir em 'secrets'"
                    continue
                if v is None:
                    if k in values:
                        values.pop(k)
                        changed.append(k)
                    continue
                try:
                    nv = clean(f, v, s.env)
                except ValueError as e:
                    errors[k] = str(e)
                    continue
                if values.get(k) != nv:
                    values[k] = nv
                    changed.append(k)
            new_plain: Dict[str, str] = {}
            for k, v in body.secrets.items():
                f = BY_KEY.get(k)
                if f is None or not f.secret:
                    errors[k] = "campo desconhecido" if f is None else "não é segredo: use 'values'"
                    continue
                if v is None:
                    if k == "webhook_secret":
                        if WH_LAST4 in values:
                            _clear_webhook(conn, tid, values)
                            cleared.append(k)
                    elif k in enc:
                        enc.pop(k)
                        plain.pop(k, None)
                        cleared.append(k)
                    continue
                if v == "":
                    continue                              # vazio = manter o atual
                try:
                    new_plain[k] = clean_secret(f, v)
                except ValueError as e:
                    errors[k] = str(e)
            if errors:
                raise ApiError("validation", "há campos inválidos", 422, {"fields": errors})
            for k, v in new_plain.items():
                if k == "webhook_secret":
                    _set_webhook(conn, tid, v, values)
                else:
                    try:
                        enc[k] = prov.vault.encrypt(v)
                    except SettingsError as e:
                        fail(e)
                    plain[k] = v
                set_s.append(k)
            _save_tables(conn, tid, body, changed)
            probs = _enable_problems(conn, tid, values, plain, enc)
            if probs:
                raise ApiError("enable_blocked", "para ativar, falta: " + "; ".join(probs), 422, {"missing": probs})
            if not (changed or set_s or cleared):
                return describe(tid, request)
            ver = _store(conn, tid, cur, values, enc, p)
            db.audit(conn, tid, "admin.settings_updated", "tenant_settings", tid,
                     {"version": ver, "changed": sorted(set(changed)), "secrets_set": sorted(set_s),
                      "secrets_cleared": sorted(set(cleared))}, actor_type="user", actor_id=str(p.user_id))
        prov.invalidate(tid)
        return describe(tid, request)

    @r.post(PREFIX + "/admin/settings/webhook-secret", tags=["admin"])
    def rotate_webhook(request: Request, p=Depends(principal)):
        """Gera um segredo novo do "Tempo real por URL". A URL completa aparece SÓ nesta resposta (no banco fica o
        SHA-256, como no seed-tenant); o segredo anterior deixa de ser aceito na hora."""
        admin_only(p)
        tid = p.tenant_id
        secret = pysecrets.token_hex(32)
        with engine.begin() as conn:
            cur = conn.execute(sa.select(m.tenant_settings).where(m.tenant_settings.c.tenant_id == tid)
                               .with_for_update()).first()
            values = dict(cur.values or {}) if cur is not None else {}
            enc = dict(cur.secrets or {}) if cur is not None else {}
            _set_webhook(conn, tid, secret, values)
            ver = _store(conn, tid, cur, values, enc, p)
            db.audit(conn, tid, "admin.settings_webhook_rotated", "tenant_settings", tid, {"version": ver},
                     actor_type="user", actor_id=str(p.user_id))
        prov.invalidate(tid)
        url = _base_url(values, request) + WEBHOOK_PATH + secret
        return JSONResponse({"url": url, "last4": secret[-4:], "version": ver, "shown_once": True},
                            headers={"Cache-Control": "no-store"})

    @r.post(PREFIX + "/admin/settings/test", tags=["admin"])
    def test_settings(request: Request, body: Optional[SettingsIn] = Body(None), p=Depends(principal)):
        """Testa com os valores salvos ou, se vierem no corpo, com os valores ainda não salvos (nada é gravado)."""
        admin_only(p)
        tid = p.tenant_id
        with engine.begin() as conn:
            row = prov.load(tid, conn) or {}
            values = dict(row.get("values") or {})
            plain = dict(row.get("secrets") or {})
            errors: Dict[str, str] = {}
            for k, v in ((body.values if body else {}) or {}).items():
                f = BY_KEY.get(k)
                if f is None or f.secret:
                    continue
                try:
                    if v is None:
                        values.pop(k, None)
                    else:
                        values[k] = clean(f, v, s.env)
                except ValueError as e:
                    errors[k] = str(e)
            for k, v in ((body.secrets if body else {}) or {}).items():
                f = BY_KEY.get(k)
                if f is not None and f.secret and v and k != "webhook_secret":
                    plain[k] = v.strip()
            if errors:
                raise ApiError("validation", "há campos inválidos", 422, {"fields": errors})
            cfg = apply(s, values, plain, row.get("version", 0))
            acc = _acc(conn, tid)
            ref = conn.execute(sa.select(m.integration_credentials_refs.c.env_var).where(
                m.integration_credentials_refs.c.tenant_id == tid,
                m.integration_credentials_refs.c.name == "chatwoot_api_token")).scalar()
            sample = latest_recording(conn, tid)
            webhook = _webhook(conn, tid, values, request)
        token = plain.get("chatwoot_api_token") or (s.cred(ref) if ref else "") or s.bridge.chatwoot_api_token
        ura_env = (acc.ura_auth if acc is not None else None) or {}
        ura = prov.ura_config(tid, ura_env)
        if body and any(k.startswith("ura_") for k in list(body.values) + list(body.secrets)):
            ura = dict(ura, type=values.get("ura_auth_type") or ura["type"],
                       token=plain.get("ura_token") or ura["token"], user=values.get("ura_user") or ura["user"],
                       password=plain.get("ura_password") or ura["password"])
            ura["ready"] = bool(ura["type"]) and (bool(ura["token"]) if ura["type"] in ("token", "bearer")
                                                  else bool(ura["user"] and ura["password"]))
        host = values.get("recordings_host") or host_of(sample) or BY_KEY["recordings_host"].default
        items = run_all(svc.tester, cfg, chatwoot_token=token, secret_defined=webhook["defined"], ura=ura,
                        recordings_host=host, sample_url=sample)
        with engine.begin() as conn:
            db.audit(conn, tid, "admin.settings_tested", "tenant_settings", tid,
                     {"results": {x["id"]: x["status"] for x in items}, "unsaved": bool(body)},
                     actor_type="user", actor_id=str(p.user_id))
        return {"tested_at": db.iso(db.utcnow()), "items": items}
