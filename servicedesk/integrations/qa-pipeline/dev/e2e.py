"""E2E do qa-pipeline no DEV (dados e áudio FICTÍCIOS), com STT REAL (faster-whisper) e LLM mock.

Parte A (contrato com o sd-ops real): consome os eventos `recording.stored` que o sd-ops do A2 já publicou
no stream DEV `sd:events` (Redis DB 7) e lê os arquivos do storage local do sd-ops (montado somente leitura).
Parte B (fala sintética): cria 3 conversas fictícias no Chatwoot DEV (inbox API do 55PBX), publica
`recording.stored` dos áudios do Piper num stream ISOLADO (para não poluir o stream compartilhado) e
processa: transcrição, resumo, QA, alertas, nota privada no Chatwoot, eventos de saída. Depois reenvia os
mesmos eventos (idempotência) e reprocessa uma gravação.

  docker run ... --env-file dev/run/dev.env --env-file dev/run/cw.env \
     -v <recordings do sd-ops>:/data/sdops:ro -v $PWD:/app sd-qa-dev python dev/e2e.py
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import uuid

import httpx
import redis
from sqlalchemy import func, select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qa_pipeline import db, logutil  # noqa: E402
from qa_pipeline.clients import ChatwootClient  # noqa: E402
from qa_pipeline.config import Settings, reset_settings  # noqa: E402
from qa_pipeline.events import EventBus, parse_message  # noqa: E402
from qa_pipeline.models import CallSummary, Job, QaEvaluation, ReviewTask, Transcription  # noqa: E402
from qa_pipeline.pipeline import Pipeline  # noqa: E402
from qa_pipeline.runner import consume_once  # noqa: E402
from qa_pipeline.storage import LocalStorage  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, "run")
TAG = uuid.uuid4().hex[:6]
REPORT = {"tag": TAG, "checks": []}


def check(name, ok, detail=""):
    REPORT["checks"].append({"check": name, "ok": bool(ok), "detail": detail})
    print(("OK  " if ok else "FALHA ") + name + (f" — {detail}" if detail else ""), flush=True)


def settings(stream: str, group: str, root: str, post_notes: bool) -> Settings:
    s = Settings()
    s.enabled = True
    s.events_stream, s.consumer_group, s.consumer_name, s.stream_start_id = stream, group, "e2e", "0"
    s.storage_local_root = root
    s.stt_provider, s.llm_provider = "faster_whisper", "mock"
    s.whisper_model, s.whisper_cpu_threads = os.environ.get("WHISPER_MODEL", "small"), 1
    s.post_notes = post_notes
    s.console_base_url = "http://localhost:3480/sd-console"
    reset_settings(s)
    return s


def drain(pipe: Pipeline, rounds: int = 40):
    for _ in range(rounds):
        consume_once(pipe, block_ms=200)
        if not pipe.run_due(5):
            break


def count(model, *where):
    with db.session() as s:
        return s.execute(select(func.count()).select_from(model).where(*where)).scalar()


def part_a(r: redis.Redis):
    """Eventos reais do sd-ops (A2) no stream compartilhado."""
    s = settings("sd:events", "qa-pipeline", "/data/sdops", post_notes=False)
    bus = EventBus(r, s.events_stream, s.consumer_group, "e2e-a", "0")
    bus.ensure_group()
    pipe = Pipeline(s, storage=LocalStorage(s.storage_local_root), bus=bus)
    real = [parse_message(f) for _, f in r.xrange("sd:events")]
    recs = [e for e in real if e and e["type"] == "recording.stored"]
    t0 = time.time()
    drain(pipe)
    ids = [e["payload"]["recording_id"] for e in recs]
    with db.session() as ss:
        jobs = ss.execute(select(Job).where(Job.recording_id.in_(ids))).scalars().all()
        st = {j.recording_id: (j.status, j.error_code) for j in jobs}
        trs = ss.execute(select(Transcription).where(Transcription.recording_id.in_(ids))).scalars().all()
        evs = ss.execute(select(QaEvaluation).where(QaEvaluation.recording_id.in_(ids))).scalars().all()
    check("A: um job por recording.stored real do sd-ops", len(jobs) == len(recs), f"{len(jobs)} jobs / {len(recs)} eventos")
    check("A: storage do sd-ops lido e transcrito (WAV)", all(v[0] == "done" for v in st.values()), json.dumps(st))
    REPORT["parte_a"] = {"eventos": len(recs), "segundos": round(time.time() - t0, 1),
                         "transcricoes": [{"recording_id": t.recording_id, "status": t.status, "duracao_s": t.audio_duration_s,
                                           "segmentos": len(t.text_masked.split()) and t.text_masked[:80], "rtf": t.rtf}
                                          for t in trs],
                         "avaliacoes": [{"status": e.status, "score": float(e.score) if e.score is not None else None} for e in evs]}
    out = [parse_message(f) for _, f in r.xrange("sd:events")]
    mine = [e for e in out if e and e.get("payload", {}).get("recording_id") in ids and e["type"] in
            ("transcription.completed", "qa.completed", "transcription.failed")]
    check("A: resultados publicados em sd:events no envelope do projeto (type + data)", len(mine) >= len(recs),
          f"{len(mine)} eventos de saída")


def create_conversations(n: int):
    url, tok, acc, inbox = (os.environ.get(k) for k in ("CHATWOOT_URL", "CHATWOOT_API_TOKEN", "CHATWOOT_ACCOUNT_ID", "PBX_INBOX_ID"))
    if not (url and tok and acc and inbox):
        return [None] * n
    h = {"api_access_token": tok}
    for _ in range(60):  # Chatwoot DEV pode estar reiniciando
        try:
            if httpx.get(f"{url}/api", timeout=10).status_code == 200:
                break
        except httpx.HTTPError:
            pass
        time.sleep(5)
    out = []
    with httpx.Client(base_url=f"{url}/api/v1/accounts/{acc}", headers=h, timeout=120) as c:
        for i in range(n):
            contact = c.post("/contacts", json={"name": f"Cliente Fictício QA {TAG}-{i + 1}", "inbox_id": int(inbox),
                                                "phone_number": f"+551190{(int(TAG, 16) + i) % 10**7:07d}"}).json()
            payload = contact.get("payload", contact)
            cid = payload["contact"]["id"] if "contact" in payload else payload["id"]
            sid = (payload.get("contact_inbox") or {}).get("source_id")
            if not sid:
                sid = c.post(f"/contacts/{cid}/contact_inboxes", json={"inbox_id": int(inbox)}).json()["source_id"]
            conv = c.post("/conversations", json={"source_id": sid, "inbox_id": int(inbox), "contact_id": cid,
                                                  "additional_attributes": {"mail_subject": f"Ligação fictícia QA {TAG}"}}).json()
            out.append(str(conv.get("display_id") or conv["id"]))
    return out


def part_b(r: redis.Redis):
    root = os.path.join(RUN, "e2e-storage")
    names = ["bom_atendimento", "atendimento_ruim", "cobranca_dados_sensiveis"]
    fmt = {"bom_atendimento": "mp3", "atendimento_ruim": "mp3", "cobranca_dados_sensiveis": "stereo8k.wav"}
    convs = create_conversations(len(names))
    check("B: conversas fictícias criadas no Chatwoot DEV", all(convs), str(convs))
    stream = f"sd:events:qa-e2e:{TAG}"
    s = settings(stream, "qa-pipeline", root, post_notes=all(convs))
    cw = ChatwootClient(os.environ["CHATWOOT_URL"], os.environ["CHATWOOT_API_TOKEN"], os.environ["CHATWOOT_ACCOUNT_ID"],
                        timeout_s=120) if all(convs) else None
    bus = EventBus(r, stream, s.consumer_group, "e2e-b", "0")
    bus.ensure_group()
    pipe = Pipeline(s, storage=LocalStorage(root), bus=bus, chatwoot=cw)
    events = []
    for i, name in enumerate(names):
        src = os.path.join(HERE, "audio", "out", f"{name}.{fmt[name]}")
        rid = f"qa-e2e-{TAG}-{i + 1}"
        key = f"recordings/dev55/2026/10/{rid}.{fmt[name].split('.')[-1]}"
        os.makedirs(os.path.dirname(os.path.join(root, key)), exist_ok=True)
        shutil.copyfile(src, os.path.join(root, key))
        sha = hashlib.sha256(open(src, "rb").read()).hexdigest()
        dur = json.load(open(os.path.join(HERE, "audio", "out", f"{name}.turns.json")))["duration_s"]
        env = {"type": "recording.stored", "id": str(uuid.uuid4()), "occurred_at": "2026-10-14T00:00:00Z", "tenant_id": "dev55",
               "version": 1, "source": "e2e-qa", "correlation_id": f"corr-{rid}", "caused_by": None,
               "subject": {"call_id": f"call-{rid}", "ticket_id": None, "conversation_id": int(convs[i]) if convs[i] else None},
               "payload": {"recording_id": rid, "call_id": f"call-{rid}", "leg_id": None, "ticket_id": None,
                           "conversation_id": int(convs[i]) if convs[i] else None, "storage_key": key,
                           "mime": "audio/mpeg" if key.endswith("mp3") else "audio/wav", "duration_s": dur,
                           "size_bytes": os.path.getsize(src), "sha256": sha, "expected_talk_s": dur, "integrity": "ok",
                           "agent_email": ["carla@exemplo.test", "bruno@exemplo.test", "marcos@exemplo.test"][i],
                           "agent_name": ["Carla Fictícia", "Bruno Fictício", "Marcos Fictício"][i], "team": "Suporte"}}
        events.append(env)
        r.xadd(stream, {"type": env["type"], "data": json.dumps(env)})
    t0 = time.time()
    drain(pipe)
    wall = time.time() - t0
    ids = [e["payload"]["recording_id"] for e in events]
    with db.session() as ss:
        jobs = {j.recording_id: j for j in ss.execute(select(Job).where(Job.recording_id.in_(ids))).scalars()}
        trs = {t.recording_id: t for t in ss.execute(select(Transcription).where(Transcription.recording_id.in_(ids))).scalars()}
        evs = {e.recording_id: e for e in ss.execute(select(QaEvaluation).where(QaEvaluation.recording_id.in_(ids))).scalars()}
        sms = {m.recording_id: m for m in ss.execute(select(CallSummary).where(CallSummary.recording_id.in_(ids))).scalars()}
        alerts = {}
        for t in ss.execute(select(ReviewTask).where(ReviewTask.recording_id.in_(ids))).scalars():
            alerts.setdefault(t.recording_id, []).append(t.alert_type or t.kind)
    check("B: 3 jobs concluídos", all(j.status == "done" for j in jobs.values()) and len(jobs) == 3,
          json.dumps({k: (j.status, j.error_code) for k, j in jobs.items()}))
    audio_s = sum(t.audio_duration_s or 0 for t in trs.values())
    stt_s = sum((j.timings or {}).get("stt_ms", 0) for j in jobs.values()) / 1000
    REPORT["parte_b"] = {"audio_total_s": round(audio_s, 1), "stt_total_s": round(stt_s, 1), "wall_s": round(wall, 1),
                         "s_stt_por_min_audio": round(60 * stt_s / audio_s, 1) if audio_s else None, "itens": []}
    for i, rid in enumerate(ids):
        t, e, m = trs.get(rid), evs.get(rid), sms.get(rid)
        REPORT["parte_b"]["itens"].append({
            "audio": names[i], "conversa": convs[i], "transcricao": t.status if t else None,
            "idioma": t.language if t else None, "diarizacao": t.diarization if t else None,
            "pii": t.pii_counts if t else None, "rtf": t.rtf if t else None, "qa": float(e.score) if e and e.score is not None else None,
            "qa_status": e.status if e else None, "alertas": sorted(set(alerts.get(rid, []))),
            "nota_chatwoot": m.note_status if m else None, "evaluation_id": e.id if e else None})
    good, bad, pii = (evs.get(x) for x in ids)
    check("B: bom atendimento com nota alta", good is not None and good.score is not None and float(good.score) >= 80,
          f"{good.score if good else None}")
    check("B: atendimento ruim com nota baixa e alertas", bad is not None and bad.score is not None and float(bad.score) < 50
          and {"reclamacao", "pedido_supervisor"} <= set(alerts.get(ids[1], [])), f"{bad.score if bad else None} {alerts.get(ids[1])}")
    t3 = trs.get(ids[2])
    check("B: cartão/telefone mascarados antes do LLM (estéreo, separado por canal)",
          t3 is not None and not any(x in t3.text_masked for x in ("4111", "98765")) and t3.diarization == "channel",
          f"pii={t3.pii_counts if t3 else None}")
    if all(convs):
        h = {"api_access_token": os.environ["CHATWOOT_API_TOKEN"]}
        base = f"{os.environ['CHATWOOT_URL']}/api/v1/accounts/{os.environ['CHATWOOT_ACCOUNT_ID']}/conversations"
        notes = []
        for c in convs:
            msgs = httpx.get(f"{base}/{c}/messages", headers=h, timeout=120).json()["payload"]
            notes += [m for m in msgs if m.get("private") and "RASCUNHO IA" in (m.get("content") or "")]
        check("B: nota PRIVADA 'rascunho IA' com link do console em cada conversa", len(notes) == 3,
              f"{len(notes)} notas; ex.: {notes[0]['content'][:90]!r}" if notes else "0")
        REPORT["parte_b"]["exemplo_nota"] = notes[0]["content"] if notes else None
    # idempotência: reenvia os mesmos eventos com outro id
    for env in events:
        r.xadd(stream, {"type": env["type"], "data": json.dumps({**env, "id": str(uuid.uuid4())})})
    drain(pipe)
    check("B: eventos repetidos não criam jobs", count(Job, Job.recording_id.in_(ids)) == 3)
    # reprocessamento (só análise)
    j2 = pipe.request_reprocess("dev55", ids[0], "analysis", "e2e@exemplo.test", "qa", "teste de reprocessamento")
    drain(pipe)
    check("B: reprocessamento cria run 2 sem nova transcrição e sem duplicar a nota",
          count(Transcription, Transcription.recording_id == ids[0]) == 1
          and count(QaEvaluation, QaEvaluation.recording_id == ids[0], QaEvaluation.is_current.is_(True)) == 1, f"run {j2.run}")
    outs = [parse_message(f) for _, f in r.xrange(stream)]
    kinds = [e["type"] for e in outs if e]
    check("B: transcription.completed e qa.completed publicados", kinds.count("transcription.completed") == 3
          and kinds.count("qa.completed") == 4, json.dumps({k: kinds.count(k) for k in set(kinds)}))
    REPORT["parte_b"]["stream"] = stream


def main():
    logutil.setup("WARNING")
    s = Settings()
    db.init_engine(s.database_url)
    r = redis.Redis.from_url(s.redis_url)
    if os.path.isdir("/data/sdops"):
        part_a(r)
    part_b(r)
    ok = all(c["ok"] for c in REPORT["checks"])
    REPORT["resultado"] = f"{sum(c['ok'] for c in REPORT['checks'])}/{len(REPORT['checks'])} verificações OK"
    with open(os.path.join(RUN, f"e2e_report_{TAG}.json"), "w", encoding="utf-8") as fh:
        json.dump(REPORT, fh, ensure_ascii=False, indent=1, default=str)
    print(REPORT["resultado"], flush=True)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
