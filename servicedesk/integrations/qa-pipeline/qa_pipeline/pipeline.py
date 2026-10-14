"""Orquestração: evento -> job idempotente -> STT -> mascaramento -> resumo/QA/alertas -> eventos -> nota.

Garantias:
- Idempotência: evento aplicado uma vez (qa.processed_events); um job por (tenant, recording_id, run);
  reentrega do mesmo recording.stored não cria job novo. Reprocessamento cria run+1 explicitamente e
  troca o "is_current" sem apagar o histórico.
- Checkpoint: se a transcrição do job já existe, um retry não roda o STT de novo.
- Retentativa com backoff exponencial, limite de tentativas, falha permanente vira tarefa humana e
  evento transcription.failed. Jobs presos em "running" (worker morreu) voltam para a fila.
- Áudio atrasado (ainda não no storage): espera com backoff até AUDIO_WAIT_ATTEMPTS.
- Nada de STT/LLM em webhook: tudo aqui roda no worker.
"""
from __future__ import annotations

import logging
import os
import shutil
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import func, select, update

from . import db
from .analysis import AlertResult, Seg, run_qa, run_summary, summary_to_note
from .clients import ChatwootClient, ClientError, SdOpsClient
from .config import Settings
from .events import EventBus, envelope
from .llm import LlmError, LlmProvider
from .models import (CallSummary, CsatResponse, Job, Outbox, ProcessedEvent, QaCriterionScore, QaEvaluation,
                     QaReviewEvent, ReviewTask, Transcription, TranscriptionSegment)
from .pii import mask_segments, mask_text
from .storage import NotFound, Storage, StorageError, sha256_file, sniff_mime, tempdir
from .stt import SttError, SttProvider

log = logging.getLogger("qa_pipeline")

