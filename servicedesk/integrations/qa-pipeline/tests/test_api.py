"""API do console de QA: autenticação pela sessão do sd-ops (/auth/me mockado), RBAC, tenant (cenário 25),
revisão humana, contestação, resumo, rubricas, métricas, CSV, reprocessamento, marcações e acesso."""
import hashlib
import json

import httpx
import pytest
import respx
from fastapi.testclient import TestClient

from qa_pipeline.api import create_app
from qa_pipeline.auth import Authenticator

from .conftest import BAD, GOOD, recording_event, xadd
from qa_pipeline.runner import consume_once

SDOPS = "http://sd-ops.test/sd-ops/api/v1"
USERS = {
    "tok-ana": {"user": {"id": 1, "email": "ana@exemplo.test", "name": "Ana Teste"}, "tenant": "t1", "roles": ["agent"]},
    "tok-bruno": {"user": {"id": 2, "email": "bruno@exemplo.test", "name": "Bruno"}, "tenant": "t1", "roles": ["agent"]},
    "tok-sup": {"user": {"id": 3, "email": "sup@exemplo.test", "name": "Sup"}, "tenant": "t1", "roles": ["supervisor"]},
    "tok-qa": {"user": {"id": 4, "email": "qa@exemplo.test", "name": "QA"}, "tenant": "t1", "roles": ["qa"]},
    "tok-outro": {"user": {"id": 9, "email": "x@outra.test", "name": "Outro"}, "tenant": "t2", "roles": ["administrator"]},
}


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture()
def client(settings, pipeline, audio, redis_client, monkeypatch):
    settings.sd_ops_url = SDOPS
    svc = "sdqa_teste_servico"
    monkeypatch.setenv("QA_SERVICE_TOKENS", json.dumps({"n8n": {"sha256": hashlib.sha256(svc.encode()).hexdigest(),
                                                                "tenants": ["t1"], "scopes": ["qa:read"]}}))
    import qa_pipeline.auth as A
    A._cache.clear()

    def me(request):
        tok = request.headers.get("authorization", "")[7:]
        return httpx.Response(200, json=USERS[tok]) if tok in USERS else httpx.Response(401)

    router = respx.Router(assert_all_called=False)
    router.get(f"{SDOPS}/auth/me").mock(side_effect=me)
    app = create_app(settings, Authenticator(settings, transport=httpx.MockTransport(router.handler)))
    audio.put("recordings/t1/a.mp3", GOOD)
    audio.put("recordings/t1/b.mp3", BAD)
    xadd(redis_client, recording_event("rec-a", "recordings/t1/a.mp3", agent_email="ana@exemplo.test",
                                       agent_name="Ana Teste", team="Suporte"))
    xadd(redis_client, recording_event("rec-b", "recordings/t1/b.mp3", agent_email="bruno@exemplo.test",
                                       agent_name="Bruno", team="Suporte"))
    consume_once(pipeline, block_ms=10)
    pipeline.run_due(5)
    c = TestClient(app)
    c.svc = svc
    return c


def ev_id(client, tok, rec):
    items = client.get("/sd-qa/api/v1/evaluations", headers=H(tok)).json()["items"]
    return next(i["id"] for i in items if i["recording_id"] == rec)


def test_health_and_auth(client):
    assert client.get("/sd-qa/health").json()["status"] == "ok"
    assert client.get("/sd-qa/api/v1/evaluations").status_code == 401
    assert client.get("/sd-qa/api/v1/evaluations", headers=H("invalido")).status_code == 401
    me = client.get("/sd-qa/api/v1/me", headers=H("tok-ana")).json()
    assert me["roles"] == ["agente"] and me["tenant"] == "t1" and me["is_manager"] is False


def test_agent_sees_only_own_and_cross_tenant_is_404(client):
    ana = client.get("/sd-qa/api/v1/evaluations", headers=H("tok-ana")).json()
    assert ana["total"] == 1 and ana["items"][0]["agent_ref"] == "ana@exemplo.test"
    sup = client.get("/sd-qa/api/v1/evaluations", headers=H("tok-sup")).json()
    assert sup["total"] == 2
    bruno_ev = ev_id(client, "tok-sup", "rec-b")
    assert client.get(f"/sd-qa/api/v1/evaluations/{bruno_ev}", headers=H("tok-ana")).status_code == 404
    # cenário 25: admin de outro tenant não vê nem confirma a existência
    assert client.get(f"/sd-qa/api/v1/evaluations/{bruno_ev}", headers=H("tok-outro")).status_code == 404
    assert client.get("/sd-qa/api/v1/evaluations", headers=H("tok-outro")).json()["total"] == 0
    assert client.get("/sd-qa/api/v1/recordings/rec-a/analysis", headers=H("tok-outro")).status_code == 404


