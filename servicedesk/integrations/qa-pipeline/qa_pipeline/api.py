"""API REST do console de QA: /sd-qa/api/v1 (OpenAPI em /sd-qa/api/v1/openapi.json).

Tudo filtrado pelo tenant da sessão; recurso de outro tenant -> 404. Agente vê só as próprias
avaliações/transcrições. Ações sensíveis vão para qa.qa_review_events / qa.access_log.
"""
from __future__ import annotations

import csv
import io
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text

from . import __version__, db
from .auth import Authenticator, Principal, require
from .config import Settings, get_settings
from .models import (AccessLog, CallSummary, CsatResponse, Job, Outbox, PromptVersion, QaCriterionScore, QaEvaluation,
                     QaReviewEvent, RecordingMark, ReviewTask, RubricVersion, Transcription, TranscriptionSegment)
from .pii import mask_text
from .pipeline import Pipeline
from .rubric import CriterionResult, compute_score, validate_rubric

PREFIX = "/sd-qa/api/v1"


def _nf():
    return HTTPException(404, detail={"error": "not_found", "message": "não encontrado"})


def _num(v):
    return float(v) if v is not None else None


def _iso(d):
    return d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def _range(frm: Optional[str], to: Optional[str]):
    now = datetime.now(timezone.utc)
    try:
        t = datetime.fromisoformat(to.replace("Z", "+00:00")) if to else now
        f = datetime.fromisoformat(frm.replace("Z", "+00:00")) if frm else t - timedelta(days=30)
    except ValueError:
        raise HTTPException(400, detail={"error": "bad_date", "message": "datas em ISO 8601"})
    if f.tzinfo is None:
        f = f.replace(tzinfo=timezone.utc)
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    if len(to or "") == 10:  # data sem hora: inclui o dia inteiro
        t = t + timedelta(days=1)
    return f, t


class CriterionIn(BaseModel):
    key: str
    status: str = Field(pattern="^(observed|not_observed|not_applicable)$")
    score: Optional[float] = Field(default=None, ge=0, le=100)
    justification: Optional[str] = Field(default=None, max_length=2000)


class ReviewIn(BaseModel):
    criteria: List[CriterionIn] = []
    comment: Optional[str] = Field(default=None, max_length=4000)


class ContestIn(BaseModel):
    reason: str = Field(min_length=5, max_length=4000)


class ContestResolveIn(BaseModel):
    decision: str = Field(pattern="^(upheld|revised)$")
    comment: str = Field(min_length=3, max_length=4000)
    criteria: List[CriterionIn] = []


class ReprocessIn(BaseModel):
    mode: str = Field(default="full", pattern="^(full|analysis)$")
    reason: str = Field(min_length=3, max_length=1000)


class SummaryReviewIn(BaseModel):
    action: str = Field(pattern="^(approve|edit|reject)$")
    content: Optional[dict] = None
    comment: Optional[str] = Field(default=None, max_length=2000)


class TaskPatchIn(BaseModel):
    status: Optional[str] = Field(default=None, pattern="^(open|in_progress|done|dismissed)$")
    resolution: Optional[str] = Field(default=None, max_length=2000)
    assigned_to: Optional[str] = Field(default=None, max_length=200)