LOW_CONF = 0.45
FAIL_TITLES = {
    "audio_inexistente": "Gravação inexistente: evento sem arquivo",
    "audio_missing": "Gravação não apareceu no storage após as tentativas",
    "audio_integrity": "Gravação corrompida (sha256 diferente do informado)",
    "audio_type": "Tipo de arquivo de áudio não permitido",
    "audio_invalid": "Áudio ilegível pelo motor de transcrição",
    "audio_empty": "Áudio vazio",
    "audio_too_large": "Gravação acima do limite de tamanho/duração",
    "transcription_failed": "Falha de transcrição após as tentativas",
    "analysis_failed": "Falha no resumo/QA após as tentativas",
    "bad_key": "Chave de storage inválida",
    "config": "Configuração inválida do pipeline",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Retry(Exception):
    def __init__(self, code: str, message: str, delay_s: Optional[int] = None, status: str = "pending"):
        super().__init__(message)
        self.code, self.delay_s, self.status = code, delay_s, status


class Permanent(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Pipeline:
    def __init__(self, settings: Settings, stt: Optional[SttProvider] = None, llm: Optional[LlmProvider] = None,
                 storage: Optional[Storage] = None, bus: Optional[EventBus] = None,
                 chatwoot: Optional[ChatwootClient] = None, sdops: Optional[SdOpsClient] = None):
        self.s = settings
        self._stt, self._llm = stt, llm
        self.storage, self.bus, self.chatwoot, self.sdops = storage, bus, chatwoot, sdops
        self.worker_id = f"{settings.consumer_name}:{os.getpid()}"

    @property
    def stt(self) -> SttProvider:
        if self._stt is None:
            from .stt import build_stt
            self._stt = build_stt(self.s)
        return self._stt

    @property
    def llm(self) -> LlmProvider:
        if self._llm is None:
            from .llm import build_llm
            self._llm = build_llm(self.s)
        return self._llm

    # ------------------------------------------------------------------ eventos
    def handle_event(self, ev: dict, stream_id: Optional[str] = None) -> str:
        typ, p = ev["type"], ev.get("payload") or {}
        tenant = ev.get("tenant_id") or p.get("tenant_id") or self.s.tenant_default
        if typ == "recording.stored":
            key = f"recording.stored:{tenant}:{p.get('recording_id')}:{p.get('sha256') or ''}"
        else:
            key = f"{typ}:{ev.get('event_id') or stream_id}"
        with db.session() as s:
            if s.execute(select(ProcessedEvent.id).where(ProcessedEvent.event_key == key)).first():
                return "duplicate"
            if typ == "recording.stored":
                result = self._on_recording(s, tenant, p, ev)
            elif typ == "csat.recorded":
                result = self._on_csat(s, tenant, p)
            elif typ == "qa.reprocess.requested":
                job = self._reprocess(s, tenant, str(p.get("recording_id") or ""), p.get("mode") or "full",
                                      p.get("requested_by") or "evento", "system", p.get("reason") or "")
                result = f"job:{job.id}"
            else:
                result = "ignored"
            s.add(ProcessedEvent(event_key=key[:200], event_type=typ, stream_id=stream_id, result=result[:64]))
        return result

    def _on_recording(self, s, tenant: str, p: dict, ev: dict) -> str:
        rec = str(p.get("recording_id") or "").strip()
        if not rec:
            return "invalid:no_recording_id"
        existing = s.execute(select(Job).where(Job.tenant_id == tenant, Job.recording_id == rec, Job.run == 1)).scalar_one_or_none()
        if existing:
            return f"job:{existing.id}:existing"
        job = Job(tenant_id=tenant, recording_id=rec, run=1, mode="full",
                  call_id=_s(p.get("call_id")), ticket_id=_s(p.get("ticket_id")), conversation_id=_s(p.get("conversation_id")),
                  agent_ref=_s(p.get("agent_email") or p.get("agent_id")), agent_name=_s(p.get("agent_name")),
                  team=_s(p.get("team") or p.get("queue")), storage_key=_s(p.get("storage_key")), mime=_s(p.get("mime")),
                  duration_s=_f(p.get("duration_s")), sha256=_s(p.get("sha256")),
                  correlation_id=_s(ev.get("correlation_id")) or _s(p.get("call_id")) or rec,
                  source_event_id=_s(ev.get("event_id")))
        s.add(job)
        s.flush()
        return f"job:{job.id}"

    def _on_csat(self, s, tenant: str, p: dict) -> str:
        ext = _s(p.get("csat_id") or p.get("id") or p.get("external_id"))
        if not ext or p.get("score") is None:
            return "invalid:csat"
        src = _s(p.get("source")) or "chatwoot"
        row = s.execute(select(CsatResponse).where(CsatResponse.tenant_id == tenant, CsatResponse.source == src,
                                                   CsatResponse.external_id == ext)).scalar_one_or_none()
        if row is None:
            row = CsatResponse(tenant_id=tenant, source=src, external_id=ext)
            s.add(row)
        row.conversation_id = _s(p.get("conversation_id"))
        row.ticket_id = _s(p.get("ticket_id"))
        row.call_id = _s(p.get("call_id"))
        row.agent_ref = _s(p.get("agent_email") or p.get("agent_ref"))
        row.score = float(p["score"])
        row.scale_max = int(p.get("scale_max") or 5)
        row.comment_masked = mask_text(p.get("comment") or "") or None
        row.responded_at = _dt(p.get("responded_at"))
        s.flush()
        if row.score / row.scale_max <= 0.4:
            ev = self._find_eval(s, tenant, row.conversation_id, row.call_id)
            self._task(s, tenant, f"{tenant}:csat_low:{src}:{ext}", kind="csat_low", severity="media",
                       title=f"CSAT baixo ({row.score:g}/{row.scale_max})", detail=row.comment_masked,
                       evaluation_id=ev.id if ev else None, conversation_id=row.conversation_id,
                       ticket_id=row.ticket_id, call_id=row.call_id, agent_ref=row.agent_ref or (ev.agent_ref if ev else None))
        return f"csat:{row.id}"

    def _on_csat_standalone(self, tenant: str, p: dict) -> str:
        with db.session() as s:
            return self._on_csat(s, tenant, p)

    def _find_eval(self, s, tenant, conversation_id, call_id) -> Optional[QaEvaluation]:
        q = select(QaEvaluation).where(QaEvaluation.tenant_id == tenant, QaEvaluation.is_current.is_(True),
                                       QaEvaluation.source == "ai")
        if call_id:
            q = q.where(QaEvaluation.call_id == call_id)
        elif conversation_id:
            q = q.where(QaEvaluation.conversation_id == conversation_id)
        else:
            return None
        return s.execute(q.order_by(QaEvaluation.id.desc())).scalars().first()

    # ------------------------------------------------------------ reprocessar
    def request_reprocess(self, tenant: str, recording_id: str, mode: str, actor: str, role: str, reason: str) -> Job:
        with db.session() as s:
            job = self._reprocess(s, tenant, recording_id, mode, actor, role, reason)
            s.expunge(job)
        return job

    def _reprocess(self, s, tenant, recording_id, mode, actor, role, reason) -> Job:
        if mode not in ("full", "analysis"):
            raise ValueError("mode deve ser full ou analysis")
        last = s.execute(select(Job).where(Job.tenant_id == tenant, Job.recording_id == recording_id)
                         .order_by(Job.run.desc()).with_for_update()).scalars().first()
        if last is None:
            raise LookupError("gravação sem processamento anterior")
        if last.status in ("pending", "running", "waiting_audio"):
            return last  # já há um em andamento: não duplica
        if mode == "analysis" and not s.execute(select(Transcription.id).where(
                Transcription.tenant_id == tenant, Transcription.recording_id == recording_id,
                Transcription.is_current.is_(True))).first():
            raise LookupError("não há transcrição atual para reanalisar; use mode=full")
        job = Job(tenant_id=tenant, recording_id=recording_id, run=last.run + 1, mode=mode, call_id=last.call_id,
                  ticket_id=last.ticket_id, conversation_id=last.conversation_id, agent_ref=last.agent_ref,
                  agent_name=last.agent_name, team=last.team, storage_key=last.storage_key, mime=last.mime,
                  duration_s=last.duration_s, sha256=last.sha256, correlation_id=last.correlation_id,
                  requested_by=actor, reason=reason)
        s.add(job)
        s.flush()
        s.add(QaReviewEvent(tenant_id=tenant, recording_id=recording_id, event_type="reprocess_requested",
                            actor_ref=actor, actor_role=role, payload={"mode": mode, "reason": reason, "job_id": job.id,
                                                                       "run": job.run}))
        return job

    # -------------------------------------------------------------------- jobs
    def recover_stale(self) -> int:
        limit = utcnow() - timedelta(seconds=self.s.stt_timeout_s + 300)
        with db.session() as s:
            res = s.execute(update(Job).where(Job.status == "running", Job.locked_at < limit)
                            .values(status="pending", locked_by=None, next_attempt_at=func.now(),
                                    last_error="recuperado após worker interrompido"))
            return res.rowcount or 0

    def claim(self) -> Optional[int]:
        with db.session() as s:
            job = s.execute(select(Job).where(Job.status.in_(("pending", "waiting_audio")),
                                              Job.next_attempt_at <= func.now())
                            .order_by(Job.next_attempt_at, Job.id).limit(1).with_for_update(skip_locked=True)
                            ).scalar_one_or_none()
            if job is None:
                return None
            job.status, job.locked_by, job.locked_at = "running", self.worker_id, utcnow()
            job.attempts += 1
            job.updated_at = utcnow()
            return job.id

    def run_due(self, max_jobs: int = 1) -> int:
        n = 0
        while n < max_jobs:
            jid = self.claim()
            if jid is None:
                break
            self.process(jid)
            n += 1
        self.publish_outbox()
        return n

    def process(self, job_id: int) -> None:
        with db.session() as s:
            job = s.get(Job, job_id)
            s.expunge(job)
        extra = {"job_id": job.id, "recording_id": job.recording_id, "call_id": job.call_id,
                 "correlation_id": job.correlation_id}
        t_total = time.perf_counter()
        tmp = None
        try:
            tr_id = self._existing_transcription(job)
            if tr_id is None:
                tmp = tempdir()
                tr_id = self._transcribe(job, tmp, extra)
            self._analyze(job, tr_id, extra)
            self._finish(job, t_total)
            log.info("job concluído", extra={**extra, "stage": "done"})
        except Retry as r:
            self._retry(job, r, extra)
        except Permanent as p:
            self._fail(job, p.code, str(p), extra)
        except Exception as exc:  # erro inesperado: tenta de novo até o limite
            log.exception("erro inesperado", extra=extra)
            self._retry(job, Retry("unexpected", f"{type(exc).__name__}: {exc}"), extra)
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
        self.publish_outbox()
        self.deliver_sdops()
        if self.s.post_notes:
            self.post_notes(job_id=job.id)

    def _existing_transcription(self, job: Job) -> Optional[int]:
        with db.session() as s:
            if job.mode == "analysis":
                tid = s.execute(select(Transcription.id).where(Transcription.tenant_id == job.tenant_id,
                                                               Transcription.recording_id == job.recording_id,
                                                               Transcription.is_current.is_(True))).scalar()
                if tid is None:
                    raise Permanent("config", "reanálise sem transcrição atual")
                return tid
            return s.execute(select(Transcription.id).where(Transcription.job_id == job.id)).scalar()

    def _transcribe(self, job: Job, tmp: str, extra: dict) -> int:
        if not job.storage_key:
            raise Permanent("audio_inexistente", "evento sem storage_key (ligação sem gravação)")
        t0 = time.perf_counter()
        try:
            path = self.storage.fetch(job.storage_key, tmp, self.s.audio_max_mb * 1024 * 1024)
        except NotFound:
            if job.attempts >= self.s.audio_wait_attempts:
                raise Permanent("audio_missing", f"arquivo não apareceu após {job.attempts} verificações")
            raise Retry("audio_not_found", "gravação ainda não disponível", status="waiting_audio",
                        delay_s=min(60 * (2 ** (job.attempts - 1)), 1800))
        except StorageError as e:
            if e.permanent:
                raise Permanent(e.code, str(e))
            raise Retry(e.code, str(e))
        fetch_ms = int((time.perf_counter() - t0) * 1000)
        if job.sha256 and sha256_file(path) != job.sha256.lower():
            raise Permanent("audio_integrity", "sha256 do arquivo difere do evento")
        mime = sniff_mime(path)
        if mime is None or mime not in self.s.allowed_mimes:
            raise Permanent("audio_type", f"tipo de áudio não permitido ({mime or 'desconhecido'})")
        t1 = time.perf_counter()
        try:
            res = self.stt.transcribe(path, expected_duration_s=job.duration_s)
        except SttError as e:
            if e.permanent:
                raise Permanent(e.code, str(e))
            if job.attempts >= self.s.max_attempts:
                raise Permanent("transcription_failed", str(e))
            raise Retry(e.code, str(e))
        stt_ms = int((time.perf_counter() - t1) * 1000)
        if res.audio_duration_s and res.audio_duration_s > self.s.audio_max_duration_s:
            raise Permanent("audio_too_large", "duração acima do limite")
        masked, pii_counts = mask_segments([sg.text for sg in res.segments])
        cmap = self.s.channel_map
        dur = res.audio_duration_s or 0
        expected = job.duration_s
        cov = 1.0
        if expected and expected > 0 and dur:
            cov = min(1.0, dur / expected)
        partial = res.partial or cov < self.s.stt_min_coverage
        confs = [sg.confidence for sg in res.segments if sg.confidence is not None]
        low = [c for c in confs if c < LOW_CONF]
        with db.session() as s:
            s.execute(update(Transcription).where(Transcription.tenant_id == job.tenant_id,
                                                  Transcription.recording_id == job.recording_id,
                                                  Transcription.is_current.is_(True)).values(is_current=False))
            tr = Transcription(
                tenant_id=job.tenant_id, job_id=job.id, recording_id=job.recording_id, run=job.run, call_id=job.call_id,
                ticket_id=job.ticket_id, conversation_id=job.conversation_id, status="partial" if partial else "completed",
                provider=res.provider, model=res.model, engine_config=res.engine_config, language=res.language,
                language_probability=res.language_probability, audio_duration_s=dur, expected_duration_s=expected,
                coverage_ratio=round(cov, 3), avg_confidence=round(sum(confs) / len(confs), 3) if confs else None,
                low_confidence_ratio=round(len(low) / len(confs), 3) if confs else None, diarization=res.diarization,
                text_masked=" ".join(masked), text_raw=" ".join(sg.text for sg in res.segments)
                if self.s.store_unmasked_transcript else None, pii_counts=pii_counts, audio_sha256=job.sha256,
                processing_ms=stt_ms, rtf=round((stt_ms / 1000) / dur, 3) if dur else None,
                warnings=list(res.warnings) + ([] if res.segments else ["nenhuma fala reconhecida"]), is_current=True)
            s.add(tr)
            s.flush()
            for i, (sg, txt) in enumerate(zip(res.segments, masked)):
                speaker = cmap.get(sg.channel) if (sg.channel is not None and cmap) else None
                s.add(TranscriptionSegment(
                    transcription_id=tr.id, idx=i, start_s=sg.start, end_s=sg.end, channel=sg.channel, speaker=speaker,
                    speaker_evidence="channel" if speaker else "none", text_masked=txt, confidence=sg.confidence,
                    no_speech_prob=sg.no_speech_prob, low_confidence=bool(sg.confidence is not None and sg.confidence < LOW_CONF)))
            job_row = s.get(Job, job.id)
            job_row.timings = {**(job_row.timings or {}), "fetch_ms": fetch_ms, "stt_ms": stt_ms,
                               "audio_s": dur, "rtf": tr.rtf}
            job_row.stage = "transcribed"
            self._outbox(s, "transcription.completed", job, {
                "transcription_id": tr.id, "status": tr.status, "language": tr.language, "duration_s": dur,
                "coverage_ratio": tr.coverage_ratio, "segments": len(masked), "provider": tr.provider, "model": tr.model,
                "avg_confidence": tr.avg_confidence, "pii_masked": pii_counts})
            log.info("transcrição salva", extra={**extra, "stage": "transcribed"})
            return tr.id

    def _analyze(self, job: Job, tr_id: int, extra: dict) -> None:
        with db.session() as s:
            tr = s.get(Transcription, tr_id)
            rows = s.execute(select(TranscriptionSegment).where(TranscriptionSegment.transcription_id == tr_id)
                             .order_by(TranscriptionSegment.idx)).scalars().all()
            segs = [Seg(idx=r.idx, start=r.start_s, end=r.end_s, text=r.text_masked, speaker=r.speaker,
                        channel=r.channel) for r in rows]
            rubric = db.active_rubric(s, job.tenant_id, self.s.rubric_code)
            pv_qa = db.ensure_prompt(s, "qa")
            pv_sum = db.ensure_prompt(s, "summary")
            coverage = {"ratio": tr.coverage_ratio or 1.0, "partial": tr.status == "partial",
                        "start_s": segs[0].start if segs else 0}
            rubric_dict = {"criteria": rubric.criteria, "mandatory_phrases": rubric.mandatory_phrases}
            rubric_id, pv_qa_id, pv_sum_id, stt_model = rubric.id, pv_qa.id, pv_sum.id, tr.model
            qa_template, sum_template = pv_qa.template, pv_sum.template
        t0 = time.perf_counter()
        try:
            if not segs:
                summary = None
                outcome = None
            else:
                summary = run_summary(self.llm, segs, sum_template)
                outcome = run_qa(self.llm, segs, rubric_dict, coverage, qa_template, self.s.min_applicable_weight)
        except LlmError as e:
            if e.permanent or job.attempts >= self.s.max_attempts:
                raise Permanent("analysis_failed", str(e))
            raise Retry(e.code, str(e))
        analysis_ms = int((time.perf_counter() - t0) * 1000)
        if job.agent_ref is None and self.sdops and job.call_id:
            info = self.sdops.call_info(job.call_id)
            job.agent_ref, job.agent_name = info.get("agent_ref"), info.get("agent_name")
            job.team = job.team or info.get("team")
        with db.session() as s:
            # Re-execução do mesmo job (retry após falha no meio): não duplica.
            if s.execute(select(QaEvaluation.id).where(QaEvaluation.job_id == job.id)).first():
                return
            s.execute(update(QaEvaluation).where(QaEvaluation.tenant_id == job.tenant_id,
                                                 QaEvaluation.recording_id == job.recording_id,
                                                 QaEvaluation.is_current.is_(True)).values(is_current=False))
            s.execute(update(CallSummary).where(CallSummary.tenant_id == job.tenant_id,
                                                CallSummary.recording_id == job.recording_id,
                                                CallSummary.is_current.is_(True)).values(is_current=False))
            provider = (outcome.provider if outcome else self.llm.name)
            model = (outcome.model if outcome else getattr(self.llm, "model", ""))
            ev = QaEvaluation(
                tenant_id=job.tenant_id, job_id=job.id, transcription_id=tr_id, recording_id=job.recording_id,
                call_id=job.call_id, ticket_id=job.ticket_id, conversation_id=job.conversation_id,
                agent_ref=job.agent_ref, agent_name=job.agent_name, team=job.team, source="ai",
                status=outcome.status if outcome else "insufficient_evidence",
                score=outcome.score if outcome else None,
                applicable_weight=outcome.applicable_weight if outcome else 0,
                redistribution=outcome.redistribution if outcome else {"resultado": "transcrição sem fala"},
                confidence=outcome.confidence if outcome else 0.0, rubric_version_id=rubric_id,
                prompt_version_id=pv_qa_id, llm_provider=provider, llm_model=model, stt_model=stt_model,
                warnings=(outcome.warnings if outcome else ["transcrição sem fala reconhecida"]))
            s.add(ev)
            s.flush()
            for c in (outcome.criteria if outcome else []):
                s.add(QaCriterionScore(
                    evaluation_id=ev.id, criterion_key=c.key, label=c.label, weight=c.weight,
                    effective_weight=c.effective_weight, status=c.status, score=c.score, justification=c.justification,
                    evidence_text=c.evidence_text, evidence_start_s=c.evidence_start_s, evidence_end_s=c.evidence_end_s,
                    evidence_segment_idx=c.evidence_segment_idx, evidence_verified=c.evidence_verified,
                    confidence=c.confidence, suggestion=c.suggestion, flags=c.flags or []))
            sm = None
            if summary is not None:
                sm = CallSummary(tenant_id=job.tenant_id, job_id=job.id, transcription_id=tr_id,
                                 recording_id=job.recording_id, conversation_id=job.conversation_id,
                                 ticket_id=job.ticket_id, status="draft", content=summary.content,
                                 llm_provider=summary.provider, llm_model=summary.model, prompt_version_id=pv_sum_id,
                                 note_status="pending" if (self.s.post_notes and job.conversation_id) else "skipped")
                s.add(sm)
                s.flush()
            base = f"{job.tenant_id}:{job.recording_id}:{job.run}"
            common = dict(evaluation_id=ev.id, job_id=job.id, recording_id=job.recording_id, call_id=job.call_id,
                          ticket_id=job.ticket_id, conversation_id=job.conversation_id, agent_ref=job.agent_ref)
            for a in (outcome.alerts if outcome else []):
                self._task(s, job.tenant_id, f"{base}:alert:{a.type}:{a.segment_idx}", kind="alert", alert_type=a.type,
                           severity=a.severity, title=a.label, detail=a.description, evidence_text=a.evidence_text,
                           evidence_start_s=a.start_s, evidence_verified=True, **common)
            if ev.status == "insufficient_evidence":
                self._task(s, job.tenant_id, f"{base}:qa_insufficient_evidence", kind="qa_insufficient_evidence",
                           severity="media", title="QA sem evidência suficiente: avaliar manualmente",
                           detail=(ev.redistribution or {}).get("resultado"), **common)
            elif ev.score is not None and float(ev.score) < self.s.low_score_threshold:
                self._task(s, job.tenant_id, f"{base}:qa_low_score", kind="qa_low_score", severity="alta",
                           title=f"QA abaixo de {self.s.low_score_threshold}: revisão do supervisor",
                           detail=f"Nota sugerida pela IA: {float(ev.score):.0f}", **common)
            job_row = s.get(Job, job.id)
            job_row.timings = {**(job_row.timings or {}), "analysis_ms": analysis_ms}
            job_row.stage = "analyzed"
            job_row.agent_ref, job_row.agent_name, job_row.team = job.agent_ref, job.agent_name, job.team
            self._outbox(s, "qa.completed", job, {
                "evaluation_id": ev.id, "summary_id": sm.id if sm else None, "status": ev.status,
                "score": float(ev.score) if ev.score is not None else None, "confidence": ev.confidence,
                "alerts": sorted({a.type for a in (outcome.alerts if outcome else [])}),
                "rubric_version_id": rubric_id, "prompt_version_id": pv_qa_id, "llm_provider": provider,
                "llm_model": model, "stt_model": stt_model, "agent_ref": job.agent_ref,
                "console_url": f"{self.s.console_base_url}/qa/avaliacoes/{ev.id}", "is_recommendation": True})
            log.info("análise salva", extra={**extra, "stage": "analyzed"})

    def _finish(self, job: Job, t_total: float) -> None:
        with db.session() as s:
            row = s.get(Job, job.id)
            row.status, row.stage, row.locked_by, row.finished_at = "done", "done", None, utcnow()
            row.error_code = row.last_error = None
            row.timings = {**(row.timings or {}), "total_ms": int((time.perf_counter() - t_total) * 1000)}
            row.updated_at = utcnow()

    def _retry(self, job: Job, r: Retry, extra: dict) -> None:
        if r.status != "waiting_audio" and job.attempts >= self.s.max_attempts:
            return self._fail(job, r.code, str(r), extra)
        delay = r.delay_s or min(self.s.retry_base_s * (2 ** max(0, job.attempts - 1)), self.s.retry_max_s)
        with db.session() as s:
            row = s.get(Job, job.id)
            row.status, row.locked_by = r.status, None
            row.error_code, row.last_error = r.code, str(r)[:2000]
            row.next_attempt_at = utcnow() + timedelta(seconds=delay)
            row.updated_at = utcnow()
        log.warning("job reagendado em %ss (%s)", delay, r.code, extra=extra)

    def _fail(self, job: Job, code: str, message: str, extra: dict) -> None:
        with db.session() as s:
            row = s.get(Job, job.id)
            row.status, row.locked_by, row.finished_at = "failed", None, utcnow()
            row.error_code, row.last_error = code, message[:2000]
            row.updated_at = utcnow()
            self._task(s, job.tenant_id, f"{job.tenant_id}:{job.recording_id}:{job.run}:pipeline_failure:{code}",
                       kind="pipeline_failure", severity="media", title=FAIL_TITLES.get(code, f"Falha: {code}"),
                       detail=message[:1000], job_id=job.id, recording_id=job.recording_id, call_id=job.call_id,
                       ticket_id=job.ticket_id, conversation_id=job.conversation_id, agent_ref=job.agent_ref)
            self._outbox(s, "transcription.failed", job, {"error_code": code, "message": message[:300],
                                                          "permanent": True})
        log.error("job falhou: %s", code, extra=extra)

    # ------------------------------------------------------------- utilidades
    def _task(self, s, tenant: str, dedupe: str, **kw) -> None:
        if s.execute(select(ReviewTask.id).where(ReviewTask.dedupe_key == dedupe[:300])).first():
            return
        s.add(ReviewTask(tenant_id=tenant, dedupe_key=dedupe[:300], **kw))
        s.flush()

    def _outbox(self, s, event_type: str, job: Job, payload: dict) -> None:
        base = {"recording_id": job.recording_id, "call_id": job.call_id, "ticket_id": job.ticket_id,
                "conversation_id": job.conversation_id, "run": job.run, "job_id": job.id}
        s.add(Outbox(event_id=str(uuid.uuid4()), event_type=event_type,
                     payload={"tenant_id": job.tenant_id, "correlation_id": job.correlation_id, **base, **payload}))

    def publish_outbox(self, limit: int = 100) -> int:
        if self.bus is None:
            return 0
        n = 0
        with db.session() as s:
            rows = s.execute(select(Outbox).where(Outbox.published_at.is_(None)).order_by(Outbox.id).limit(limit)
                             .with_for_update(skip_locked=True)).scalars().all()
            for o in rows:
                p = dict(o.payload)
                tenant = p.pop("tenant_id", self.s.tenant_default)
                corr = p.pop("correlation_id", None)
                try:
                    o.stream_id = self.bus.publish(envelope(o.event_type, p, tenant, corr, o.event_id))
                    o.published_at = utcnow()
                    n += 1
                except Exception:
                    o.attempts += 1
                    log.warning("falha ao publicar evento %s", o.event_type)
                    break
        return n

    def deliver_sdops(self, limit: int = 50) -> int:
        """Entrega os resultados ao sd-ops por REST (o sd-ops não lê o stream). Retentativa com backoff."""
        if self.sdops is None or not self.sdops.base:
            return 0
        done = 0
        with db.session() as s:
            rows = s.execute(select(Outbox).where(Outbox.sdops_status == "pending", Outbox.sdops_next_at <= func.now())
                             .order_by(Outbox.id).limit(limit).with_for_update(skip_locked=True)).scalars().all()
            for o in rows:
                bodies = analysis_results_for(o)
                if not bodies:
                    o.sdops_status = "skipped"
                    continue
                o.sdops_attempts += 1
                try:
                    for b in bodies:
                        self.sdops.post_analysis_result(b)
                    o.sdops_status, o.sdops_error = "delivered", None
                    done += 1
                except ClientError as e:
                    o.sdops_error = str(e)[:500]
                    if e.permanent or o.sdops_attempts >= 10:
                        o.sdops_status = "failed"
                    else:
                        o.sdops_next_at = utcnow() + timedelta(seconds=min(30 * 2 ** o.sdops_attempts, 3600))
        return done

    def post_notes(self, job_id: Optional[int] = None, max_attempts: int = 5) -> int:
        """Nota privada 'rascunho IA' no Chatwoot. Falha aqui não afeta o QA; tenta de novo depois."""
        if not self.chatwoot:
            return 0
        sent = 0
        with db.session() as s:
            q = select(CallSummary).where(CallSummary.note_status.in_(("pending", "failed")),
                                          CallSummary.note_attempts < max_attempts, CallSummary.is_current.is_(True),
                                          CallSummary.conversation_id.isnot(None))
            if job_id:
                q = q.where(CallSummary.job_id == job_id)
            items = s.execute(q.limit(20).with_for_update(skip_locked=True)).scalars().all()
            for sm in items:
                ev = s.execute(select(QaEvaluation).where(QaEvaluation.job_id == sm.job_id)).scalar_one_or_none()
                alerts = s.execute(select(ReviewTask).where(ReviewTask.job_id == sm.job_id,
                                                            ReviewTask.kind == "alert")).scalars().all()
                link = f"{self.s.console_base_url}/qa/avaliacoes/{ev.id}" if ev else self.s.console_base_url
                text = summary_to_note(sm.content, link, float(ev.score) if ev and ev.score is not None else None,
                                       [AlertResult(a.alert_type, a.title, a.severity, "", "", 0, 0) for a in alerts])
                job = s.get(Job, sm.job_id)
                marker = f"qa:{sm.recording_id}:{job.run}"
                sm.note_attempts += 1
                try:
                    sm.note_message_id = self.chatwoot.post_private_note(sm.conversation_id, text, marker)
                    sm.note_status, sm.note_error = "sent", None
                    sent += 1
                except ClientError as e:
                    sm.note_status, sm.note_error = "failed", str(e)[:500]
                    if e.permanent:
                        sm.note_attempts = max_attempts
        return sent


def analysis_results_for(o: Outbox) -> List[dict]:
    """Converte um evento da outbox no corpo de POST /sd-ops/api/v1/analysis-results (§8.8)."""
    p = o.payload
    ts = (o.created_at or utcnow()).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    common = {"recording_id": p.get("recording_id"), "call_id": p.get("call_id"), "completed_at": ts}
    if o.event_type == "transcription.completed":
        return [{**common, "kind": "transcription", "status": "partial" if p.get("status") == "partial" else "completed",
                 "external_id": f"qa.transcriptions:{p['transcription_id']}", "score": None,
                 "data": {"language": p.get("language"), "segments": p.get("segments"),
                          "confidence": p.get("avg_confidence"), "coverage_ratio": p.get("coverage_ratio"),
                          "model": p.get("model"), "run": p.get("run")}}]
    if o.event_type == "transcription.failed":
        return [{**common, "kind": "transcription", "status": "failed", "external_id": f"qa.processing_jobs:{p['job_id']}",
                 "score": None, "data": {"error_code": p.get("error_code"), "run": p.get("run")}}]
    if o.event_type == "qa.completed":
        out = [{**common, "kind": "qa", "status": "completed" if p.get("score") is not None else "partial",
                "external_id": f"qa.qa_evaluations:{p['evaluation_id']}", "score": p.get("score"),
                "data": {"rubric_version": p.get("rubric_version_id"), "prompt_version": p.get("prompt_version_id"),
                         "model": p.get("llm_model"), "alerts": p.get("alerts"), "console_url": p.get("console_url"),
                         "recommendation_only": True, "run": p.get("run")}}]
        if p.get("summary_id"):
            out.append({**common, "kind": "summary", "status": "completed",
                        "external_id": f"qa.call_summaries:{p['summary_id']}", "score": None,
                        "data": {"review_status": "draft", "console_url": p.get("console_url")}})
        return out
    return []


def _s(v) -> Optional[str]:
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def _f(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _dt(v) -> Optional[datetime]:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v).replace("Z", "+00:00"))
    except ValueError:
        return None


def segments_of(s, transcription_id: int) -> List[TranscriptionSegment]:
    return s.execute(select(TranscriptionSegment).where(TranscriptionSegment.transcription_id == transcription_id)
                     .order_by(TranscriptionSegment.idx)).scalars().all()
