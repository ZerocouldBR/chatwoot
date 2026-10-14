"""Modelo de dados do schema `qa` (banco servicedesk_ops). Nada em tabelas do Chatwoot.

Convenções: UTC (timestamptz), multi-tenant por `tenant_id`, IDs externos como texto
(recording_id, call_id, ticket_id vêm do sd-ops; conversation_id do Chatwoot),
idempotência por índices únicos. Tabelas de auditoria são append-only.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer,
    MetaData, Numeric, String, Text, UniqueConstraint, func, text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "qa"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA, naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s",
        "pk": "pk_%(table_name)s",
    })


def _now():
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RubricVersion(Base):
    __tablename__ = "rubric_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # [{key,label,weight,description,guidance,audio_verifiable}]
    criteria: Mapped[list] = mapped_column(JSONB, nullable=False)
    redistribution_rule: Mapped[str] = mapped_column(Text, nullable=False)
    mandatory_phrases: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_by: Mapped[Optional[str]] = mapped_column(String(200))
    created_at: Mapped[datetime] = _now()
    __table_args__ = (UniqueConstraint("tenant_id", "code", "version"),)


class PromptVersion(Base):
    __tablename__ = "prompt_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # summary | qa
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    template: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = _now()
    __table_args__ = (UniqueConstraint("kind", "version"),)


class ProcessedEvent(Base):
    """Inbox: cada evento do stream é aplicado uma única vez."""
    __tablename__ = "processed_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    stream_id: Mapped[Optional[str]] = mapped_column(String(64))
    result: Mapped[Optional[str]] = mapped_column(String(64))
    processed_at: Mapped[datetime] = _now()


class Job(Base):
    __tablename__ = "processing_jobs"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recording_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1"))
    mode: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'full'"))  # full | analysis
    call_id: Mapped[Optional[str]] = mapped_column(String(128))
    ticket_id: Mapped[Optional[str]] = mapped_column(String(128))
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64))
    agent_ref: Mapped[Optional[str]] = mapped_column(String(200))
    agent_name: Mapped[Optional[str]] = mapped_column(String(200))
    team: Mapped[Optional[str]] = mapped_column(String(200))
    storage_key: Mapped[Optional[str]] = mapped_column(Text)
    mime: Mapped[Optional[str]] = mapped_column(String(64))
    duration_s: Mapped[Optional[float]] = mapped_column(Float)
    sha256: Mapped[Optional[str]] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'pending'"))
    stage: Mapped[Optional[str]] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    next_attempt_at: Mapped[datetime] = _now()
    locked_by: Mapped[Optional[str]] = mapped_column(String(128))
    locked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    requested_by: Mapped[Optional[str]] = mapped_column(String(200))
    reason: Mapped[Optional[str]] = mapped_column(Text)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64))
    source_event_id: Mapped[Optional[str]] = mapped_column(String(128))
    timings: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("tenant_id", "recording_id", "run"),
        CheckConstraint("status in ('pending','running','waiting_audio','done','failed','cancelled')", name="status"),
        Index("ix_processing_jobs_due", "status", "next_attempt_at"),
        Index("ix_processing_jobs_call", "tenant_id", "call_id"),
    )


class Transcription(Base):
    __tablename__ = "transcriptions"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("processing_jobs.id"), nullable=False, unique=True)
    recording_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run: Mapped[int] = mapped_column(Integer, nullable=False)
    call_id: Mapped[Optional[str]] = mapped_column(String(128))
    ticket_id: Mapped[Optional[str]] = mapped_column(String(128))
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # completed | partial
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(64), nullable=False)
    engine_config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    language: Mapped[Optional[str]] = mapped_column(String(8))
    language_probability: Mapped[Optional[float]] = mapped_column(Float)
    audio_duration_s: Mapped[Optional[float]] = mapped_column(Float)
    expected_duration_s: Mapped[Optional[float]] = mapped_column(Float)
    coverage_ratio: Mapped[Optional[float]] = mapped_column(Float)
    avg_confidence: Mapped[Optional[float]] = mapped_column(Float)
    low_confidence_ratio: Mapped[Optional[float]] = mapped_column(Float)
    diarization: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'none'"))
    text_masked: Mapped[str] = mapped_column(Text, nullable=False)
    text_raw: Mapped[Optional[str]] = mapped_column(Text)  # só se STORE_UNMASKED_TRANSCRIPT=true
    pii_counts: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    audio_sha256: Mapped[Optional[str]] = mapped_column(String(64))
    processing_ms: Mapped[Optional[int]] = mapped_column(Integer)
    rtf: Mapped[Optional[float]] = mapped_column(Float)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _now()
    __table_args__ = (
        UniqueConstraint("tenant_id", "recording_id", "run"),
        Index("uq_transcriptions_current", "tenant_id", "recording_id", unique=True,
              postgresql_where=text("is_current")),
    )


class TranscriptionSegment(Base):
    __tablename__ = "transcription_segments"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    transcription_id: Mapped[int] = mapped_column(ForeignKey("transcriptions.id", ondelete="CASCADE"), nullable=False)
    idx: Mapped[int] = mapped_column(Integer, nullable=False)
    start_s: Mapped[float] = mapped_column(Float, nullable=False)
    end_s: Mapped[float] = mapped_column(Float, nullable=False)
    channel: Mapped[Optional[int]] = mapped_column(Integer)
    # Rótulo de interlocutor só com evidência (canal separado + mapa configurado); senão NULL.
    speaker: Mapped[Optional[str]] = mapped_column(String(32))
    speaker_evidence: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'none'"))
    text_masked: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    no_speech_prob: Mapped[Optional[float]] = mapped_column(Float)
    low_confidence: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    __table_args__ = (UniqueConstraint("transcription_id", "idx"),)


class CallSummary(Base):
    __tablename__ = "call_summaries"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    job_id: Mapped[int] = mapped_column(ForeignKey("processing_jobs.id"), nullable=False, unique=True)
    transcription_id: Mapped[int] = mapped_column(ForeignKey("transcriptions.id"), nullable=False)
    recording_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64))
    ticket_id: Mapped[Optional[str]] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'draft'"))
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    final_content: Mapped[Optional[dict]] = mapped_column(JSONB)
    llm_provider: Mapped[str] = mapped_column(String(32), nullable=False)
    llm_model: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version_id: Mapped[int] = mapped_column(ForeignKey("prompt_versions.id"), nullable=False)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(200))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    note_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"))
    note_message_id: Mapped[Optional[str]] = mapped_column(String(64))
    note_error: Mapped[Optional[str]] = mapped_column(Text)
    note_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _now()
    __table_args__ = (
        CheckConstraint("status in ('draft','approved','edited','rejected')", name="status"),
        CheckConstraint("note_status in ('pending','sent','skipped','failed')", name="note_status"),
        Index("ix_call_summaries_rec", "tenant_id", "recording_id"),
    )


class QaEvaluation(Base):
    __tablename__ = "qa_evaluations"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("processing_jobs.id"))
    transcription_id: Mapped[int] = mapped_column(ForeignKey("transcriptions.id"), nullable=False)
    parent_evaluation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("qa_evaluations.id"))
    recording_id: Mapped[str] = mapped_column(String(128), nullable=False)
    call_id: Mapped[Optional[str]] = mapped_column(String(128))
    ticket_id: Mapped[Optional[str]] = mapped_column(String(128))
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64))
    agent_ref: Mapped[Optional[str]] = mapped_column(String(200))
    agent_name: Mapped[Optional[str]] = mapped_column(String(200))
    team: Mapped[Optional[str]] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(String(8), nullable=False)  # ai | human
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    applicable_weight: Mapped[Optional[int]] = mapped_column(Integer)
    redistribution: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    rubric_version_id: Mapped[int] = mapped_column(ForeignKey("rubric_versions.id"), nullable=False)
    prompt_version_id: Mapped[Optional[int]] = mapped_column(ForeignKey("prompt_versions.id"))
    llm_provider: Mapped[Optional[str]] = mapped_column(String(32))
    llm_model: Mapped[Optional[str]] = mapped_column(String(64))
    stt_model: Mapped[Optional[str]] = mapped_column(String(64))
    reviewer_ref: Mapped[Optional[str]] = mapped_column(String(200))
    comment: Mapped[Optional[str]] = mapped_column(Text)
    warnings: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = _now()
    __table_args__ = (
        CheckConstraint("source in ('ai','human')", name="source"),
        CheckConstraint(
            "status in ('ai_completed','insufficient_evidence','reviewed','contested','contest_upheld','contest_revised')",
            name="status"),
        CheckConstraint("score is null or (score >= 0 and score <= 100)", name="score_range"),
        Index("ix_qa_evaluations_agent", "tenant_id", "agent_ref", "created_at"),
        Index("ix_qa_evaluations_rec", "tenant_id", "recording_id"),
        Index("ix_qa_evaluations_parent", "parent_evaluation_id"),
    )


class QaCriterionScore(Base):
    __tablename__ = "qa_criteria_scores"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("qa_evaluations.id", ondelete="CASCADE"), nullable=False)
    criterion_key: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    weight: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_weight: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[Optional[float]] = mapped_column(Float)
    justification: Mapped[Optional[str]] = mapped_column(Text)
    evidence_text: Mapped[Optional[str]] = mapped_column(Text)
    evidence_start_s: Mapped[Optional[float]] = mapped_column(Float)
    evidence_end_s: Mapped[Optional[float]] = mapped_column(Float)
    evidence_segment_idx: Mapped[Optional[int]] = mapped_column(Integer)
    evidence_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    suggestion: Mapped[Optional[str]] = mapped_column(Text)
    flags: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    __table_args__ = (
        UniqueConstraint("evaluation_id", "criterion_key"),
        CheckConstraint("status in ('observed','not_observed','not_applicable')", name="status"),
    )


class QaReviewEvent(Base):
    """Trilha de auditoria (append-only) de revisão, contestação, reprocessamento e resumo."""
    __tablename__ = "qa_review_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("qa_evaluations.id"))
    summary_id: Mapped[Optional[int]] = mapped_column(ForeignKey("call_summaries.id"))
    recording_id: Mapped[Optional[str]] = mapped_column(String(128))
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _now()


class ReviewTask(Base):
    __tablename__ = "review_tasks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(300), nullable=False, unique=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # alert | qa_low_score | qa_insufficient_evidence | contest | pipeline_failure
    alert_type: Mapped[Optional[str]] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'media'"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[Optional[str]] = mapped_column(Text)
    evidence_text: Mapped[Optional[str]] = mapped_column(Text)
    evidence_start_s: Mapped[Optional[float]] = mapped_column(Float)
    evidence_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    evaluation_id: Mapped[Optional[int]] = mapped_column(ForeignKey("qa_evaluations.id"))
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("processing_jobs.id"))
    recording_id: Mapped[Optional[str]] = mapped_column(String(128))
    call_id: Mapped[Optional[str]] = mapped_column(String(128))
    ticket_id: Mapped[Optional[str]] = mapped_column(String(128))
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64))
    agent_ref: Mapped[Optional[str]] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'open'"))
    assigned_to: Mapped[Optional[str]] = mapped_column(String(200))
    resolution: Mapped[Optional[str]] = mapped_column(Text)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(200))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    __table_args__ = (
        CheckConstraint("status in ('open','in_progress','done','dismissed')", name="status"),
        CheckConstraint("severity in ('baixa','media','alta')", name="severity"),
        Index("ix_review_tasks_open", "tenant_id", "status", "created_at"),
        Index("ix_review_tasks_rec", "tenant_id", "recording_id"),
    )


class CsatResponse(Base):
    __tablename__ = "csat_responses"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # chatwoot | 55pbx | n8n
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(64))
    ticket_id: Mapped[Optional[str]] = mapped_column(String(128))
    call_id: Mapped[Optional[str]] = mapped_column(String(128))
    agent_ref: Mapped[Optional[str]] = mapped_column(String(200))
    score: Mapped[float] = mapped_column(Float, nullable=False)
    scale_max: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("5"))
    comment_masked: Mapped[Optional[str]] = mapped_column(Text)
    responded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = _now()
    __table_args__ = (UniqueConstraint("tenant_id", "source", "external_id"),)


class AccessLog(Base):
    """Quem ouviu/leu o quê (gravação, transcrição, avaliação). Append-only."""
    __tablename__ = "access_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recording_id: Mapped[Optional[str]] = mapped_column(String(128))
    evaluation_id: Mapped[Optional[int]] = mapped_column(BigInteger)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    ip: Mapped[Optional[str]] = mapped_column(String(64))
    created_at: Mapped[datetime] = _now()


class RecordingMark(Base):
    """Marcação de trechos no player (início/fim, rótulo, nota mascarada)."""
    __tablename__ = "recording_marks"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False)
    recording_id: Mapped[str] = mapped_column(String(128), nullable=False)
    start_s: Mapped[float] = mapped_column(Float, nullable=False)
    end_s: Mapped[Optional[float]] = mapped_column(Float)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = _now()
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_recording_marks_rec", "tenant_id", "recording_id"),)


class Outbox(Base):
    """Outbox: eventos publicados no stream após o commit (entrega pelo menos uma vez)."""
    __tablename__ = "outbox"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    stream_id: Mapped[Optional[str]] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    # Entrega REST ao sd-ops (POST /analysis-results), independente do stream.
    sdops_status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'pending'"))
    sdops_attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    sdops_error: Mapped[Optional[str]] = mapped_column(Text)
    sdops_next_at: Mapped[datetime] = _now()
    created_at: Mapped[datetime] = _now()
