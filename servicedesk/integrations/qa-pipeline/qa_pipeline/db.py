"""Engine/sessão SQLAlchemy e seeds idempotentes (rubrica padrão e prompts versionados)."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from . import prompts
from .models import PromptVersion, RubricVersion
from .rubric import DEFAULT_RUBRIC

_engine: Optional[Engine] = None
_Session: Optional[sessionmaker] = None


def init_engine(url: str) -> Engine:
    global _engine, _Session
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    _engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=5, future=True)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    return _engine


def engine() -> Engine:
    assert _engine is not None, "init_engine() não chamado"
    return _engine


@contextmanager
def session() -> Iterator[Session]:
    assert _Session is not None, "init_engine() não chamado"
    s = _Session()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def ensure_prompt(s: Session, kind: str, version: Optional[str] = None) -> PromptVersion:
    ver, template, digest = prompts.load(kind, version)
    pv = s.execute(select(PromptVersion).where(PromptVersion.kind == kind, PromptVersion.version == ver)).scalar_one_or_none()
    if pv is None:
        pv = PromptVersion(kind=kind, version=ver, template=template, sha256=digest)
        s.add(pv)
        s.flush()
    elif pv.sha256 != digest:
        raise RuntimeError(f"prompt {kind}_{ver} mudou sem nova versão (sha256 diferente). Crie {kind}_v<N+1>.txt")
    return pv


def active_rubric(s: Session, tenant: str, code: str) -> RubricVersion:
    rv = s.execute(select(RubricVersion).where(RubricVersion.tenant_id == tenant, RubricVersion.code == code,
                                               RubricVersion.active.is_(True))
                   .order_by(RubricVersion.version.desc())).scalars().first()
    if rv is None:
        rv = RubricVersion(tenant_id=tenant, code=DEFAULT_RUBRIC["code"], version=DEFAULT_RUBRIC["version"],
                           name=DEFAULT_RUBRIC["name"], criteria=DEFAULT_RUBRIC["criteria"],
                           mandatory_phrases=DEFAULT_RUBRIC["mandatory_phrases"],
                           redistribution_rule=DEFAULT_RUBRIC["redistribution_rule"], active=True,
                           created_by="sistema")
        s.add(rv)
        s.flush()
    return rv
