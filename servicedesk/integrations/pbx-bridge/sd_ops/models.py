"""Modelo de dados do sd-ops (Postgres, banco servicedesk_ops, schema ops).

Tudo em UTC (timestamptz). Toda tabela de negócio tem tenant_id. IDs externos (Chatwoot, 55PBX) em colunas
próprias com índices únicos onde há idempotência. As migrations ficam em sd_ops/migrations (Alembic).
"""
from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

SCHEMA = "ops"
metadata = sa.MetaData(schema=SCHEMA, naming_convention={
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
})

TS = sa.TIMESTAMP(timezone=True)
NOW = sa.text("now()")
EMPTY_OBJ = sa.text("'{}'::jsonb")
EMPTY_ARR = sa.text("'[]'::jsonb")


def uuid_pk():
    return sa.Column("id", UUID(as_uuid=False), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def tenant_fk(nullable=False):
    return sa.Column("tenant_id", sa.Text, sa.ForeignKey("ops.tenants.id"), nullable=nullable, index=True)


def stamps():
    return [sa.Column("created_at", TS, nullable=False, server_default=NOW),
            sa.Column("updated_at", TS, nullable=False, server_default=NOW)]


# ------------------------------------------------------------------ tenants e integração
business_hours = sa.Table(
    "business_hours", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("name", sa.Text, nullable=False, unique=True),
    sa.Column("timezone", sa.Text, nullable=False),
    # {"0":[["09:00","18:00"]], ... "4":[...]} 0=segunda (datetime.weekday)
    sa.Column("schedule", JSONB, nullable=False),
    sa.Column("holidays", JSONB, nullable=False, server_default=EMPTY_ARR),  # ["2026-11-02", ...]
    *stamps(),
)

tenants = sa.Table(
    "tenants", metadata,
    sa.Column("id", sa.Text, primary_key=True),  # slug: b2b, dev55
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("chatwoot_account_id", sa.Integer, nullable=False, unique=True),
    sa.Column("pbx_inbox_id", sa.Integer),
    sa.Column("integration_user_id", sa.Integer),
    sa.Column("protocol_prefix", sa.Text, nullable=False, server_default="SD"),
    sa.Column("business_hours_id", sa.Integer, sa.ForeignKey("ops.business_hours.id")),
    sa.Column("settings", JSONB, nullable=False, server_default=EMPTY_OBJ),  # sobreposições da config da ponte
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    *stamps(),
)

integration_credentials_refs = sa.Table(
    "integration_credentials_refs", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    tenant_fk(),
    sa.Column("name", sa.Text, nullable=False),     # chatwoot_api_token, pbx_dial_api_key, ...
    sa.Column("env_var", sa.Text, nullable=False),  # o VALOR nunca fica no banco
    sa.Column("description", sa.Text),
    sa.Column("rotated_at", TS),
    *stamps(),
    sa.UniqueConstraint("tenant_id", "name"),
)

integration_accounts = sa.Table(
    "integration_accounts", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    tenant_fk(),
    sa.Column("provider", sa.Text, nullable=False, server_default="55pbx"),
    sa.Column("central_id", sa.Text),
    sa.Column("webhook_secret_sha256", sa.Text, unique=True),
    sa.Column("webhook_token_ref", sa.Text),        # nome da credencial do header "token" (opcional)
    sa.Column("allowed_ips", JSONB, nullable=False, server_default=EMPTY_ARR),
    sa.Column("ura_auth", JSONB, nullable=False, server_default=EMPTY_OBJ),  # {"type":"token","header":"token","ref":"..."}
    sa.Column("config", JSONB, nullable=False, server_default=EMPTY_OBJ),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    *stamps(),
)

agent_phone_mappings = sa.Table(
    "agent_phone_mappings", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    tenant_fk(),
    sa.Column("branch", sa.Text, nullable=False),        # ramal 55PBX
    sa.Column("pbx_email", sa.Text),                      # e-mail do ramal na 55PBX (API de discagem)
    sa.Column("agent_email", sa.Text, nullable=False),    # e-mail do agente no Chatwoot
    sa.Column("chatwoot_user_id", sa.Integer),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    *stamps(),
    sa.Index("uq_agent_phone_mappings_active_branch", "tenant_id", "branch", unique=True,
             postgresql_where=sa.text("active")),
    sa.Index("ix_agent_phone_mappings_user", "tenant_id", "chatwoot_user_id"),
)

user_roles = sa.Table(
    "user_roles", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    tenant_fk(),
    sa.Column("chatwoot_user_id", sa.Integer, nullable=False),
    sa.Column("role", sa.Text, nullable=False),
    sa.Column("granted_by", sa.Integer),
    sa.Column("created_at", TS, nullable=False, server_default=NOW),
    sa.UniqueConstraint("tenant_id", "chatwoot_user_id", "role"),
    sa.CheckConstraint("role in ('supervisor','qa','admin','agente')", name="role"),
)

cti_sessions = sa.Table(
    "cti_sessions", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("token_sha256", sa.Text, nullable=False, unique=True),
    sa.Column("csrf_sha256", sa.Text, nullable=False),
    tenant_fk(),
    sa.Column("chatwoot_user_id", sa.Integer, nullable=False),
    sa.Column("email", sa.Text),
    sa.Column("name", sa.Text),
    sa.Column("roles", JSONB, nullable=False),
    sa.Column("ip", sa.Text),
    sa.Column("created_at", TS, nullable=False, server_default=NOW),
    sa.Column("last_seen_at", TS, nullable=False, server_default=NOW),
    sa.Column("expires_at", TS, nullable=False),
    sa.Column("revoked_at", TS),
)

# ------------------------------------------------------------------ inbox / outbox
webhook_inbox = sa.Table(
    "webhook_inbox", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(nullable=True),
    sa.Column("source", sa.Text, nullable=False),          # webhook | report02 | manual
    sa.Column("provider", sa.Text, nullable=False, server_default="55pbx"),
    sa.Column("received_at", TS, nullable=False, server_default=NOW),
    sa.Column("content_type", sa.Text),
    sa.Column("headers", JSONB, nullable=False, server_default=EMPTY_OBJ),  # subconjunto sem segredos
    sa.Column("raw", sa.Text),                              # payload bruto (acesso restrito; apagado na retenção)
    sa.Column("body_sha256", sa.Text, nullable=False),
    sa.Column("dedup_key", sa.Text, nullable=False, unique=True),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),  # pending|processing|done|unparsed|dead
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("next_attempt_at", TS, nullable=False, server_default=NOW),
    sa.Column("locked_until", TS),
    sa.Column("last_error", sa.Text),
    sa.Column("result", JSONB),
    sa.Column("processed_at", TS),
    sa.Column("raw_purged_at", TS),
    sa.Column("correlation_id", sa.Text),
    sa.Index("ix_webhook_inbox_due", "status", "next_attempt_at"),
)