def test_evaluation_detail_has_versions_evidence_and_masked_transcript(client):
    eid = ev_id(client, "tok-ana", "rec-a")
    d = client.get(f"/sd-qa/api/v1/evaluations/{eid}", headers=H("tok-ana")).json()
    assert d["rubric"]["version"] == 1 and d["prompt"]["version"] == "v1" and len(d["prompt"]["sha256"]) == 64
    assert d["llm_provider"] == "mock" and d["stt_model"] == "mock"
    assert len(d["criteria"]) == 7 and any(c["evidence_verified"] for c in d["criteria"])
    text = " ".join(s["text"] for s in d["segments"])
    assert "[CPF]" in text and "123 456 789" not in text
    assert d["summary"]["status"] == "draft"


def test_human_review_and_divergence(client):
    eid = ev_id(client, "tok-sup", "rec-b")
    assert client.post(f"/sd-qa/api/v1/evaluations/{eid}/review", headers=H("tok-ana"),
                       json={"criteria": []}).status_code == 403
    r = client.post(f"/sd-qa/api/v1/evaluations/{eid}/review", headers=H("tok-sup"), json={
        "criteria": [{"key": "empatia", "status": "observed", "score": 40, "justification": "Tom seco, sem acolher"}],
        "comment": "Revisado com o áudio"})
    assert r.status_code == 200 and r.json()["score"] is not None
    d = client.get(f"/sd-qa/api/v1/evaluations/{eid}", headers=H("tok-sup")).json()
    assert d["review_state"] == "revisada" and d["human_reviews"][0]["reviewer"] == "sup@exemplo.test"
    assert d["events"][0]["type"] == "reviewed" and "empatia" in d["events"][0]["payload"]["diff"]
    assert all(t["status"] == "done" for t in d["tasks"] if t["kind"] == "qa_low_score")
    q = client.get("/sd-qa/api/v1/metrics/quality", headers=H("tok-sup")).json()
    assert q["divergencia_ia_humano"]["pares"] == 1 and q["revisadas_por_humano"] == 1
    stats = client.get("/sd-qa/api/v1/agents/stats", headers=H("tok-qa")).json()["items"]
    bruno = next(i for i in stats if i["agent_ref"] == "bruno@exemplo.test")
    assert bruno["qa_medio_humano"] is not None and bruno["criterios_a_treinar"]


def test_contest_flow(client):
    eid = ev_id(client, "tok-ana", "rec-a")
    assert client.post(f"/sd-qa/api/v1/evaluations/{eid}/contest", headers=H("tok-ana"),
                       json={"reason": "O protocolo foi informado, ver 01:05. CPF 123.456.789-09"}).status_code == 200
    assert client.post(f"/sd-qa/api/v1/evaluations/{eid}/contest", headers=H("tok-ana"),
                       json={"reason": "de novo por favor"}).status_code == 409
    d = client.get(f"/sd-qa/api/v1/evaluations/{eid}", headers=H("tok-sup")).json()
    assert d["review_state"] == "contestada" and "[CPF]" in d["events"][0]["payload"]["reason"]
    r = client.post(f"/sd-qa/api/v1/evaluations/{eid}/contest/resolve", headers=H("tok-sup"), json={
        "decision": "revised", "comment": "Procede",
        "criteria": [{"key": "procedimentos", "status": "observed", "score": 100}]})
    assert r.json()["status"] == "contest_revised"


def test_summary_review_by_own_agent(client):
    rec = client.get("/sd-qa/api/v1/recordings/rec-a/analysis", headers=H("tok-ana")).json()
    sid = rec["summary"]["id"]
    assert client.post(f"/sd-qa/api/v1/summaries/{sid}/review", headers=H("tok-bruno"),
                       json={"action": "approve"}).status_code == 404
    content = rec["summary"]["content"]
    content["proxima_acao"] = {"texto": "Ligar para 11 98765-4321 amanhã", "tipo": "fato", "evidencia": []}
    r = client.post(f"/sd-qa/api/v1/summaries/{sid}/review", headers=H("tok-ana"), json={"action": "edit", "content": content})
    assert r.json()["status"] == "edited" and "[TELEFONE]" in r.json()["final_content"]["proxima_acao"]["texto"]


