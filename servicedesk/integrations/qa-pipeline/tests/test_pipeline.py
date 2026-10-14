"""Cenários do prompt mestre §17 cobertos pelo qa-pipeline (16–21, 27, 30) + idempotência.
Banco real (servicedesk_ops_test), Redis falso, STT/LLM mock. Nenhum áudio ou dado real."""
import json
from datetime import datetime, timedelta, timezone

import httpx
import respx
from sqlalchemy import func, select, update

from qa_pipeline import db
from qa_pipeline.clients import ChatwootClient, SdOpsClient
from qa_pipeline.events import parse_message
from qa_pipeline.models import (CallSummary, CsatResponse, Job, Outbox, QaCriterionScore, QaEvaluation,
                                ReviewTask, Transcription, TranscriptionSegment)
from qa_pipeline.runner import consume_once

from .conftest import BAD, GOOD, recording_event, xadd

KEY = "recordings/t1/2026/10/rec-1.mp3"


def count(model, *where):
    with db.session() as s:
        return s.execute(select(func.count()).select_from(model).where(*where)).scalar()


def one(model, *where):
    with db.session() as s:
        return s.execute(select(model).where(*where)).scalars().first()


def drain(pipeline, n=10):
    for _ in range(n):
        if not pipeline.run_due(5):
            break


def published(redis_client, typ):
    out = []
    for _, fields in redis_client.xrange("sd:events"):
        ev = parse_message(fields)
        if ev and ev["type"] == typ:
            out.append(ev)
    return out


def test_good_call_end_to_end(pipeline, audio, redis_client):
    audio.put(KEY, GOOD)
    xadd(redis_client, recording_event())
    assert consume_once(pipeline, block_ms=10) == 1
    drain(pipeline)
    job = one(Job)
    assert job.status == "done" and job.timings["stt_ms"] >= 0
    tr = one(Transcription)
    assert tr.status == "completed" and tr.language == "pt" and tr.pii_counts.get("cpf") == 1
    assert "123 456 789 09" not in tr.text_masked and tr.text_raw is None
    segs = count(TranscriptionSegment)
    assert segs == len(GOOD)
    ev = one(QaEvaluation)
    assert ev.status == "ai_completed" and float(ev.score) >= 85 and ev.rubric_version_id and ev.prompt_version_id
    assert ev.llm_provider == "mock" and ev.stt_model == "mock"
    assert count(QaCriterionScore) == 7
    sm = one(CallSummary)
    assert sm.status == "draft" and sm.content["_meta"]["rascunho"] is True
    assert count(ReviewTask, ReviewTask.kind == "qa_low_score") == 0
    tc, qc = published(redis_client, "transcription.completed"), published(redis_client, "qa.completed")
    assert len(tc) == 1 and len(qc) == 1
    assert qc[0]["payload"]["console_url"].endswith(f"/qa/avaliacoes/{ev.id}")
    assert qc[0]["payload"]["is_recommendation"] is True and qc[0]["tenant_id"] == "t1"


def test_bad_call_creates_alerts_and_low_score_task(pipeline, audio, redis_client):
    audio.put(KEY, BAD)
    xadd(redis_client, recording_event())
    consume_once(pipeline, block_ms=10)
    drain(pipeline)
    ev = one(QaEvaluation)
    assert float(ev.score) < 40
    kinds = {t.alert_type for t in _all(ReviewTask, ReviewTask.kind == "alert")}
    assert {"reclamacao", "pedido_supervisor", "cliente_sem_solucao", "compromisso_retorno", "recorrencia"} <= kinds
    assert count(ReviewTask, ReviewTask.kind == "qa_low_score") == 1
    assert set(published(redis_client, "qa.completed")[0]["payload"]["alerts"]) >= {"reclamacao"}


def _all(model, *where):
    with db.session() as s:
        return s.execute(select(model).where(*where)).scalars().all()


def test_duplicate_events_and_reprocessing_do_not_duplicate(pipeline, audio, redis_client):
    audio.put(KEY, GOOD)
    ev = recording_event()
    xadd(redis_client, ev)
    xadd(redis_client, {**ev, "id": "outro-id"})  # mesma gravação, outro event_id
    consume_once(pipeline, block_ms=10)
    drain(pipeline)
    assert count(Job) == 1 and count(QaEvaluation) == 1
    # job reexecutado (ex.: worker caiu após salvar): não duplica transcrição/avaliação
    job = one(Job)
    pipeline.process(job.id)
    assert count(Transcription) == 1 and count(QaEvaluation) == 1 and count(CallSummary) == 1
    # reprocessamento explícito (cenário 21): run 2, histórico preservado, um "atual"
    j2 = pipeline.request_reprocess("t1", "rec-1", "full", "sup@exemplo.test", "supervisor", "nova versão do modelo")
    again = pipeline.request_reprocess("t1", "rec-1", "full", "sup@exemplo.test", "supervisor", "clique duplo")
    assert again.id == j2.id and j2.run == 2
    drain(pipeline)
    assert count(Transcription) == 2 and count(Transcription, Transcription.is_current.is_(True)) == 1
    assert count(QaEvaluation, QaEvaluation.is_current.is_(True)) == 1 and count(QaEvaluation) == 2
    j3 = pipeline.request_reprocess("t1", "rec-1", "analysis", "qa@exemplo.test", "qa", "rubrica v2")
    drain(pipeline)
    assert one(Job, Job.id == j3.id).status == "done"
    assert count(Transcription) == 2 and count(QaEvaluation) == 3  # só reanálise, sem novo STT