outbox = sa.Table(
    "outbox", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(),
    sa.Column("kind", sa.Text, nullable=False),            # stream | chatwoot.sync_call | chatwoot.sync_ticket | recording.fetch
    sa.Column("ordering_key", sa.Text),                    # mesma chave = ordem FIFO garantida
    sa.Column("dedup_key", sa.Text, nullable=False, unique=True),
    sa.Column("payload", JSONB, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),  # pending|processing|done|dead
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("next_attempt_at", TS, nullable=False, server_default=NOW),
    sa.Column("locked_until", TS),
    sa.Column("last_error", sa.Text),
    sa.Column("created_at", TS, nullable=False, server_default=NOW),
    sa.Column("processed_at", TS),
    sa.Column("correlation_id", sa.Text),
    sa.Index("ix_outbox_due", "status", "next_attempt_at"),
    sa.Index("ix_outbox_ordering", "ordering_key", "id"),
)

# ------------------------------------------------------------------ chamadas
calls = sa.Table(
    "calls", metadata,
    uuid_pk(),
    tenant_fk(),
    sa.Column("root_provider_call_id", sa.Text, nullable=False),
    sa.Column("direction", sa.Text),                       # receptivo | ativo | interno | sms
    sa.Column("state", sa.Text, nullable=False, server_default="active"),  # active | ended | merged
    sa.Column("outcome", sa.Text),                         # answered | missed | abandoned_ura | abandoned_queue | rejected | dropped | after_hours | failed | unknown
    sa.Column("status_raw", sa.Text),
    sa.Column("number_e164", sa.Text),
    sa.Column("central_id", sa.Text),
    sa.Column("contact_id", sa.Integer),
    sa.Column("conversation_id", sa.Integer),
    sa.Column("queue", sa.Text),
    sa.Column("ura", sa.Text),
    sa.Column("branch", sa.Text),
    sa.Column("agent_email", sa.Text),
    sa.Column("started_at", TS),
    sa.Column("answered_at", TS),
    sa.Column("ended_at", TS),
    sa.Column("talk_s", sa.Integer),
    sa.Column("wait_s", sa.Integer),
    sa.Column("total_s", sa.Integer),
    sa.Column("disconnection", sa.Text),
    sa.Column("legs_count", sa.Integer, nullable=False, server_default="1"),
    sa.Column("merged_into", UUID(as_uuid=False)),
    sa.Column("needs_classification", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("ticket_policy", sa.Text),                   # decisão aplicada (auditoria)
    sa.Column("dial_request_id", UUID(as_uuid=False)),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    sa.Column("data", JSONB, nullable=False, server_default=EMPTY_OBJ),
    *stamps(),
    sa.Index("ix_calls_tenant_number", "tenant_id", "number_e164"),
    sa.Index("ix_calls_tenant_started", "tenant_id", "started_at"),
    sa.Index("ix_calls_tenant_conversation", "tenant_id", "conversation_id"),
    sa.Index("ix_calls_tenant_contact", "tenant_id", "contact_id"),
)

call_legs = sa.Table(
    "call_legs", metadata,
    uuid_pk(),
    tenant_fk(),
    sa.Column("call_id", UUID(as_uuid=False), sa.ForeignKey("ops.calls.id"), nullable=False, index=True),
    sa.Column("seq", sa.Integer, nullable=False),
    sa.Column("provider_call_id", sa.Text, nullable=False),
    sa.Column("state", sa.Text, nullable=False),            # pending | started | ended | transferred
    sa.Column("direction", sa.Text),
    sa.Column("branch", sa.Text),
    sa.Column("agent_email", sa.Text),
    sa.Column("agent_name", sa.Text),
    sa.Column("queue", sa.Text),
    sa.Column("ura", sa.Text),
    sa.Column("started_at", TS),
    sa.Column("answered_at", TS),
    sa.Column("ended_at", TS),
    sa.Column("talk_s", sa.Integer),
    sa.Column("wait_s", sa.Integer),
    sa.Column("total_s", sa.Integer),
    sa.Column("disconnection", sa.Text),
    sa.Column("status_raw", sa.Text),
    sa.Column("has_audio_url", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("transferred_from_leg_id", UUID(as_uuid=False)),
    sa.Column("transfer_to_provider_call_id", sa.Text),
    sa.Column("data", JSONB, nullable=False, server_default=EMPTY_OBJ),  # dados normalizados (sem payload bruto)
    *stamps(),
    sa.UniqueConstraint("tenant_id", "provider_call_id"),
)

call_events = sa.Table(
    "call_events", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(),
    sa.Column("call_id", UUID(as_uuid=False), index=True),
    sa.Column("leg_id", UUID(as_uuid=False)),
    sa.Column("inbox_id", sa.BigInteger),
    sa.Column("provider_call_id", sa.Text, nullable=False),
    sa.Column("kind", sa.Text, nullable=False),            # start | end | transfer | report
    sa.Column("rank", sa.Integer, nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("dedup_key", sa.Text, nullable=False, unique=True),
    sa.Column("occurred_at", TS),
    sa.Column("received_at", TS, nullable=False, server_default=NOW),
    sa.Column("normalized", JSONB, nullable=False),
    sa.Column("anomalies", JSONB, nullable=False, server_default=EMPTY_ARR),
    sa.Index("ix_call_events_leg", "tenant_id", "provider_call_id", "rank", "id"),
)

call_recordings = sa.Table(
    "call_recordings", metadata,
    uuid_pk(),
    tenant_fk(),
    sa.Column("call_id", UUID(as_uuid=False), sa.ForeignKey("ops.calls.id"), nullable=False, index=True),
    sa.Column("leg_id", UUID(as_uuid=False), sa.ForeignKey("ops.call_legs.id"), nullable=False, unique=True),
    sa.Column("source_url", sa.Text),                       # URL da 55PBX: NUNCA exposta pela API
    sa.Column("source_host", sa.Text),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),  # pending | stored | failed
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("next_attempt_at", TS),
    sa.Column("last_error", sa.Text),
    sa.Column("storage_backend", sa.Text),
    sa.Column("storage_key", sa.Text),
    sa.Column("mime", sa.Text),
    sa.Column("size_bytes", sa.BigInteger),
    sa.Column("duration_s", sa.Float),
    sa.Column("sha256", sa.Text),
    sa.Column("integrity", sa.Text),                        # ok | short
    sa.Column("expected_talk_s", sa.Integer),
    sa.Column("stored_at", TS),
    sa.Column("deleted_at", TS),
    *stamps(),
)

csat_responses = sa.Table(
    "csat_responses", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(),
    sa.Column("call_id", UUID(as_uuid=False), sa.ForeignKey("ops.calls.id")),
    sa.Column("leg_id", UUID(as_uuid=False), unique=True),
    sa.Column("ticket_id", UUID(as_uuid=False)),
    sa.Column("source", sa.Text, nullable=False, server_default="55pbx"),
    sa.Column("score", sa.Float),
    sa.Column("weight", sa.Float),
    sa.Column("rating_type", sa.Text),
    sa.Column("form_id", sa.Text),
    sa.Column("form_name", sa.Text),
    sa.Column("data", JSONB, nullable=False, server_default=EMPTY_OBJ),
    sa.Column("created_at", TS, nullable=False, server_default=NOW),
)

dial_requests = sa.Table(
    "dial_requests", metadata,
    uuid_pk(),
    tenant_fk(),
    sa.Column("chatwoot_user_id", sa.Integer, nullable=False),
    sa.Column("branch", sa.Text),
    sa.Column("pbx_email", sa.Text),
    sa.Column("number_e164", sa.Text, nullable=False),
    sa.Column("ticket_id", UUID(as_uuid=False)),
    sa.Column("conversation_id", sa.Integer),
    sa.Column("contact_id", sa.Integer),
    sa.Column("status", sa.Text, nullable=False),          # pending | accepted | rejected | error | mock | disabled
    sa.Column("provider_http_status", sa.Integer),
    sa.Column("provider_call_id", sa.Text),
    sa.Column("message", sa.Text),
    sa.Column("created_at", TS, nullable=False, server_default=NOW),
    sa.Column("finished_at", TS),
    sa.Index("ix_dial_requests_provider", "tenant_id", "provider_call_id"),
)

callback_tasks = sa.Table(
    "callback_tasks", metadata,
    uuid_pk(),
    tenant_fk(),
    sa.Column("call_id", UUID(as_uuid=False), sa.ForeignKey("ops.calls.id"), unique=True),
    sa.Column("ticket_id", UUID(as_uuid=False)),
    sa.Column("number_e164", sa.Text),
    sa.Column("reason", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False, server_default="pending"),  # pending | done | cancelled
    sa.Column("due_at", TS),
    sa.Column("assigned_to", sa.Integer),
    sa.Column("completed_by", sa.Integer),
    sa.Column("completed_at", TS),
    sa.Column("completion_call_id", UUID(as_uuid=False)),
    sa.Column("result", sa.Text),
    *stamps(),
    sa.Index("ix_callback_tasks_pending", "tenant_id", "status", "due_at"),
)

# ------------------------------------------------------------------ tickets
support_tickets = sa.Table(
    "support_tickets", metadata,
    uuid_pk(),
    tenant_fk(),
    sa.Column("protocol", sa.Text, nullable=False, unique=True),
    sa.Column("protocol_numeric", sa.Text, nullable=False),
    sa.Column("contact_id", sa.Integer),
    sa.Column("contact_e164", sa.Text),
    sa.Column("contact_email", sa.Text),
    sa.Column("contact_name", sa.Text),
    sa.Column("organization", sa.Text),
    sa.Column("channel", sa.Text, nullable=False),          # phone | whatsapp | email | chat | api ...
    sa.Column("origin", sa.Text),                           # call_inbound | call_outbound | call_missed | manual | dial ...
    sa.Column("subject", sa.Text, nullable=False),
    sa.Column("description", sa.Text),
    sa.Column("category", sa.Text),
    sa.Column("subcategory", sa.Text),
    sa.Column("type", sa.Text),                             # question | incident | problem | task
    sa.Column("priority", sa.Text, nullable=False, server_default="normal"),  # baixa | normal | alta | urgente
    sa.Column("severity", sa.Text),
    sa.Column("department", sa.Text),
    sa.Column("team_id", sa.Integer),
    sa.Column("team_name", sa.Text),
    sa.Column("assignee_id", sa.Integer),
    sa.Column("status", sa.Text, nullable=False, server_default="novo"),
    sa.Column("escalation_level", sa.Integer, nullable=False, server_default="0"),
    sa.Column("parent_ticket_id", UUID(as_uuid=False)),
    sa.Column("reopen_count", sa.Integer, nullable=False, server_default="0"),
    sa.Column("close_reason", sa.Text),
    sa.Column("close_approved_by", sa.Integer),
    sa.Column("cancel_reason", sa.Text),
    sa.Column("needs_identification", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("first_response_at", TS),
    sa.Column("resolved_at", TS),
    sa.Column("closed_at", TS),
    sa.Column("cancelled_at", TS),
    sa.Column("created_by", sa.Text),                       # system | user:<id>
    sa.Column("deleted_at", TS),
    sa.Column("version", sa.Integer, nullable=False, server_default="1"),
    *stamps(),
    sa.UniqueConstraint("tenant_id", "protocol_numeric"),
    sa.Index("ix_support_tickets_tenant_status", "tenant_id", "status"),
    sa.Index("ix_support_tickets_tenant_contact", "tenant_id", "contact_id"),
    sa.Index("ix_support_tickets_tenant_e164", "tenant_id", "contact_e164"),
    sa.CheckConstraint("status in ('novo','triagem','em_atendimento','aguardando_cliente','aguardando_terceiro',"
                       "'resolvido','encerrado','cancelado')", name="status"),
)

protocol_counters = sa.Table(
    "protocol_counters", metadata,
    sa.Column("tenant_id", sa.Text, sa.ForeignKey("ops.tenants.id"), primary_key=True),
    sa.Column("year", sa.Integer, primary_key=True),
    sa.Column("last_value", sa.Integer, nullable=False),
)

ticket_events = sa.Table(
    "ticket_events", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(),
    sa.Column("ticket_id", UUID(as_uuid=False), sa.ForeignKey("ops.support_tickets.id"), nullable=False, index=True),
    sa.Column("kind", sa.Text, nullable=False),    # created | status_changed | field_changed | escalated | reopened | linked | merged
    sa.Column("from_status", sa.Text),
    sa.Column("to_status", sa.Text),
    sa.Column("field", sa.Text),
    sa.Column("old_value", JSONB),
    sa.Column("new_value", JSONB),
    sa.Column("reason", sa.Text),
    sa.Column("actor_type", sa.Text, nullable=False),
    sa.Column("actor_id", sa.Text),
    sa.Column("created_at", TS, nullable=False, server_default=NOW),
    sa.Column("correlation_id", sa.Text),
)

ticket_conversations = sa.Table(
    "ticket_conversations", metadata,
    sa.Column("ticket_id", UUID(as_uuid=False), sa.ForeignKey("ops.support_tickets.id"), primary_key=True),
    sa.Column("conversation_id", sa.Integer, primary_key=True),
    tenant_fk(),
    sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("last_synced_status", sa.Text),
    sa.Column("last_synced_at", TS),
    sa.Column("created_at", TS, nullable=False, server_default=NOW),
    sa.Index("ix_ticket_conversations_conv", "tenant_id", "conversation_id"),
)

ticket_calls = sa.Table(
    "ticket_calls", metadata,
    sa.Column("ticket_id", UUID(as_uuid=False), sa.ForeignKey("ops.support_tickets.id"), primary_key=True),
    sa.Column("call_id", UUID(as_uuid=False), sa.ForeignKey("ops.calls.id"), primary_key=True),
    tenant_fk(),
    sa.Column("relation", sa.Text, nullable=False, server_default="origin"),  # origin | related | dial | callback
    sa.Column("created_at", TS, nullable=False, server_default=NOW),
    sa.Index("ix_ticket_calls_call", "call_id"),
)

ticket_activities = sa.Table(
    "ticket_activities", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(),
    sa.Column("ticket_id", UUID(as_uuid=False), sa.ForeignKey("ops.support_tickets.id"), nullable=False, index=True),
    sa.Column("kind", sa.Text, nullable=False),     # registro | disposicao | nota_interna | analise | sistema
    sa.Column("body", sa.Text),
    sa.Column("data", JSONB, nullable=False, server_default=EMPTY_OBJ),
    sa.Column("call_id", UUID(as_uuid=False)),
    sa.Column("author_id", sa.Text),
    sa.Column("author_name", sa.Text),
    sa.Column("chatwoot_message_id", sa.Integer),
    sa.Column("dedup_key", sa.Text, unique=True),
    sa.Column("created_at", TS, nullable=False, server_default=NOW),
)

ticket_open_rules = sa.Table(
    "ticket_open_rules", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    tenant_fk(),
    sa.Column("sort", sa.Integer, nullable=False, server_default="100"),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("direction", sa.Text),           # receptivo | ativo | interno | NULL=qualquer
    sa.Column("queue_pattern", sa.Text),       # fnmatch sobre o nome normalizado da fila; NULL=qualquer
    sa.Column("channel", sa.Text, nullable=False, server_default="phone"),
    sa.Column("mode", sa.Text, nullable=False),          # all | answered | missed | none
    sa.Column("reuse", sa.Text, nullable=False),         # reuse_open | new | ask
    sa.Column("reuse_window_hours", sa.Integer, nullable=False, server_default="24"),
    sa.Column("default_priority", sa.Text, nullable=False, server_default="normal"),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    *stamps(),
    sa.CheckConstraint("mode in ('all','answered','missed','none')", name="mode"),
    sa.CheckConstraint("reuse in ('reuse_open','new','ask')", name="reuse"),
)

# ------------------------------------------------------------------ SLA
sla_policies = sa.Table(
    "sla_policies", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    tenant_fk(),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("sort", sa.Integer, nullable=False, server_default="100"),
    sa.Column("priority", sa.Text),            # NULL = qualquer
    sa.Column("team_name", sa.Text),           # NULL = qualquer
    sa.Column("channel", sa.Text),             # NULL = qualquer
    sa.Column("first_response_min", sa.Integer),
    sa.Column("resolution_min", sa.Integer),
    sa.Column("business_hours_id", sa.Integer, sa.ForeignKey("ops.business_hours.id")),
    sa.Column("pause_on_waiting", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("phone_answer_counts", sa.Boolean, nullable=False, server_default=sa.true()),
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    *stamps(),
)

sla_instances = sa.Table(
    "sla_instances", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(),
    sa.Column("ticket_id", UUID(as_uuid=False), sa.ForeignKey("ops.support_tickets.id"), nullable=False),
    sa.Column("policy_id", sa.Integer, sa.ForeignKey("ops.sla_policies.id")),
    sa.Column("metric", sa.Text, nullable=False),           # first_response | resolution
    sa.Column("status", sa.Text, nullable=False),           # running | paused | stopped
    sa.Column("breached", sa.Boolean, nullable=False, server_default=sa.false()),
    sa.Column("target_min", sa.Integer, nullable=False),
    sa.Column("started_at", TS, nullable=False),
    sa.Column("due_at", TS, nullable=False),
    sa.Column("paused_at", TS),
    sa.Column("stopped_at", TS),
    sa.Column("breached_at", TS),
    *stamps(),
    sa.UniqueConstraint("ticket_id", "metric"),
    sa.Index("ix_sla_instances_due", "status", "breached", "due_at"),
)

sla_events = sa.Table(
    "sla_events", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(),
    sa.Column("sla_instance_id", sa.BigInteger, sa.ForeignKey("ops.sla_instances.id"), nullable=False),
    sa.Column("ticket_id", UUID(as_uuid=False), nullable=False, index=True),
    sa.Column("kind", sa.Text, nullable=False),            # started | paused | resumed | met | breached | recalculated
    sa.Column("at", TS, nullable=False, server_default=NOW),
    sa.Column("data", JSONB, nullable=False, server_default=EMPTY_OBJ),
)

# ------------------------------------------------------------------ análise (referências do A3), auditoria, sync
analysis_refs = sa.Table(
    "analysis_refs", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(),
    sa.Column("kind", sa.Text, nullable=False),     # transcription | summary | qa
    sa.Column("external_id", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),   # completed | partial | failed
    sa.Column("call_id", UUID(as_uuid=False)),
    sa.Column("recording_id", UUID(as_uuid=False)),
    sa.Column("score", sa.Float),
    sa.Column("data", JSONB, nullable=False, server_default=EMPTY_OBJ),
    sa.Column("completed_at", TS),
    sa.Column("created_at", TS, nullable=False, server_default=NOW),
    sa.UniqueConstraint("tenant_id", "kind", "external_id"),
)

audit_events = sa.Table(
    "audit_events", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(nullable=True),
    sa.Column("at", TS, nullable=False, server_default=NOW),
    sa.Column("actor_type", sa.Text, nullable=False),     # system | user | service | provider
    sa.Column("actor_id", sa.Text),
    sa.Column("action", sa.Text, nullable=False),
    sa.Column("entity_type", sa.Text),
    sa.Column("entity_id", sa.Text),
    sa.Column("data", JSONB, nullable=False, server_default=EMPTY_OBJ),
    sa.Column("ip", sa.Text),
    sa.Column("correlation_id", sa.Text),
    sa.Index("ix_audit_events_entity", "entity_type", "entity_id"),
    sa.Index("ix_audit_events_tenant_at", "tenant_id", "at"),
)

integration_sync_logs = sa.Table(
    "integration_sync_logs", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(nullable=True),
    sa.Column("target", sa.Text, nullable=False),          # chatwoot | 55pbx | redis | storage
    sa.Column("operation", sa.Text, nullable=False),
    sa.Column("entity_type", sa.Text),
    sa.Column("entity_id", sa.Text),
    sa.Column("status", sa.Text, nullable=False),          # ok | error | retry | dead
    sa.Column("duration_ms", sa.Integer),
    sa.Column("error", sa.Text),
    sa.Column("at", TS, nullable=False, server_default=NOW),
    sa.Column("correlation_id", sa.Text),
)

reconciliation_runs = sa.Table(
    "reconciliation_runs", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(),
    sa.Column("mode", sa.Text, nullable=False),            # poll | historical
    sa.Column("window_start", TS, nullable=False),
    sa.Column("window_end", TS, nullable=False),
    sa.Column("status", sa.Text, nullable=False),          # ok | error
    sa.Column("rows", sa.Integer),
    sa.Column("new_rows", sa.Integer),
    sa.Column("error", sa.Text),
    sa.Column("started_at", TS, nullable=False, server_default=NOW),
    sa.Column("finished_at", TS),
)

# Estado da projeção legada (notas no Chatwoot no formato do Zendesk) — antes ficava no SQLite da pbx-bridge.
chatwoot_call_projection = sa.Table(
    "chatwoot_call_projection", metadata,
    sa.Column("tenant_id", sa.Text, sa.ForeignKey("ops.tenants.id"), primary_key=True),
    sa.Column("call_id", sa.Text, primary_key=True),       # provider_call_id da perna raiz
    sa.Column("data", JSONB, nullable=False),
    sa.Column("conversation_id", sa.Integer),
    sa.Column("contact_id", sa.Integer),
    sa.Column("parts", JSONB, nullable=False, server_default=EMPTY_ARR),
    sa.Column("audio_status", sa.Text, nullable=False, server_default="none"),
    sa.Column("audio_attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("audio_next_at", sa.Float, nullable=False, server_default="0"),
    *stamps(),
)

kv = sa.Table(
    "kv", metadata,
    sa.Column("k", sa.Text, primary_key=True),
    sa.Column("v", sa.Text),
    sa.Column("updated_at", TS, nullable=False, server_default=NOW),
)

# ------------------------------------------------------------------ automações (ponte para o n8n) e idempotência
automation_routes = sa.Table(
    "automation_routes", metadata,
    sa.Column("id", sa.Integer, primary_key=True),
    tenant_fk(nullable=True),                  # NULL = todos os tenants
    sa.Column("name", sa.Text, nullable=False),          # WF01 ...
    sa.Column("event_types", JSONB, nullable=False),     # ["call.missed", "ticket.*"]
    sa.Column("url", sa.Text, nullable=False),
    sa.Column("token_ref", sa.Text),                     # variável de ambiente do X-SD-Webhook-Token
    sa.Column("secret_ref", sa.Text),                    # variável de ambiente do segredo HMAC
    sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
    *stamps(),
)

automation_executions = sa.Table(
    "automation_executions", metadata,
    sa.Column("id", sa.BigInteger, primary_key=True),
    tenant_fk(),
    sa.Column("route_id", sa.Integer, sa.ForeignKey("ops.automation_routes.id"), nullable=False),
    sa.Column("event_id", sa.Text, nullable=False),
    sa.Column("event_type", sa.Text, nullable=False),
    sa.Column("status", sa.Text, nullable=False),        # ok | error | dead | skipped_loop
    sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    sa.Column("http_status", sa.Integer),
    sa.Column("error", sa.Text),
    *stamps(),
    sa.UniqueConstraint("route_id", "event_id"),
)

idempotency_keys = sa.Table(
    "idempotency_keys", metadata,
    sa.Column("key", sa.Text, primary_key=True),          # <ator>:<Idempotency-Key>
    tenant_fk(),
    sa.Column("method", sa.Text, nullable=False),
    sa.Column("path", sa.Text, nullable=False),
    sa.Column("status_code", sa.Integer, nullable=False),
    sa.Column("response", JSONB, nullable=False),
    sa.Column("created_at", TS, nullable=False, server_default=NOW),
)