def test_rubric_versions(client):
    rubs = client.get("/sd-qa/api/v1/rubrics", headers=H("tok-qa")).json()["items"]
    assert rubs[0]["active"] and rubs[0]["evaluations"] == 2
    bad = {"name": "Teste", "criteria": [{"key": "a", "label": "A", "weight": 60}]}
    assert client.post("/sd-qa/api/v1/rubrics", headers=H("tok-qa"), json=bad).status_code == 422
    good = {"name": "Rubrica v2", "criteria": [{**c, "weight": c["weight"]} for c in rubs[0]["criteria"]]}
    assert client.post("/sd-qa/api/v1/rubrics", headers=H("tok-ana"), json=good).status_code == 403
    r = client.post("/sd-qa/api/v1/rubrics", headers=H("tok-qa"), json=good).json()
    assert r["version"] == 2 and r["active"] is False
    client.post(f"/sd-qa/api/v1/rubrics/{r['id']}/activate", headers=H("tok-qa"))
    rubs = client.get("/sd-qa/api/v1/rubrics", headers=H("tok-qa")).json()["items"]
    assert [x["version"] for x in rubs if x["active"]] == [2]


def test_metrics_and_csv(client):
    q = client.get("/sd-qa/api/v1/metrics/quality", headers=H("tok-sup")).json()
    assert q["gravacoes_recebidas"] == 2 and q["transcritas"] == 2 and q["taxa_sucesso"] == 1.0
    assert q["avaliacoes"] == 2 and q["reclamacoes"] == 1 and sum(q["distribuicao"].values()) == 2
    assert q["criterios"][0]["taxa_falha"] >= q["criterios"][-1]["taxa_falha"]
    own = client.get("/sd-qa/api/v1/metrics/quality", headers=H("tok-ana")).json()
    assert own["avaliacoes"] == 1
    assert client.get("/sd-qa/api/v1/export/evaluations.csv", headers=H("tok-ana")).status_code == 403
    csv = client.get("/sd-qa/api/v1/export/evaluations.csv", headers=H("tok-sup"))
    assert csv.status_code == 200 and csv.text.startswith("﻿id;created_at") and csv.text.count("\n") == 3


def test_reprocess_marks_access_and_service_token(client):
    assert client.post("/sd-qa/api/v1/recordings/rec-a/reprocess", headers=H("tok-ana"),
                       json={"mode": "analysis", "reason": "teste"}).status_code == 403
    r = client.post("/sd-qa/api/v1/recordings/rec-a/reprocess", headers=H("tok-sup"),
                    json={"mode": "analysis", "reason": "rubrica nova"})
    assert r.status_code == 202 and r.json()["run"] == 2
    m = client.post("/sd-qa/api/v1/recordings/rec-a/marks", headers=H("tok-ana"),
                    json={"start_s": 32.5, "end_s": 40.2, "label": "dados pessoais"})
    assert m.status_code == 201
    assert client.post("/sd-qa/api/v1/recordings/rec-b/marks", headers=H("tok-ana"),
                       json={"start_s": 1, "label": "x"}).status_code == 404
    client.post("/sd-qa/api/v1/access-log", headers=H("tok-ana"), json={"recording_id": "rec-a", "action": "play",
                                                                       "detail": {"position_s": 0, "rate": 1.5}})
    log = client.get("/sd-qa/api/v1/access-log?recording_id=rec-a", headers=H("tok-sup")).json()["items"]
    assert {"play", "mark"} <= {x["action"] for x in log}
    assert client.get("/sd-qa/api/v1/evaluations", headers=H(client.svc)).json()["total"] == 2
    eid = ev_id(client, "tok-sup", "rec-b")
    assert client.post(f"/sd-qa/api/v1/evaluations/{eid}/review", headers=H(client.svc),
                       json={"criteria": []}).status_code == 403
    assert client.get("/sd-qa/api/v1/evaluations", headers=H("sdqa_errado")).status_code == 401


@respx.mock
def test_sdops_down_is_503_not_success(settings, clean_db):
    settings.sd_ops_url = SDOPS
    import qa_pipeline.auth as A
    A._cache.clear()
    respx.get(f"{SDOPS}/auth/me").mock(side_effect=httpx.ConnectError("down"))
    c = TestClient(create_app(settings))
    assert c.get("/sd-qa/api/v1/evaluations", headers=H("tok-x")).status_code == 503
