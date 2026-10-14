"""Migrations (Alembic) e cadastro idempotente de tenant (horário, SLA, regras de abertura, credenciais)."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from . import db, sla
from . import models as m

HERE = os.path.dirname(os.path.abspath(__file__))


def alembic_config(url: str):
    from alembic.config import Config
    cfg = Config()
    cfg.set_main_option("script_location", os.path.join(HERE, "migrations"))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return cfg


def migrate(url: str, revision: str = "head") -> None:
    from alembic import command
    command.upgrade(alembic_config(url), revision)


def downgrade(url: str, revision: str) -> None:
    from alembic import command
    command.downgrade(alembic_config(url), revision)


DEFAULT_RULES = [
    {"name": "ligação interna: sem ticket", "sort": 10, "direction": "interno", "mode": "none", "reuse": "new"},
    {"name": "receptiva: toda chamada, reaproveita ticket aberto 24 h", "sort": 50, "direction": "receptivo",
     "mode": "all", "reuse": "reuse_open", "reuse_window_hours": 24},
    {"name": "ativa: toda chamada, reaproveita ticket aberto 24 h", "sort": 60, "direction": "ativo",
     "mode": "all", "reuse": "reuse_open", "reuse_window_hours": 24},
]


def seed_tenant(conn, tenant_id: str, name: str, chatwoot_account_id: int, pbx_inbox_id: Optional[int] = None,
                integration_user_id: Optional[int] = None, protocol_prefix: str = "SD",
                webhook_secret: Optional[str] = None, webhook_token_env: Optional[str] = None,
                chatwoot_token_env: Optional[str] = None, ura_auth: Optional[Dict[str, Any]] = None,
                settings: Optional[Dict[str, Any]] = None, rules: bool = True, policies: bool = True) -> Dict[str, Any]:
    bh = conn.execute(pg_insert(m.business_hours).values(
        name=sla.DEFAULT_BH_NAME, timezone="America/Sao_Paulo", schedule=sla.DEFAULT_SCHEDULE, holidays=[])
        .on_conflict_do_nothing(index_elements=["name"])).rowcount
    bh_id = conn.execute(sa.select(m.business_hours.c.id).where(m.business_hours.c.name == sla.DEFAULT_BH_NAME)).scalar()
    vals = dict(name=name, chatwoot_account_id=chatwoot_account_id, pbx_inbox_id=pbx_inbox_id,
                integration_user_id=integration_user_id, protocol_prefix=protocol_prefix, business_hours_id=bh_id,
                settings=settings or {}, updated_at=db.utcnow())
    conn.execute(pg_insert(m.tenants).values(id=tenant_id, **vals).on_conflict_do_update(
        index_elements=["id"], set_=vals))
    if chatwoot_token_env:
        conn.execute(pg_insert(m.integration_credentials_refs).values(
            tenant_id=tenant_id, name="chatwoot_api_token", env_var=chatwoot_token_env,
            description="token do usuário de integração no Chatwoot").on_conflict_do_update(
            index_elements=["tenant_id", "name"], set_={"env_var": chatwoot_token_env, "updated_at": db.utcnow()}))
    acc = conn.execute(sa.select(m.integration_accounts).where(m.integration_accounts.c.tenant_id == tenant_id,
                                                               m.integration_accounts.c.provider == "55pbx")).first()
    av = {"webhook_token_ref": webhook_token_env, "ura_auth": ura_auth or {}, "updated_at": db.utcnow()}
    if webhook_secret:
        av["webhook_secret_sha256"] = db.sha256(webhook_secret)
    if acc is None:
        conn.execute(m.integration_accounts.insert().values(tenant_id=tenant_id, provider="55pbx", **av))
    else:
        conn.execute(m.integration_accounts.update().where(m.integration_accounts.c.id == acc.id).values(**av))
    if rules and not conn.execute(sa.select(sa.func.count()).select_from(m.ticket_open_rules).where(
            m.ticket_open_rules.c.tenant_id == tenant_id)).scalar():
        for r in DEFAULT_RULES:
            conn.execute(m.ticket_open_rules.insert().values(tenant_id=tenant_id, **r))
    if policies and not conn.execute(sa.select(sa.func.count()).select_from(m.sla_policies).where(
            m.sla_policies.c.tenant_id == tenant_id)).scalar():
        for p in sla.DEFAULT_POLICIES:
            conn.execute(m.sla_policies.insert().values(tenant_id=tenant_id, business_hours_id=bh_id, **p))
    return {"tenant": tenant_id, "business_hours_id": bh_id}