def test_scenario16_audio_inexistente(pipeline, redis_client):
    xadd(redis_client, recording_event(key=None))
    consume_once(pipeline, block_ms=10)
    drain(pipeline)
    job = one(Job)
    assert job.status == "failed" and job.error_code == "audio_inexistente"
    assert count(ReviewTask, ReviewTask.kind == "pipeline_failure") == 1
    assert published(redis_client, "transcription.failed")[0]["payload"]["error_code"] == "audio_inexistente"


def test_scenario17_audio_atrasado_then_arrives(pipeline, audio, redis_client):
    xadd(redis_client, recording_event())
    consume_once(pipeline, block_ms=10)
    pipeline.run_due(1)
    job = one(Job)
    assert job.status == "waiting_audio" and job.next_attempt_at > datetime.now(timezone.utc)
    audio.put(KEY, GOOD)  # o arquivo chega depois
    _due_now()
    drain(pipeline)
    assert one(Job).status == "done" and count(QaEvaluation) == 1


def test_scenario16b_audio_never_arrives(pipeline, redis_client):
    xadd(redis_client, recording_event())
    consume_once(pipeline, block_ms=10)
    for _ in range(5):
        _due_now()
        pipeline.run_due(1)
    job = one(Job)
    assert job.status == "failed" and job.error_code == "audio_missing"


def _due_now():
    with db.session() as s:
        s.execute(update(Job).values(next_attempt_at=datetime.now(timezone.utc) - timedelta(seconds=1)))


def test_scenario18_transcription_failure_retry_then_fail(pipeline, audio, redis_client):
    audio.put(KEY, GOOD)
    audio.flag(KEY, ".fail")
    xadd(redis_client, recording_event())
    consume_once(pipeline, block_ms=10)
    for _ in range(5):
        _due_now()
        pipeline.run_due(1)
    job = one(Job)
    assert job.status == "failed" and job.error_code == "transcription_failed" and job.attempts == 3
    assert count(ReviewTask, ReviewTask.kind == "pipeline_failure") == 1


def test_scenario18b_corrupt_audio_permanent(pipeline, audio, redis_client):
    audio.put(KEY, raw=b"isto nao e audio" * 10)
    xadd(redis_client, recording_event())
    consume_once(pipeline, block_ms=10)
    pipeline.run_due(1)
    job = one(Job)
    assert job.status == "failed" and job.error_code == "audio_type" and job.attempts == 1


def test_scenario18c_integrity_mismatch(pipeline, audio, redis_client):
    audio.put(KEY, GOOD)
    xadd(redis_client, recording_event(sha256="0" * 64))
    consume_once(pipeline, block_ms=10)
    pipeline.run_due(1)
    assert one(Job).error_code == "audio_integrity"


def test_scenario19_partial_transcription(pipeline, audio, redis_client):
    audio.put(KEY, GOOD[:6], duration=32.0)
    xadd(redis_client, recording_event(duration_s=81.0))
    consume_once(pipeline, block_ms=10)
    drain(pipeline)
    tr = one(Transcription)
    assert tr.status == "partial" and tr.coverage_ratio < 0.5
    ev = one(QaEvaluation)
    enc = one(QaCriterionScore, QaCriterionScore.evaluation_id == ev.id, QaCriterionScore.criterion_key == "encerramento")
    assert enc.status == "not_applicable" and "trecho" in (enc.justification or "").lower()
    assert ev.redistribution["peso_aplicavel"] < 100
    assert published(redis_client, "transcription.completed")[0]["payload"]["status"] == "partial"


def test_scenario20_qa_without_evidence(pipeline, audio, redis_client):
    audio.put(KEY, [])  # silêncio: nenhuma fala reconhecida
    xadd(redis_client, recording_event())
    consume_once(pipeline, block_ms=10)
    drain(pipeline)
    ev = one(QaEvaluation)
    assert ev.status == "insufficient_evidence" and ev.score is None
    assert count(ReviewTask, ReviewTask.kind == "qa_insufficient_evidence") == 1
    assert count(CallSummary) == 0


def test_scenario27_closing_with_csat(pipeline, audio, redis_client):
    audio.put(KEY, GOOD)
    xadd(redis_client, recording_event())
    consume_once(pipeline, block_ms=10)
    drain(pipeline)
    csat = {"type": "csat.recorded", "id": "csat-ev-1", "tenant_id": "t1", "version": 1, "source": "n8n",
            "payload": {"csat_id": "77", "source": "chatwoot", "score": 2, "scale_max": 5, "call_id": "call-rec-1",
                        "conversation_id": "101", "comment": "Demorou. Meu CPF é 123.456.789-09"}}
    xadd(redis_client, csat)
    xadd(redis_client, csat)  # duplicado
    consume_once(pipeline, block_ms=10)
    row = one(CsatResponse)
    assert count(CsatResponse) == 1 and row.score == 2 and "[CPF]" in row.comment_masked
    t = one(ReviewTask, ReviewTask.kind == "csat_low")
    assert t.evaluation_id == one(QaEvaluation).id


