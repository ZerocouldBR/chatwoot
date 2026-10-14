"""Alembic do sd-ops: banco servicedesk_ops, schema ops (o A3 usa o schema qa com Alembic próprio)."""
from __future__ import annotations

import os

import sqlalchemy as sa
from alembic import context

from sd_ops.models import SCHEMA, metadata

config = context.config
url = config.get_main_option("sqlalchemy.url") or os.environ.get("SDOPS_DATABASE_URL", "")


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name == SCHEMA
    return True


def run_migrations_online() -> None:
    engine = sa.create_engine(url, future=True)
    with engine.connect() as conn:
        conn.execute(sa.text("CREATE SCHEMA IF NOT EXISTS %s" % SCHEMA))
        conn.commit()
        context.configure(connection=conn, target_metadata=metadata, include_schemas=True,
                          include_name=include_name, version_table_schema=SCHEMA, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(url=url, target_metadata=metadata, literal_binds=True, include_schemas=True,
                      version_table_schema=SCHEMA)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
