"""ops: notification_logs (registro idempotente de envios do n8n)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13 23:00:00

POST /sd-ops/api/v1/notifications/log passa a ser idempotente por (tenant_id, dedupe_key), com a chave
vinda do corpo (dedupe_key) ou do header Idempotency-Key. Ver WEBHOOK_CONTRACTS.md §8.4.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('notification_logs',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('tenant_id', sa.Text(), nullable=False),
    sa.Column('dedupe_key', sa.Text(), nullable=False),
    sa.Column('channel', sa.Text(), nullable=False),
    sa.Column('template', sa.Text(), nullable=True),
    sa.Column('ticket_id', sa.Text(), nullable=True),
    sa.Column('call_id', sa.Text(), nullable=True),
    sa.Column('status', sa.Text(), nullable=False),
    sa.Column('opt_out', sa.Boolean(), server_default=sa.false(), nullable=False),
    sa.Column('detail', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('actor', sa.Text(), nullable=True),
    sa.Column('caused_by', sa.Text(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['ops.tenants.id'], name=op.f('fk_notification_logs_tenant_id_tenants')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notification_logs')),
    sa.UniqueConstraint('tenant_id', 'dedupe_key', name=op.f('uq_notification_logs_tenant_id_dedupe_key')),
    schema='ops'
    )
    op.create_index(op.f('ix_notification_logs_tenant_id'), 'notification_logs', ['tenant_id'], unique=False, schema='ops')
    op.create_index('ix_notification_logs_ticket', 'notification_logs', ['tenant_id', 'ticket_id'], unique=False,
                    schema='ops')


def downgrade() -> None:
    op.drop_index('ix_notification_logs_ticket', table_name='notification_logs', schema='ops')
    op.drop_index(op.f('ix_notification_logs_tenant_id'), table_name='notification_logs', schema='ops')
    op.drop_table('notification_logs', schema='ops')
