"""Ambiente Alembic do schema qa. Só enxerga objetos do schema qa (nunca toca no Chatwoot nem no ops)."""
from __future__ import annotations

import os

from alembic import context
from sqlalchemy import create_engine, text

from qa_pipeline.models import SCHEMA, Base

config = context.config
target_metadata = Base.metadata


def _url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL não definido")
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def include_object(obj, name, type_, reflected, compare_to):
    schema = getattr(obj, "schema", None) or getattr(getattr(obj, "table", None), "schema", None)
    return schema == SCHEMA if type_ in ("table", "index", "unique_constraint", "foreign_key_constraint") else True


def run_migrations_offline():
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True,
                      version_table="alembic_version", version_table_schema=SCHEMA, include_schemas=True,
                      include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(_url())
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}"))
        conn.commit()
        context.configure(connection=conn, target_metadata=target_metadata, version_table="alembic_version",
                          version_table_schema=SCHEMA, include_schemas=True, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
