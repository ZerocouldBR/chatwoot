"""ops: tenant_settings (configuração da 55PBX pelo painel) e role do Chatwoot na sessão

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-14 12:00:00

- ops.tenant_settings: valores por tenant gravados pela tela "Telefonia 55PBX" (Configurações do Chatwoot).
  Precedência: valor da tela > variável de ambiente. Segredos só cifrados com Fernet (SDOPS_SETTINGS_KEY).
- ops.cti_sessions.chatwoot_role: role da conta no Chatwoot no momento do login (a API de configuração exige
  administrator; papéis concedidos em ops.user_roles não bastam).
Ver docs/INTEGRACAO-55PBX.md, "Configuração pelo painel (admin)".
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('tenant_settings',
    sa.Column('tenant_id', sa.Text(), nullable=False),
    sa.Column('values', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('secrets', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    sa.Column('version', sa.Integer(), server_default='1', nullable=False),
    sa.Column('updated_by', sa.Integer(), nullable=True),
    sa.Column('updated_by_email', sa.Text(), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['tenant_id'], ['ops.tenants.id'], name=op.f('fk_tenant_settings_tenant_id_tenants')),
    sa.PrimaryKeyConstraint('tenant_id', name=op.f('pk_tenant_settings')),
    schema='ops'
    )
    op.add_column('cti_sessions', sa.Column('chatwoot_role', sa.Text(), nullable=True), schema='ops')


def downgrade() -> None:
    op.drop_column('cti_sessions', 'chatwoot_role', schema='ops')
    op.drop_table('tenant_settings', schema='ops')