def test_scenario30_recovery_after_crash(pipeline, audio, redis_client):
    audio.put(KEY, GOOD)
    xadd(redis_client, recording_event())
    consume_once(pipeline, block_ms=10)
    jid = pipeline.claim()  # worker pegou o job e morreu
    with db.session() as s:
        s.execute(update(Job).where(Job.id == jid).values(locked_at=datetime.now(timezone.utc) - timedelta(hours=3)))
    assert pipeline.run_due(1) == 0  # ainda "running"
    assert pipeline.recover_stale() == 1
    drain(pipeline)
    assert one(Job).status == "done"


def test_unacked_event_redelivered_after_restart(pipeline, audio):
    """Redis REAL (DEV, DB 7, stream temporário): o fakeredis não devolve a PEL."""
    import os
    import uuid

    import pytest
    import redis
    from qa_pipeline.events import EventBus
    if not os.environ.get("REDIS_URL"):
        pytest.skip("REDIS_URL não definido")
    r = redis.Redis.from_url(os.environ["REDIS_URL"])
    stream = f"qa:test:{uuid.uuid4().hex[:8]}"
    try:
        pipeline.bus = EventBus(r, stream, "qa-pipeline", "w1", "0")
        pipeline.bus.ensure_group()
        audio.put(KEY, GOOD)
        ev = recording_event()
        r.xadd(stream, {"type": ev["type"], "data": json.dumps(ev)})
        assert len(pipeline.bus.read(count=10, block_ms=10)) == 1  # lido e não confirmado (worker morreu)
        assert consume_once(pipeline, block_ms=10) == 1  # reentregue a partir da PEL após reiniciar
        assert count(Job) == 1 and r.xpending(stream, "qa-pipeline")["pending"] == 0
    finally:
        r.delete(stream)


@respx.mock
def test_results_delivered_to_sdops_rest(pipeline, audio, redis_client):
    respx.get("http://sd-ops/sd-ops/api/v1/calls/call-rec-1").mock(return_value=httpx.Response(200, json={
        "id": "call-rec-1", "legs": [{"agent_email": "ana@exemplo.test", "agent_name": "Ana Teste",
                                      "queue": "FILA_SUPORTE_1"}]}))
    route = respx.post("http://sd-ops/sd-ops/api/v1/analysis-results").mock(
        side_effect=[httpx.Response(503), httpx.Response(201, json={}), httpx.Response(201, json={}),
                     httpx.Response(200, json={"duplicate": True}), httpx.Response(201, json={})])
    pipeline.sdops = SdOpsClient("http://sd-ops/sd-ops/api/v1", "sdsvc_teste")
    audio.put(KEY, GOOD)
    xadd(redis_client, recording_event())
    consume_once(pipeline, block_ms=10)
    drain(pipeline)
    with db.session() as s:
        s.execute(update(Outbox).values(sdops_next_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    pipeline.deliver_sdops()
    kinds = [json.loads(c.request.content)["kind"] for c in route.calls]
    assert kinds.count("transcription") >= 2 and "qa" in kinds and "summary" in kinds
    assert route.calls[0].request.headers["authorization"] == "Bearer sdsvc_teste"
    assert route.calls[0].request.headers["idempotency-key"].startswith("transcription:qa.transcriptions:")
    assert count(Outbox, Outbox.sdops_status == "delivered") == 2
    ev = one(QaEvaluation)
    assert ev.agent_ref == "ana@exemplo.test" and ev.team == "FILA_SUPORTE_1"  # enriquecido pelo sd-ops


@respx.mock
def test_private_note_in_chatwoot_is_idempotent(pipeline, audio, redis_client, settings):
    base = "http://chatwoot.test/api/v1/accounts/1/conversations/101/messages"
    posted = []

    def list_msgs(request):
        return httpx.Response(200, json={"payload": [{"id": 9, "source_id": m} for m in posted]})

    def create(request):
        body = json.loads(request.content)
        assert body["private"] is True and body["content"].startswith("**[RASCUNHO IA")
        posted.append(body["source_id"])
        return httpx.Response(200, json={"id": 555})

    respx.get(base).mock(side_effect=list_msgs)
    respx.post(base).mock(side_effect=create)
    settings.post_notes = True
    pipeline.chatwoot = ChatwootClient("http://chatwoot.test", "tok", "1")
    audio.put(KEY, GOOD)
    xadd(redis_client, recording_event())
    consume_once(pipeline, block_ms=10)
    drain(pipeline)
    sm = one(CallSummary)
    assert sm.note_status == "sent" and sm.note_message_id == "555" and posted == ["qa:rec-1:1"]
    with db.session() as s:
        s.execute(update(CallSummary).values(note_status="pending"))
    pipeline.post_notes()
    assert len(posted) == 1  # achou o source_id: não posta de novo