class RubricIn(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    criteria: List[dict]
    mandatory_phrases: List[dict] = []


class AccessIn(BaseModel):
    recording_id: str
    action: str = Field(pattern="^(play|pause|seek|rate|mark|transcript_view|download_blocked)$")
    detail: dict = {}


class MarkIn(BaseModel):
    start_s: float = Field(ge=0)
    end_s: Optional[float] = Field(default=None, ge=0)
    label: str = Field(min_length=1, max_length=64)
    note: Optional[str] = Field(default=None, max_length=1000)


class CsatIn(BaseModel):
    csat_id: str
    source: str = "n8n"
    score: float
    scale_max: int = 5
    conversation_id: Optional[str] = None
    ticket_id: Optional[str] = None
    call_id: Optional[str] = None
    agent_email: Optional[str] = None
    comment: Optional[str] = None
    responded_at: Optional[str] = None


def create_app(settings: Optional[Settings] = None, authenticator: Optional[Authenticator] = None) -> FastAPI:
    s = settings or get_settings()
    if db._engine is None:
        db.init_engine(s.database_url)
    auth = authenticator or Authenticator(s)
    pipe = Pipeline(s)
    app = FastAPI(title="ServiceDesk QA/IA", version=__version__, docs_url=f"{PREFIX}/docs",
                  openapi_url=f"{PREFIX}/openapi.json", redoc_url=None)

    def me(request: Request) -> Principal:
        return auth(request)

    def log_access(session, p: Principal, action: str, request: Request, recording_id=None, evaluation_id=None,
                   detail=None):
        session.add(AccessLog(tenant_id=p.tenant, recording_id=recording_id, evaluation_id=evaluation_id,
                              action=action, actor_ref=p.ref, actor_role=",".join(sorted(p.roles)) or "servico",
                              detail=detail or {}, ip=(request.client.host if request.client else None)))

    def ev_visible(session, p: Principal, ev_id: int) -> QaEvaluation:
        ev = session.get(QaEvaluation, ev_id)
        if ev is None or ev.tenant_id != p.tenant:
            raise _nf()
        if not p.is_manager and ev.agent_ref != p.ref:
            raise _nf()
        return ev

    @app.get("/sd-qa/health")
    def health():
        out = {"status": "ok", "version": __version__, "config": s.redacted()}
        try:
            with db.session() as ss:
                ss.execute(text("select 1"))
                rows = ss.execute(select(Job.status, func.count()).group_by(Job.status)).all()
                out["jobs"] = {k: v for k, v in rows}
                out["outbox_pending"] = ss.execute(select(func.count()).select_from(Outbox)
                                                   .where(Outbox.published_at.is_(None))).scalar()
                out["sdops_pending"] = ss.execute(select(func.count()).select_from(Outbox)
                                                  .where(Outbox.sdops_status == "pending")).scalar()
                out["alembic"] = ss.execute(text("select version_num from qa.alembic_version")).scalar()
        except Exception as exc:
            return JSONResponse({"status": "error", "error": type(exc).__name__}, status_code=503)
        return out

    @app.get(f"{PREFIX}/me")
    def whoami(p: Principal = Depends(me)):
        return {"ref": p.ref, "name": p.name, "tenant": p.tenant, "roles": sorted(p.roles),
                "is_manager": p.is_manager, "scopes": sorted(p.scopes)}

    # ------------------------------------------------------------ avaliações
    def _ev_row(ev: QaEvaluation, human: Optional[QaEvaluation], open_tasks: int) -> dict:
        review_state = "pendente"
        if ev.status == "contested":
            review_state = "contestada"
        elif human is not None:
            review_state = "revisada"
        return {"id": ev.id, "recording_id": ev.recording_id, "call_id": ev.call_id, "ticket_id": ev.ticket_id,
                "conversation_id": ev.conversation_id, "agent_ref": ev.agent_ref, "agent_name": ev.agent_name,
                "team": ev.team, "status": ev.status, "review_state": review_state, "ai_score": _num(ev.score),
                "human_score": _num(human.score) if human else None,
                "final_score": _num(human.score) if human else _num(ev.score), "confidence": ev.confidence,
                "llm_provider": ev.llm_provider, "llm_model": ev.llm_model, "created_at": _iso(ev.created_at),
                "open_tasks": open_tasks}

    def _latest_human(ss, ev_ids: List[int]):
        if not ev_ids:
            return {}
        rows = ss.execute(select(QaEvaluation).where(QaEvaluation.parent_evaluation_id.in_(ev_ids),
                                                     QaEvaluation.source == "human")
                          .order_by(QaEvaluation.id)).scalars().all()
        return {r.parent_evaluation_id: r for r in rows}

    def _ai_query(p: Principal, frm, to, agent, team, status, review):
        q = select(QaEvaluation).where(QaEvaluation.tenant_id == p.tenant, QaEvaluation.source == "ai",
                                       QaEvaluation.is_current.is_(True), QaEvaluation.created_at >= frm,
                                       QaEvaluation.created_at < to)
        if not p.is_manager:
            q = q.where(QaEvaluation.agent_ref == p.ref)
        elif agent:
            q = q.where(QaEvaluation.agent_ref == agent)
        if team:
            q = q.where(QaEvaluation.team == team)
        if status:
            q = q.where(QaEvaluation.status == status)
        if review == "contestada":
            q = q.where(QaEvaluation.status == "contested")
        return q

    @app.get(f"{PREFIX}/evaluations")
    def list_evaluations(p: Principal = Depends(me), frm: Optional[str] = Query(None, alias="from"),
                         to: Optional[str] = None, agent: Optional[str] = None, team: Optional[str] = None,
                         status: Optional[str] = None, review: Optional[str] = Query(None, pattern="^(pendente|revisada|contestada)$"),
                         min_score: Optional[float] = None, max_score: Optional[float] = None,
                         page: int = Query(1, ge=1), per_page: int = Query(25, ge=1, le=100)):
        if p.is_service:
            require(p, scope="qa:read")
        f, t = _range(frm, to)
        with db.session() as ss:
            evs = ss.execute(_ai_query(p, f, t, agent, team, status, review).order_by(QaEvaluation.id.desc())).scalars().all()
            humans = _latest_human(ss, [e.id for e in evs])
            tasks = dict(ss.execute(select(ReviewTask.evaluation_id, func.count()).where(
                ReviewTask.tenant_id == p.tenant, ReviewTask.status.in_(("open", "in_progress")),
                ReviewTask.evaluation_id.in_([e.id for e in evs] or [0])).group_by(ReviewTask.evaluation_id)).all())
            rows = [_ev_row(e, humans.get(e.id), tasks.get(e.id, 0)) for e in evs]
        if review:
            rows = [r for r in rows if r["review_state"] == review]
        if min_score is not None:
            rows = [r for r in rows if r["final_score"] is not None and r["final_score"] >= min_score]
        if max_score is not None:
            rows = [r for r in rows if r["final_score"] is not None and r["final_score"] <= max_score]
        total = len(rows)
        return {"total": total, "page": page, "per_page": per_page,
                "items": rows[(page - 1) * per_page: page * per_page]}

    def _criteria(ss, ev_id):
        return [{"key": c.criterion_key, "label": c.label, "weight": c.weight, "effective_weight": c.effective_weight,
                 "status": c.status, "score": c.score, "justification": c.justification,
                 "evidence_text": c.evidence_text, "evidence_start_s": c.evidence_start_s,
                 "evidence_end_s": c.evidence_end_s, "evidence_segment_idx": c.evidence_segment_idx,
                 "evidence_verified": c.evidence_verified, "confidence": c.confidence, "suggestion": c.suggestion,
                 "flags": c.flags}
                for c in ss.execute(select(QaCriterionScore).where(QaCriterionScore.evaluation_id == ev_id)
                                    .order_by(QaCriterionScore.id)).scalars()]

    def _segments(ss, tr_id):
        return [{"idx": g.idx, "start_s": g.start_s, "end_s": g.end_s, "speaker": g.speaker, "channel": g.channel,
                 "text": g.text_masked, "confidence": g.confidence, "low_confidence": g.low_confidence}
                for g in ss.execute(select(TranscriptionSegment).where(TranscriptionSegment.transcription_id == tr_id)
                                    .order_by(TranscriptionSegment.idx)).scalars()]

    def _tr_meta(tr: Transcription):
        return {"id": tr.id, "status": tr.status, "provider": tr.provider, "model": tr.model, "language": tr.language,
                "language_probability": tr.language_probability, "audio_duration_s": tr.audio_duration_s,
                "coverage_ratio": tr.coverage_ratio, "avg_confidence": tr.avg_confidence,
                "low_confidence_ratio": tr.low_confidence_ratio, "diarization": tr.diarization,
                "pii_counts": tr.pii_counts, "warnings": tr.warnings, "run": tr.run, "rtf": tr.rtf,
                "created_at": _iso(tr.created_at)}

    def _summary(sm: Optional[CallSummary]):
        if sm is None:
            return None
        return {"id": sm.id, "status": sm.status, "content": sm.content, "final_content": sm.final_content,
                "llm_provider": sm.llm_provider, "llm_model": sm.llm_model, "prompt_version_id": sm.prompt_version_id,
                "reviewed_by": sm.reviewed_by, "reviewed_at": _iso(sm.reviewed_at), "note_status": sm.note_status,
                "note_message_id": sm.note_message_id}

    @app.get(f"{PREFIX}/evaluations/{{ev_id}}")
    def get_evaluation(ev_id: int, request: Request, p: Principal = Depends(me)):
        if p.is_service:
            require(p, scope="qa:read")
        with db.session() as ss:
            ev = ev_visible(ss, p, ev_id)
            if ev.source == "human" and ev.parent_evaluation_id:
                ev = ss.get(QaEvaluation, ev.parent_evaluation_id)
            tr = ss.get(Transcription, ev.transcription_id)
            humans = ss.execute(select(QaEvaluation).where(QaEvaluation.parent_evaluation_id == ev.id)
                                .order_by(QaEvaluation.id)).scalars().all()
            rv = ss.get(RubricVersion, ev.rubric_version_id)
            pv = ss.get(PromptVersion, ev.prompt_version_id) if ev.prompt_version_id else None
            sm = ss.execute(select(CallSummary).where(CallSummary.job_id == ev.job_id)).scalar_one_or_none()
            tasks = ss.execute(select(ReviewTask).where(ReviewTask.evaluation_id == ev.id).order_by(ReviewTask.id)).scalars().all()
            events = ss.execute(select(QaReviewEvent).where(QaReviewEvent.evaluation_id == ev.id)
                                .order_by(QaReviewEvent.id)).scalars().all()
            history = ss.execute(select(QaEvaluation).where(QaEvaluation.tenant_id == p.tenant,
                                                            QaEvaluation.recording_id == ev.recording_id,
                                                            QaEvaluation.source == "ai").order_by(QaEvaluation.id)).scalars().all()
            out = {**_ev_row(ev, humans[-1] if humans else None, sum(t.status in ("open", "in_progress") for t in tasks)),
                   "applicable_weight": ev.applicable_weight, "redistribution": ev.redistribution,
                   "warnings": ev.warnings, "criteria": _criteria(ss, ev.id), "stt_model": ev.stt_model,
                   "human_reviews": [{"id": h.id, "score": _num(h.score), "status": h.status, "reviewer": h.reviewer_ref,
                                      "comment": h.comment, "created_at": _iso(h.created_at),
                                      "criteria": _criteria(ss, h.id)} for h in humans],
                   "rubric": {"id": rv.id, "code": rv.code, "version": rv.version, "name": rv.name},
                   "prompt": {"id": pv.id, "kind": pv.kind, "version": pv.version, "sha256": pv.sha256} if pv else None,
                   "transcription": _tr_meta(tr), "segments": _segments(ss, tr.id), "summary": _summary(sm),
                   "tasks": [_task(t) for t in tasks],
                   "events": [{"type": e.event_type, "actor": e.actor_ref, "role": e.actor_role, "payload": e.payload,
                               "created_at": _iso(e.created_at)} for e in events],
                   "history": [{"id": h.id, "score": _num(h.score), "status": h.status, "is_current": h.is_current,
                                "llm_model": h.llm_model, "rubric_version_id": h.rubric_version_id,
                                "prompt_version_id": h.prompt_version_id, "created_at": _iso(h.created_at)} for h in history]}
            log_access(ss, p, "evaluation_view", request, ev.recording_id, ev.id)
            return out

    def _human_eval(ss, p: Principal, ai: QaEvaluation, items: List[CriterionIn], comment: Optional[str], status: str):
        base = {c.criterion_key: c for c in ss.execute(select(QaCriterionScore).where(
            QaCriterionScore.evaluation_id == ai.id)).scalars()}
        given = {c.key: c for c in items}
        unknown = set(given) - set(base)
        if unknown:
            raise HTTPException(422, detail={"error": "unknown_criteria", "message": f"critérios inválidos: {sorted(unknown)}"})
        results = []
        for key, b in base.items():
            g = given.get(key)
            if g is not None and g.status == "observed" and g.score is None:
                raise HTTPException(422, detail={"error": "score_required", "message": f"nota obrigatória em {key}"})
            results.append(CriterionResult(
                key=key, label=b.label, weight=b.weight, status=g.status if g else b.status,
                score=(g.score if g else b.score), justification=mask_text(g.justification or "") if g else b.justification,
                evidence_text=b.evidence_text, evidence_start_s=b.evidence_start_s, evidence_end_s=b.evidence_end_s,
                evidence_segment_idx=b.evidence_segment_idx, evidence_verified=b.evidence_verified,
                confidence=1.0 if g else b.confidence, suggestion=b.suggestion, flags=["revisado_humano"] if g else []))
        sc = compute_score(results, s.min_applicable_weight)
        h = QaEvaluation(tenant_id=p.tenant, transcription_id=ai.transcription_id, parent_evaluation_id=ai.id,
                         recording_id=ai.recording_id, call_id=ai.call_id, ticket_id=ai.ticket_id,
                         conversation_id=ai.conversation_id, agent_ref=ai.agent_ref, agent_name=ai.agent_name, team=ai.team,
                         source="human", status=status, score=sc["score"], applicable_weight=sc["applicable_weight"],
                         redistribution=sc["redistribution"], confidence=1.0, rubric_version_id=ai.rubric_version_id,
                         reviewer_ref=p.ref, comment=mask_text(comment or "") or None, is_current=True)
        ss.add(h)
        ss.flush()
        for r in results:
            ss.add(QaCriterionScore(evaluation_id=h.id, criterion_key=r.key, label=r.label, weight=r.weight,
                                    effective_weight=r.effective_weight, status=r.status, score=r.score,
                                    justification=r.justification, evidence_text=r.evidence_text,
                                    evidence_start_s=r.evidence_start_s, evidence_end_s=r.evidence_end_s,
                                    evidence_segment_idx=r.evidence_segment_idx, evidence_verified=r.evidence_verified,
                                    confidence=r.confidence, suggestion=r.suggestion, flags=r.flags or []))
        diff = {r.key: {"ia": base[r.key].score, "humano": r.score, "status_ia": base[r.key].status, "status_humano": r.status}
                for r in results if r.key in given}
        return h, sc, diff

    @app.post(f"{PREFIX}/evaluations/{{ev_id}}/review")
    def review(ev_id: int, body: ReviewIn, p: Principal = Depends(me)):
        require(p, "supervisor", "qa")
        with db.session() as ss:
            ai = ev_visible(ss, p, ev_id)
            if ai.source != "ai":
                raise HTTPException(409, detail={"error": "not_ai", "message": "revise a avaliação da IA"})
            h, sc, diff = _human_eval(ss, p, ai, body.criteria, body.comment, "reviewed")
            ss.add(QaReviewEvent(tenant_id=p.tenant, evaluation_id=ai.id, recording_id=ai.recording_id,
                                 event_type="reviewed", actor_ref=p.ref, actor_role=",".join(sorted(p.roles)),
                                 payload={"human_evaluation_id": h.id, "ai_score": _num(ai.score), "human_score": sc["score"],
                                          "diff": diff, "comment": h.comment}))
            for t in ss.execute(select(ReviewTask).where(ReviewTask.evaluation_id == ai.id,
                                                         ReviewTask.kind.in_(("qa_low_score", "qa_insufficient_evidence")),
                                                         ReviewTask.status.in_(("open", "in_progress")))).scalars():
                t.status, t.resolved_by, t.resolved_at, t.resolution = "done", p.ref, datetime.now(timezone.utc), "revisão humana registrada"
            return {"human_evaluation_id": h.id, "score": sc["score"], "redistribution": sc["redistribution"]}

    @app.post(f"{PREFIX}/evaluations/{{ev_id}}/contest")
    def contest(ev_id: int, body: ContestIn, p: Principal = Depends(me)):
        with db.session() as ss:
            ai = ev_visible(ss, p, ev_id)
            if ai.agent_ref != p.ref and not p.has("supervisor"):
                raise HTTPException(403, detail={"error": "forbidden", "message": "só o agente avaliado ou o supervisor contesta"})
            if ai.status == "contested":
                raise HTTPException(409, detail={"error": "already_contested", "message": "contestação já em aberto"})
            ai.status = "contested"
            reason = mask_text(body.reason)
            ss.add(QaReviewEvent(tenant_id=p.tenant, evaluation_id=ai.id, recording_id=ai.recording_id,
                                 event_type="contested", actor_ref=p.ref, actor_role=",".join(sorted(p.roles)),
                                 payload={"reason": reason}))
            n = ss.execute(select(func.count()).select_from(QaReviewEvent).where(
                QaReviewEvent.evaluation_id == ai.id, QaReviewEvent.event_type == "contested")).scalar()
            ss.add(ReviewTask(tenant_id=p.tenant, dedupe_key=f"{p.tenant}:contest:{ai.id}:{n + 1}", kind="contest",
                              severity="media", title="Contestação de avaliação de QA", detail=reason,
                              evaluation_id=ai.id, job_id=ai.job_id, recording_id=ai.recording_id, call_id=ai.call_id,
                              ticket_id=ai.ticket_id, conversation_id=ai.conversation_id, agent_ref=ai.agent_ref))
            return {"status": "contested"}

    @app.post(f"{PREFIX}/evaluations/{{ev_id}}/contest/resolve")
    def resolve_contest(ev_id: int, body: ContestResolveIn, p: Principal = Depends(me)):
        require(p, "supervisor", "qa")
        with db.session() as ss:
            ai = ev_visible(ss, p, ev_id)
            if ai.status != "contested":
                raise HTTPException(409, detail={"error": "not_contested", "message": "não há contestação em aberto"})
            payload = {"decision": body.decision, "comment": mask_text(body.comment)}
            if body.decision == "revised":
                h, sc, diff = _human_eval(ss, p, ai, body.criteria, body.comment, "contest_revised")
                payload.update({"human_evaluation_id": h.id, "score": sc["score"], "diff": diff})
            ai.status = "contest_upheld" if body.decision == "upheld" else "contest_revised"
            ss.add(QaReviewEvent(tenant_id=p.tenant, evaluation_id=ai.id, recording_id=ai.recording_id,
                                 event_type="contest_resolved", actor_ref=p.ref, actor_role=",".join(sorted(p.roles)),
                                 payload=payload))
            for t in ss.execute(select(ReviewTask).where(ReviewTask.evaluation_id == ai.id, ReviewTask.kind == "contest",
                                                         ReviewTask.status.in_(("open", "in_progress")))).scalars():
                t.status, t.resolved_by, t.resolved_at, t.resolution = "done", p.ref, datetime.now(timezone.utc), body.decision
            return {"status": ai.status}

    # ------------------------------------------------------------ gravações
    def _job_visible(ss, p: Principal, recording_id: str) -> Job:
        job = ss.execute(select(Job).where(Job.tenant_id == p.tenant, Job.recording_id == recording_id)
                         .order_by(Job.run.desc())).scalars().first()
        if job is None:
            raise _nf()
        if not p.is_manager and job.agent_ref != p.ref:
            raise _nf()
        return job

    @app.get(f"{PREFIX}/recordings/{{recording_id}}/analysis")
    def recording_analysis(recording_id: str, request: Request, p: Principal = Depends(me)):
        """Tudo que o pós-atendimento do CTI precisa: estado do job, transcrição, resumo, QA e alertas."""
        with db.session() as ss:
            job = _job_visible(ss, p, recording_id)
            tr = ss.execute(select(Transcription).where(Transcription.tenant_id == p.tenant,
                                                        Transcription.recording_id == recording_id,
                                                        Transcription.is_current.is_(True))).scalar_one_or_none()
            ev = ss.execute(select(QaEvaluation).where(QaEvaluation.tenant_id == p.tenant,
                                                       QaEvaluation.recording_id == recording_id,
                                                       QaEvaluation.source == "ai",
                                                       QaEvaluation.is_current.is_(True))).scalar_one_or_none()
            sm = ss.execute(select(CallSummary).where(CallSummary.tenant_id == p.tenant,
                                                      CallSummary.recording_id == recording_id,
                                                      CallSummary.is_current.is_(True))).scalar_one_or_none()
            alerts = ss.execute(select(ReviewTask).where(ReviewTask.tenant_id == p.tenant,
                                                         ReviewTask.recording_id == recording_id,
                                                         ReviewTask.kind == "alert",
                                                         ReviewTask.job_id == (ev.job_id if ev else -1))).scalars().all()
            humans = _latest_human(ss, [ev.id]) if ev else {}
            csat = None
            if job.conversation_id or job.call_id:
                cq = select(CsatResponse).where(CsatResponse.tenant_id == p.tenant)
                cq = cq.where(CsatResponse.call_id == job.call_id) if job.call_id else cq.where(
                    CsatResponse.conversation_id == job.conversation_id)
                c = ss.execute(cq.order_by(CsatResponse.id.desc())).scalars().first()
                if c is None and job.conversation_id:
                    c = ss.execute(select(CsatResponse).where(CsatResponse.tenant_id == p.tenant,
                                                              CsatResponse.conversation_id == job.conversation_id)
                                   .order_by(CsatResponse.id.desc())).scalars().first()
                if c:
                    csat = {"score": c.score, "scale_max": c.scale_max, "comment": c.comment_masked,
                            "responded_at": _iso(c.responded_at), "source": c.source}
            if tr:
                log_access(ss, p, "transcript_view", request, recording_id)
            return {"recording_id": recording_id, "call_id": job.call_id, "conversation_id": job.conversation_id,
                    "job": {"id": job.id, "run": job.run, "status": job.status, "stage": job.stage,
                            "error_code": job.error_code, "attempts": job.attempts,
                            "next_attempt_at": _iso(job.next_attempt_at), "timings": job.timings},
                    "transcription": _tr_meta(tr) if tr else None, "segments": _segments(ss, tr.id) if tr else [],
                    "summary": _summary(sm),
                    "evaluation": (_ev_row(ev, humans.get(ev.id), 0) | {"criteria": _criteria(ss, ev.id),
                                                                         "redistribution": ev.redistribution})
                    if ev else None,
                    "alerts": [_task(a) for a in alerts], "csat": csat}

    @app.get(f"{PREFIX}/calls/{{call_id}}/recordings")
    def call_recordings(call_id: str, p: Principal = Depends(me)):
        with db.session() as ss:
            q = select(Job.recording_id, func.max(Job.run), func.max(Job.agent_ref)).where(
                Job.tenant_id == p.tenant, Job.call_id == call_id).group_by(Job.recording_id)
            rows = ss.execute(q).all()
            return {"items": [{"recording_id": r[0], "runs": r[1]} for r in rows if p.is_manager or r[2] == p.ref]}

    @app.post(f"{PREFIX}/recordings/{{recording_id}}/reprocess", status_code=202)
    def reprocess(recording_id: str, body: ReprocessIn, p: Principal = Depends(me)):
        require(p, "supervisor", "qa", scope="qa:write")
        with db.session() as ss:
            _job_visible(ss, p, recording_id)
        try:
            job = pipe.request_reprocess(p.tenant, recording_id, body.mode, p.ref, ",".join(sorted(p.roles)) or "servico",
                                         mask_text(body.reason))
        except LookupError as exc:
            raise HTTPException(409, detail={"error": "cannot_reprocess", "message": str(exc)})
        return {"job_id": job.id, "run": job.run, "status": job.status, "mode": job.mode}

    @app.get(f"{PREFIX}/recordings/{{recording_id}}/marks")
    def list_marks(recording_id: str, p: Principal = Depends(me)):
        with db.session() as ss:
            _job_visible(ss, p, recording_id)
            rows = ss.execute(select(RecordingMark).where(RecordingMark.tenant_id == p.tenant,
                                                          RecordingMark.recording_id == recording_id,
                                                          RecordingMark.deleted_at.is_(None))
                              .order_by(RecordingMark.start_s)).scalars().all()
            return {"items": [{"id": m.id, "start_s": m.start_s, "end_s": m.end_s, "label": m.label, "note": m.note,
                               "created_by": m.created_by, "created_at": _iso(m.created_at)} for m in rows]}

    @app.post(f"{PREFIX}/recordings/{{recording_id}}/marks", status_code=201)
    def add_mark(recording_id: str, body: MarkIn, request: Request, p: Principal = Depends(me)):
        if body.end_s is not None and body.end_s < body.start_s:
            raise HTTPException(422, detail={"error": "bad_range", "message": "fim antes do início"})
        with db.session() as ss:
            _job_visible(ss, p, recording_id)
            m = RecordingMark(tenant_id=p.tenant, recording_id=recording_id, start_s=body.start_s, end_s=body.end_s,
                              label=mask_text(body.label), note=mask_text(body.note or "") or None, created_by=p.ref)
            ss.add(m)
            ss.flush()
            log_access(ss, p, "mark", request, recording_id, detail={"mark_id": m.id, "start_s": body.start_s})
            return {"id": m.id}

    @app.delete(f"{PREFIX}/recordings/{{recording_id}}/marks/{{mark_id}}", status_code=204)
    def del_mark(recording_id: str, mark_id: int, p: Principal = Depends(me)):
        with db.session() as ss:
            m = ss.get(RecordingMark, mark_id)
            if m is None or m.tenant_id != p.tenant or m.recording_id != recording_id or m.deleted_at:
                raise _nf()
            if m.created_by != p.ref and not p.is_manager:
                raise HTTPException(403, detail={"error": "forbidden", "message": "só o autor remove"})
            m.deleted_at = datetime.now(timezone.utc)
        return Response(status_code=204)

    @app.post(f"{PREFIX}/access-log", status_code=201)
    def access(body: AccessIn, request: Request, p: Principal = Depends(me)):
        with db.session() as ss:
            _job_visible(ss, p, body.recording_id)
            detail = {k: v for k, v in (body.detail or {}).items() if k in ("position_s", "rate", "from_s", "to_s")}
            log_access(ss, p, body.action, request, body.recording_id, detail=detail)
        return {"ok": True}

    @app.get(f"{PREFIX}/access-log")
    def access_list(recording_id: str, p: Principal = Depends(me)):
        require(p, "supervisor", "qa")
        with db.session() as ss:
            rows = ss.execute(select(AccessLog).where(AccessLog.tenant_id == p.tenant, AccessLog.recording_id == recording_id)
                              .order_by(AccessLog.id.desc()).limit(500)).scalars().all()
            return {"items": [{"action": a.action, "actor": a.actor_ref, "role": a.actor_role, "detail": a.detail,
                               "created_at": _iso(a.created_at)} for a in rows]}

    # ------------------------------------------------------------ resumo
    @app.post(f"{PREFIX}/summaries/{{summary_id}}/review")
    def review_summary(summary_id: int, body: SummaryReviewIn, p: Principal = Depends(me)):
        with db.session() as ss:
            sm = ss.get(CallSummary, summary_id)
            if sm is None or sm.tenant_id != p.tenant:
                raise _nf()
            job = ss.get(Job, sm.job_id)
            if not p.is_manager and job.agent_ref != p.ref:
                raise _nf()
            if body.action == "edit" and not body.content:
                raise HTTPException(422, detail={"error": "content_required", "message": "envie o conteúdo editado"})
            sm.status = {"approve": "approved", "edit": "edited", "reject": "rejected"}[body.action]
            if body.action == "edit":
                sm.final_content = _mask_obj(body.content)
            elif body.action == "approve":
                sm.final_content = sm.content
            sm.reviewed_by, sm.reviewed_at = p.ref, datetime.now(timezone.utc)
            ss.add(QaReviewEvent(tenant_id=p.tenant, summary_id=sm.id, recording_id=sm.recording_id,
                                 event_type=f"summary_{sm.status}", actor_ref=p.ref,
                                 actor_role=",".join(sorted(p.roles)), payload={"comment": mask_text(body.comment or "")}))
            return _summary(sm)

    # ------------------------------------------------------------ tarefas
    @app.get(f"{PREFIX}/review-tasks")
    def tasks(p: Principal = Depends(me), status: Optional[str] = "open", kind: Optional[str] = None,
              page: int = Query(1, ge=1), per_page: int = Query(50, ge=1, le=200)):
        with db.session() as ss:
            q = select(ReviewTask).where(ReviewTask.tenant_id == p.tenant)
            if status and status != "all":
                q = q.where(ReviewTask.status == status)
            if kind:
                q = q.where(ReviewTask.kind == kind)
            if not p.is_manager:
                q = q.where(ReviewTask.agent_ref == p.ref)
            total = ss.execute(select(func.count()).select_from(q.subquery())).scalar()
            rows = ss.execute(q.order_by(ReviewTask.id.desc()).offset((page - 1) * per_page).limit(per_page)).scalars().all()
            return {"total": total, "items": [_task(t) for t in rows]}

    @app.patch(f"{PREFIX}/review-tasks/{{task_id}}")
    def patch_task(task_id: int, body: TaskPatchIn, p: Principal = Depends(me)):
        require(p, "supervisor", "qa", scope="qa:write")
        with db.session() as ss:
            t = ss.get(ReviewTask, task_id)
            if t is None or t.tenant_id != p.tenant:
                raise _nf()
            if body.assigned_to is not None:
                t.assigned_to = body.assigned_to or None
            if body.resolution is not None:
                t.resolution = mask_text(body.resolution)
            if body.status:
                t.status = body.status
                if body.status in ("done", "dismissed"):
                    t.resolved_by, t.resolved_at = p.ref, datetime.now(timezone.utc)
            ss.add(QaReviewEvent(tenant_id=p.tenant, evaluation_id=t.evaluation_id, recording_id=t.recording_id,
                                 event_type="task_updated", actor_ref=p.ref, actor_role=",".join(sorted(p.roles)) or "servico",
                                 payload={"task_id": t.id, **body.model_dump(exclude_none=True)}))
            return _task(t)

    # ------------------------------------------------------------ rubricas
    @app.get(f"{PREFIX}/rubrics")
    def rubrics(p: Principal = Depends(me)):
        with db.session() as ss:
            db.active_rubric(ss, p.tenant, s.rubric_code)
            rows = ss.execute(select(RubricVersion).where(RubricVersion.tenant_id == p.tenant)
                              .order_by(RubricVersion.code, RubricVersion.version.desc())).scalars().all()
            used = dict(ss.execute(select(QaEvaluation.rubric_version_id, func.count()).where(
                QaEvaluation.tenant_id == p.tenant).group_by(QaEvaluation.rubric_version_id)).all())
            return {"items": [{"id": r.id, "code": r.code, "version": r.version, "name": r.name, "active": r.active,
                               "criteria": r.criteria, "mandatory_phrases": r.mandatory_phrases,
                               "redistribution_rule": r.redistribution_rule, "created_by": r.created_by,
                               "created_at": _iso(r.created_at), "evaluations": used.get(r.id, 0)} for r in rows]}

    @app.post(f"{PREFIX}/rubrics", status_code=201)
    def new_rubric(body: RubricIn, p: Principal = Depends(me)):
        require(p, "qa")
        try:
            validate_rubric(body.criteria)
        except (ValueError, KeyError) as exc:
            raise HTTPException(422, detail={"error": "invalid_rubric", "message": str(exc)})
        with db.session() as ss:
            cur = db.active_rubric(ss, p.tenant, s.rubric_code)
            last = ss.execute(select(func.max(RubricVersion.version)).where(
                RubricVersion.tenant_id == p.tenant, RubricVersion.code == cur.code)).scalar()
            rv = RubricVersion(tenant_id=p.tenant, code=cur.code, version=last + 1, name=body.name,
                               criteria=body.criteria, mandatory_phrases=body.mandatory_phrases,
                               redistribution_rule=cur.redistribution_rule, active=False, created_by=p.ref)
            ss.add(rv)
            ss.flush()
            ss.add(QaReviewEvent(tenant_id=p.tenant, event_type="rubric_created", actor_ref=p.ref,
                                 actor_role=",".join(sorted(p.roles)), payload={"rubric_id": rv.id, "version": rv.version}))
            return {"id": rv.id, "version": rv.version, "active": False}

    @app.post(f"{PREFIX}/rubrics/{{rubric_id}}/activate")
    def activate_rubric(rubric_id: int, p: Principal = Depends(me)):
        require(p, "qa")
        with db.session() as ss:
            rv = ss.get(RubricVersion, rubric_id)
            if rv is None or rv.tenant_id != p.tenant:
                raise _nf()
            for other in ss.execute(select(RubricVersion).where(RubricVersion.tenant_id == p.tenant,
                                                                RubricVersion.code == rv.code)).scalars():
                other.active = other.id == rv.id
            ss.add(QaReviewEvent(tenant_id=p.tenant, event_type="rubric_activated", actor_ref=p.ref,
                                 actor_role=",".join(sorted(p.roles)), payload={"rubric_id": rv.id, "version": rv.version}))
            return {"id": rv.id, "active": True}

    @app.get(f"{PREFIX}/prompts")
    def prompt_versions(p: Principal = Depends(me)):
        with db.session() as ss:
            db.ensure_prompt(ss, "qa")
            db.ensure_prompt(ss, "summary")
            rows = ss.execute(select(PromptVersion).order_by(PromptVersion.kind, PromptVersion.id)).scalars().all()
            return {"items": [{"id": r.id, "kind": r.kind, "version": r.version, "sha256": r.sha256,
                               "created_at": _iso(r.created_at), "template": r.template if p.is_manager else None}
                              for r in rows]}

    # ------------------------------------------------------------ métricas
    def _quality(p: Principal, frm, to, agent, team):
        f, t = _range(frm, to)
        with db.session() as ss:
            jq = select(Job).where(Job.tenant_id == p.tenant, Job.created_at >= f, Job.created_at < t)
            if agent:
                jq = jq.where(Job.agent_ref == agent)
            if team:
                jq = jq.where(Job.team == team)
            jobs = ss.execute(jq).scalars().all()
            evs = ss.execute(_ai_query(p, f, t, agent, team, None, None)).scalars().all()
            humans = _latest_human(ss, [e.id for e in evs])
            ev_ids = [e.id for e in evs] or [0]
            crit = ss.execute(select(QaCriterionScore).where(QaCriterionScore.evaluation_id.in_(ev_ids))).scalars().all()
            trs = ss.execute(select(Transcription).where(Transcription.tenant_id == p.tenant,
                                                         Transcription.created_at >= f, Transcription.created_at < t)).scalars().all()
            alerts = ss.execute(select(ReviewTask.alert_type, func.count()).where(
                ReviewTask.tenant_id == p.tenant, ReviewTask.kind == "alert", ReviewTask.created_at >= f,
                ReviewTask.created_at < t, ReviewTask.evaluation_id.in_(ev_ids)).group_by(ReviewTask.alert_type)).all()
            open_tasks = ss.execute(select(ReviewTask.kind, func.count()).where(
                ReviewTask.tenant_id == p.tenant, ReviewTask.status.in_(("open", "in_progress")))
                .group_by(ReviewTask.kind)).all()
            cq = select(CsatResponse).where(CsatResponse.tenant_id == p.tenant, CsatResponse.created_at >= f,
                                            CsatResponse.created_at < t)
            if agent:
                cq = cq.where(CsatResponse.agent_ref == agent)
            csats = ss.execute(cq).scalars().all()
        first_runs = [j for j in jobs if j.run == 1]
        done = [j for j in first_runs if j.status == "done"]
        failed = [j for j in first_runs if j.status == "failed"]
        in_progress = [j for j in first_runs if j.status in ("pending", "running", "waiting_audio")]
        rtfs = [tr.rtf for tr in trs if tr.rtf]
        audio_min = sum((tr.audio_duration_s or 0) for tr in trs) / 60
        scores = [float(e.score) for e in evs if e.score is not None]
        finals = [float(humans[e.id].score) if e.id in humans and humans[e.id].score is not None else
                  (float(e.score) if e.score is not None else None) for e in evs]
        finals = [x for x in finals if x is not None]
        buckets = Counter()
        for x in finals:
            b = "0-49" if x < 50 else ("90-100" if x >= 90 else f"{int(x // 10) * 10}-{int(x // 10) * 10 + 9}")
            buckets[b] += 1
        per_crit = defaultdict(lambda: {"aplicavel": 0, "falhas": 0, "nao_aplicavel": 0, "soma": 0.0, "label": ""})
        for c in crit:
            d = per_crit[c.criterion_key]
            d["label"] = c.label
            if c.status == "not_applicable":
                d["nao_aplicavel"] += 1
                continue
            d["aplicavel"] += 1
            d["soma"] += float(c.score or 0)
            if c.status == "not_observed" or (c.score is not None and c.score < 60):
                d["falhas"] += 1
        criteria_rank = sorted(({"key": k, "label": v["label"], "aplicavel": v["aplicavel"], "falhas": v["falhas"],
                                 "nao_aplicavel": v["nao_aplicavel"],
                                 "taxa_falha": round(v["falhas"] / v["aplicavel"], 3) if v["aplicavel"] else None,
                                 "media": round(v["soma"] / v["aplicavel"], 1) if v["aplicavel"] else None}
                                for k, v in per_crit.items()), key=lambda r: -(r["taxa_falha"] or 0))
        pairs = [(float(e.score), float(humans[e.id].score)) for e in evs
                 if e.id in humans and e.score is not None and humans[e.id].score is not None]
        div = [abs(a - b) for a, b in pairs]
        series = defaultdict(list)
        for e in evs:
            if e.score is not None:
                series[e.created_at.astimezone(timezone.utc).date().isoformat()].append(float(e.score))
        alert_counts = dict(alerts)
        csat_scores = [c.score / c.scale_max for c in csats]
        return {
            "periodo": {"from": _iso(f), "to": _iso(t)},
            "gravacoes_recebidas": len(first_runs), "transcritas": len(done), "falhas": len(failed),
            "em_processamento": len(in_progress),
            "taxa_sucesso": round(len(done) / (len(done) + len(failed)), 3) if (done or failed) else None,
            "transcricoes_parciais": sum(1 for tr in trs if tr.status == "partial"),
            "minutos_audio": round(audio_min, 1),
            "tempo_proc_por_min_audio_s": round(60 * statistics.mean(rtfs), 1) if rtfs else None,
            "avaliacoes": len(evs), "sem_evidencia_suficiente": sum(1 for e in evs if e.status == "insufficient_evidence"),
            "qa_medio_ia": round(statistics.mean(scores), 1) if scores else None,
            "qa_medio_final": round(statistics.mean(finals), 1) if finals else None,
            "distribuicao": {k: buckets.get(k, 0) for k in ("0-49", "50-59", "60-69", "70-79", "80-89", "90-100")},
            "criterios": criteria_rank,
            "revisadas_por_humano": len(humans), "cobertura_revisao": round(len(humans) / len(evs), 3) if evs else None,
            "divergencia_ia_humano": {"pares": len(pairs), "media_abs": round(statistics.mean(div), 1) if div else None,
                                      "acima_de_15": sum(1 for d in div if d > 15)},
            "contestacoes": sum(1 for e in evs if e.status.startswith("contest")),
            "reclamacoes": alert_counts.get("reclamacao", 0), "retornos_prometidos": alert_counts.get("compromisso_retorno", 0),
            "alertas": alert_counts, "tarefas_abertas": dict(open_tasks),
            "csat": {"respostas": len(csats), "media_pct": round(100 * statistics.mean(csat_scores), 1) if csat_scores else None,
                     "satisfeitos_pct": round(100 * sum(1 for x in csat_scores if x >= 0.8) / len(csat_scores), 1)
                     if csat_scores else None},
            "custo_ia": {"llm_provider": s.llm_provider, "stt_provider": s.stt_provider,
                         "estimado_brl": 0.0 if s.llm_provider in ("mock", "local") and s.stt_provider != "openai" else None,
                         "nota": "local/mock: sem custo por uso; ver COST_ESTIMATE-IA.md"},
            "serie_diaria": [{"dia": d, "avaliacoes": len(v), "qa_medio": round(statistics.mean(v), 1)}
                             for d, v in sorted(series.items())],
        }

    @app.get(f"{PREFIX}/metrics/quality")
    def quality(p: Principal = Depends(me), frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
                agent: Optional[str] = None, team: Optional[str] = None):
        if not p.is_manager:
            agent = p.ref  # agente vê só o próprio painel
        return _quality(p, frm, to, agent, team)

    @app.get(f"{PREFIX}/agents/stats")
    def agent_stats(p: Principal = Depends(me), frm: Optional[str] = Query(None, alias="from"), to: Optional[str] = None,
                    team: Optional[str] = None):
        require(p, "supervisor", "qa", scope="qa:read")
        f, t = _range(frm, to)
        with db.session() as ss:
            evs = ss.execute(_ai_query(p, f, t, None, team, None, None)).scalars().all()
            humans = _latest_human(ss, [e.id for e in evs])
            crit = ss.execute(select(QaCriterionScore).where(QaCriterionScore.evaluation_id.in_([e.id for e in evs] or [0]))).scalars().all()
        by_ev = defaultdict(list)
        for c in crit:
            by_ev[c.evaluation_id].append(c)
        agg = defaultdict(lambda: {"n": 0, "ia": [], "humano": [], "div": [], "falhas": Counter(), "contestacoes": 0,
                                   "nome": None, "time": None})
        for e in evs:
            a = agg[e.agent_ref or "(não identificado)"]
            a["n"] += 1
            a["nome"] = a["nome"] or e.agent_name
            a["time"] = a["time"] or e.team
            if e.score is not None:
                a["ia"].append(float(e.score))
            h = humans.get(e.id)
            if h is not None and h.score is not None:
                a["humano"].append(float(h.score))
                if e.score is not None:
                    a["div"].append(abs(float(e.score) - float(h.score)))
            if e.status.startswith("contest"):
                a["contestacoes"] += 1
            for c in by_ev[e.id]:
                if c.status == "not_observed" or (c.score is not None and c.score < 60):
                    a["falhas"][c.label] += 1
        items = []
        for ref, a in agg.items():
            items.append({"agent_ref": ref, "agent_name": a["nome"], "team": a["time"], "avaliacoes": a["n"],
                          "qa_medio_ia": round(statistics.mean(a["ia"]), 1) if a["ia"] else None,
                          "qa_medio_humano": round(statistics.mean(a["humano"]), 1) if a["humano"] else None,
                          "divergencia_media": round(statistics.mean(a["div"]), 1) if a["div"] else None,
                          "contestacoes": a["contestacoes"],
                          "criterios_a_treinar": [k for k, _ in a["falhas"].most_common(3)]})
        items.sort(key=lambda r: (r["qa_medio_ia"] is None, r["qa_medio_ia"] or 0))
        return {"items": items}

    @app.get(f"{PREFIX}/export/evaluations.csv")
    def export_csv(request: Request, p: Principal = Depends(me), frm: Optional[str] = Query(None, alias="from"),
                   to: Optional[str] = None, agent: Optional[str] = None, team: Optional[str] = None):
        require(p, "supervisor", "qa", scope="qa:read")
        data = list_evaluations(p=p, frm=frm, to=to, agent=agent, team=team, status=None, review=None,
                                min_score=None, max_score=None, page=1, per_page=100)
        rows = data["items"]
        page = 2
        while len(rows) < data["total"]:
            rows += list_evaluations(p=p, frm=frm, to=to, agent=agent, team=team, status=None, review=None,
                                     min_score=None, max_score=None, page=page, per_page=100)["items"]
            page += 1
        buf = io.StringIO()
        cols = ["id", "created_at", "agent_ref", "agent_name", "team", "call_id", "ticket_id", "conversation_id",
                "status", "review_state", "ai_score", "human_score", "final_score", "confidence", "llm_model"]
        w = csv.DictWriter(buf, fieldnames=cols, extrasaction="ignore", delimiter=";")
        w.writeheader()
        for r in rows:
            w.writerow({k: ("" if r.get(k) is None else r.get(k)) for k in cols})
        with db.session() as ss:
            log_access(ss, p, "export_csv", request, detail={"rows": len(rows)})
        return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": "attachment; filename=qa_avaliacoes.csv"})

    # ------------------------------------------------------------ CSAT
    @app.post(f"{PREFIX}/csat", status_code=201)
    def csat_in(body: CsatIn, p: Principal = Depends(me)):
        require(p, "admin", scope="csat:write")
        if body.score < 0 or body.score > body.scale_max:
            raise HTTPException(422, detail={"error": "bad_score", "message": "nota fora da escala"})
        r = pipe._on_csat_standalone(p.tenant, body.model_dump())
        return {"result": r}

    return app


def _task(t: ReviewTask) -> dict:
    return {"id": t.id, "kind": t.kind, "alert_type": t.alert_type, "severity": t.severity, "title": t.title,
            "detail": t.detail, "evidence_text": t.evidence_text, "evidence_start_s": t.evidence_start_s,
            "evidence_verified": t.evidence_verified, "evaluation_id": t.evaluation_id, "recording_id": t.recording_id,
            "call_id": t.call_id, "ticket_id": t.ticket_id, "conversation_id": t.conversation_id,
            "agent_ref": t.agent_ref, "status": t.status, "assigned_to": t.assigned_to, "resolution": t.resolution,
            "resolved_by": t.resolved_by, "resolved_at": _iso(t.resolved_at), "created_at": _iso(t.created_at)}


def _mask_obj(o):
    if isinstance(o, dict):
        return {k: _mask_obj(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_mask_obj(v) for v in o]
    if isinstance(o, str):
        return mask_text(o)
    return o
