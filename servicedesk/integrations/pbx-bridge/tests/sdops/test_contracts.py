"""Contratos fechados na integração final (WEBHOOK_CONTRACTS.md §8.3/§8.4, CTI_AUTH.md §3):
log de notificações idempotente, perfil de token do n8n, qa.completed -> n8n (WF11) e GET /capabilities."""
from __future__ import annotations

import hashlib
import hmac
import json
import os

import httpx
import pytest

from tests.sdops.conftest import URL, one, q, run, session, rt, post

pytestmark = pytest.mark.skipif(not URL, reason="SDOPS_TEST_DATABASE_URL não definido")
API = "/sd-ops/api/v1"
N8N = {"Authorization": "Bearer sdsvc_n8n", "X-SD-Tenant": "dev55", "X-SD-Origin": "n8n", "X-SD-Workflow": "WF05"}
QA = {"Authorization": "Bearer sdsvc_qa"}
HERE = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------------ a) /notifications/log idempotente
def test_notificacao_idempotente_por_chave(env):
    body = {"channel": "whatsapp", "ticket_id": "t-1", "template": "pos_atendimento", "status": "enviando",
            "detail": {"tipo": "whatsapp_pos_atendimento", "workflow": "WF05"}}
    h = dict(N8N, **{"Idempotency-Key": "whatsapp_pos_atendimento:t-1"})
    r1 = env.client.post(API + "/notifications/log", json=body, headers=h)
    assert r1.status_code == 201 and r1.json()["duplicate"] is False
    assert r1.json()["dedupe_key"] == "whatsapp_pos_atendimento:t-1"
    assert "idempotent-replay" not in r1.headers
    # outra execução do workflow (o n8n perdeu o static data): mesma chave -> registro original, sem gravar de novo
    r2 = env.client.post(API + "/notifications/log", json=dict(body, status="sent"), headers=h)
    assert r2.status_code == 200 and r2.headers["idempotent-replay"] == "true"
    assert r2.json()["duplicate"] is True and r2.json()["id"] == r1.json()["id"] and r2.json()["status"] == "enviando"
    assert one(env, "select count(*) from ops.notification_logs") == 1
    assert one(env, "select count(*) from ops.audit_events where action like 'notification.%'") == 1
    assert one(env, "select caused_by from ops.notification_logs") == "n8n:WF05"
    # dedupe_key no corpo vale mais que o header; chave diferente = envio novo
    r3 = env.client.post(API + "/notifications/log", json=dict(body, dedupe_key="csat:t-1"), headers=h)
    assert r3.status_code == 201 and r3.json()["dedupe_key"] == "csat:t-1"
    # a chave é por tenant
    r4 = env.client.post(API + "/notifications/log", json=body, headers=dict(h, **{"X-SD-Tenant": "outro"}))
    assert r4.status_code == 201
    # sem chave nenhuma: 422 (o registro precisa ser idempotente)
    r5 = env.client.post(API + "/notifications/log", json=body, headers=N8N)
    assert r5.status_code == 422 and r5.json()["error"] == "dedupe_key_required"
    # consulta (n8n/supervisor) e permissão
    items = env.client.get(API + "/notifications/log", params={"ticket_id": "t-1"}, headers=N8N).json()["items"]
    assert sorted(i["dedupe_key"] for i in items) == ["csat:t-1", "whatsapp_pos_atendimento:t-1"]
    assert env.client.post(API + "/notifications/log", json=dict(body, dedupe_key="x"), headers=session(env)).status_code == 403
    assert env.client.post(API + "/notifications/log", json=dict(body, dedupe_key="x"), headers=QA).status_code == 403


def test_notificacao_concorrente_grava_uma_vez(env):
    import threading
    res = []
    body = {"channel": "email", "ticket_id": "t-9", "status": "enviando", "dedupe_key": "email_protocolo:t-9"}

    def go():
        res.append(env.client.post(API + "/notifications/log", json=body, headers=N8N).status_code)
    ts = [threading.Thread(target=go) for _ in range(6)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sorted(res) == [200] * 5 + [201]
    assert one(env, "select count(*) from ops.notification_logs") == 1


# ------------------------------------------------------------------ b) perfil n8n do token de serviço
def test_new_service_token_perfil_n8n(capsys):
    from sd_ops.__main__ import main
    from sd_ops.auth import SERVICE_PROFILES
    assert main(["new-service-token", "n8n"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    tok = out[0].rsplit(" ", 1)[-1]
    entry = json.loads(out[-1])["n8n"]
    assert tok.startswith("sdsvc_") and entry["sha256"] == hashlib.sha256(tok.encode()).hexdigest()
    for sc in ("tickets:write", "notify:send", "reconcile:run", "reports:read"):
        assert sc in entry["scopes"]
    assert "tickets:close" not in entry["scopes"] and "dial:write" not in entry["scopes"]
    assert entry["scopes"] == SERVICE_PROFILES["n8n"]
    assert main(["new-service-token", "integra", "--profile", "qa-pipeline", "--scopes", "reports:read",
                 "--tenants", "b2b,dev55"]) == 0
    e2 = json.loads(capsys.readouterr().out.strip().splitlines()[-1])["integra"]
    assert e2["tenants"] == ["b2b", "dev55"] and "analysis:write" in e2["scopes"] and "reports:read" in e2["scopes"]
    assert main(["new-service-token", "x", "--scopes", "tudo:liberado"]) == 2
    assert main(["new-service-token", "x", "--profile", "inexistente"]) == 2


def test_perfil_n8n_cobre_os_endpoints_dos_workflows(env):
    """Cada rota de sdops_endpoints_used.json (gerado pelo build dos workflows) aceita o token com o perfil n8n:
    nenhuma resposta 401/403."""
    from sd_ops.auth import SERVICE_PROFILES
    from sd_ops import db
    env.s.service_tokens["n8n-perfil"] = {"sha256": db.sha256("sdsvc_perfil"), "tenants": ["*"],
                                          "scopes": SERVICE_PROFILES["n8n"]}
    used = json.load(open(os.path.join(HERE, "..", "..", "..", "n8n", "sdops_endpoints_used.json"), encoding="utf-8"))
    h = {"Authorization": "Bearer sdsvc_perfil", "X-SD-Tenant": "dev55", "X-SD-Origin": "n8n", "X-SD-Workflow": "WF99",
         "Idempotency-Key": "perfil-1"}
    bodies = {"POST /reconciliations": {"from": "2026-10-12T00:00:00Z", "to": "2026-10-13T00:00:00Z"},
              "POST /notifications/log": {"channel": "email", "status": "simulado"},
              "POST /tickets/{id}/reopen": {"to": "em_atendimento", "reason": "teste"},
              "POST /tickets/{id}/notes": {"kind": "nota_interna", "body": "teste", "post_to_chatwoot": False},
              "POST /tickets/{id}/links": {"conversation_id": 1}}
    seen = set()
    for wf, routes in used.items():
        for rt_ in routes:
            if rt_ in seen:
                continue
            seen.add(rt_)
            method, path = rt_.split(" ", 1)
            url = API + path.replace("{id}", "00000000-0000-0000-0000-000000000000")
            r = env.client.request(method, url, json=bodies.get(rt_), headers=h)
            assert r.status_code not in (401, 403), (wf, rt_, r.status_code, r.text)
    assert len(seen) >= 10


# ------------------------------------------------------------------ c) qa.completed -> n8n (WF11)
def _routes(env, monkeypatch, got):
    monkeypatch.setenv("N8N_TOKEN", "tok-n8n")
    monkeypatch.setenv("N8N_SECRET", "segredo-hmac")

    def handler(req):
        got.append(req)
        return httpx.Response(200)
    env.svc.worker.http = httpx.Client(transport=httpx.MockTransport(handler))
    ha = session(env, "tok-admin")
    for name, types in (("WF11", ["qa.completed"]), ("WF02", ["call.ended", "recording.*"])):
        r = env.client.post(API + "/admin/automation-routes", json={
            "name": name, "event_types": types, "url": "https://n8n.exemplo.test/webhook/sd/" + name.lower(),
            "token_ref": "N8N_TOKEN", "secret_ref": "N8N_SECRET"}, headers=ha)
        assert r.status_code == 201


def test_qa_completed_vai_ao_wf11_pela_ponte_hmac(env, monkeypatch):
    got = []
    post(env, rt("1760000300.1"))
    run(env)
    _routes(env, monkeypatch, got)
    rid, call_id = q(env, "select id, call_id from ops.call_recordings")[0]
    tid, prot = q(env, "select id, protocol from ops.support_tickets")[0]
    conv = one(env, "select conversation_id from ops.calls where id = :c", c=call_id)
    body = {"kind": "qa", "status": "completed", "recording_id": rid, "external_id": "qa.qa_evaluations:42",
            "score": 41.5, "completed_at": "2026-10-13T18:10:00Z",
            "data": {"rubric_version": "v1", "alerts": ["reclamacao", "supervisor"],
                     "console_url": "https://helpdesk.exemplo.test/sd-console/qa/avaliacoes/42"}}
    r = env.client.post(API + "/analysis-results", json=body, headers=QA)
    assert r.status_code == 200 and r.json()["forwarded"] is True
    assert env.client.post(API + "/analysis-results", json=body, headers=QA).json() == {"duplicate": True}
    # transcrição não vai ao n8n
    env.client.post(API + "/analysis-results", json={"kind": "transcription", "status": "completed",
                                                      "recording_id": rid, "external_id": "qa.transcriptions:9"},
                    headers=QA)
    env.pub.events.clear()
    got.clear()
    run(env)
    qa_reqs = [g for g in got if g.headers["x-sd-event-type"] == "qa.completed"]
    assert len(qa_reqs) == 1 and qa_reqs[0].url.path == "/webhook/sd/wf11"
    req = qa_reqs[0]
    exp = "sha256=" + hmac.new(b"segredo-hmac", req.headers["x-sd-timestamp"].encode() + b"." + req.content,
                               hashlib.sha256).hexdigest()
    assert req.headers["x-sd-signature"] == exp and req.headers["x-sd-webhook-token"] == "tok-n8n"
    assert req.headers["x-sd-origin"] == "sd-ops"
    ev = json.loads(req.content)
    p = ev["payload"]
    assert ev["type"] == "qa.completed" and ev["source"] == "sd-ops" and ev["caused_by"] is None
    assert p["evaluation_id"] == "42" and p["score"] == 41.5 and p["alerts"] == ["reclamacao", "supervisor"]
    assert p["ticket_id"] == tid and p["ticket_protocol"] == prot and p["conversation_id"] == conv
    assert p["call_id"] == call_id and p["is_recommendation"] is True and p["console_url"].endswith("/42")
    assert ev["subject"]["conversation_id"] == conv and ev["occurred_at"] == "2026-10-13T18:10:00Z"
    # não duplica o evento no sd:events (o qa-pipeline já publica o original)
    assert "qa.completed" not in env.pub.types()
    # reprocessar a outbox não reenvia
    got.clear()
    run(env)
    assert got == []
    st = q(env, "select r.name, e.status from ops.automation_executions e join ops.automation_routes r on "
                "r.id = e.route_id where e.event_type = 'qa.completed'")
    assert st == [("WF11", "ok")]


def test_qa_completed_anti_loop_e_sem_chamada(env, monkeypatch):
    got = []
    _routes(env, monkeypatch, got)
    # resultado reenviado por um fluxo do próprio WF11 (X-SD-Origin n8n): não volta para o WF11
    h = dict(QA, **{"X-SD-Origin": "n8n", "X-SD-Workflow": "WF11"})
    r = env.client.post(API + "/analysis-results", json={"kind": "qa", "status": "partial", "score": None,
                                                         "external_id": "qa.qa_evaluations:77",
                                                         "data": {"alerts": ["supervisor"]}}, headers=h)
    assert r.status_code == 200 and r.json()["forwarded"] is True
    run(env)
    assert got == []
    assert q(env, "select status from ops.automation_executions where event_type='qa.completed'") == [("skipped_loop",)]
    # sem X-SD-Origin: entregue, mesmo sem chamada/ticket (ids nulos)
    r = env.client.post(API + "/analysis-results", json={"kind": "qa", "status": "completed", "score": 90,
                                                         "external_id": "qa.qa_evaluations:78"}, headers=QA)
    run(env)
    assert len(got) == 1
    p = json.loads(got[0].content)["payload"]
    assert p["evaluation_id"] == "78" and p["ticket_id"] is None and p["conversation_id"] is None
    # status failed não é qa.completed
    r = env.client.post(API + "/analysis-results", json={"kind": "qa", "status": "failed",
                                                         "external_id": "qa.qa_evaluations:79"}, headers=QA)
    assert r.json()["forwarded"] is False


# ------------------------------------------------------------------ d) GET /capabilities
def test_capabilities_por_usuario(env, monkeypatch):
    ana = env.client.get(API + "/capabilities", headers=session(env)).json()
    c = ana["capabilities"]
    assert set(c) == {"dial", "webphone", "callbacks", "recordings", "ura"}
    assert c["dial"]["enabled"] is True and c["dial"]["mode"] == "mock" and c["dial"]["branch"] == "5005"
    assert "MOCK" in c["dial"]["reason"]
    assert c["webphone"] == {"enabled": False, "mode": "external", "url": None,
                             "reason": "webphone da 55PBX não configurado no sd-ops (PBX_WEBPHONE_URL)"}
    assert c["callbacks"]["enabled"] is True and c["recordings"]["enabled"] is True
    assert c["recordings"]["mode"] == "local" and c["ura"]["enabled"] is True
    assert ana["tenant_id"] == "dev55" and ana["env"] == "dev"
    # Bruno não tem ramal mapeado: discagem desabilitada com o motivo
    br = env.client.get(API + "/capabilities", headers=session(env, "tok-bruno")).json()["capabilities"]
    assert br["dial"]["enabled"] is False and "ramal" in br["dial"]["reason"]
    # webphone configurado
    env.s.webphone_url = "https://fone.55pbx.test"
    c = env.client.get(API + "/capabilities", headers=session(env)).json()["capabilities"]
    assert c["webphone"] == {"enabled": True, "mode": "external", "url": "https://fone.55pbx.test", "reason": None}
    # discagem desligada no servidor
    env.s.dial_mode = "disabled"
    c = env.client.get(API + "/capabilities", headers=session(env)).json()["capabilities"]
    assert c["dial"]["enabled"] is False and "PBX_DIAL_MODE=disabled" in c["dial"]["reason"]
    # URA sem credencial no ambiente
    monkeypatch.delenv("URA_TOKEN_DEV55")
    c = env.client.get(API + "/capabilities", headers=session(env)).json()["capabilities"]
    assert c["ura"]["enabled"] is False and c["ura"]["reason"]


def test_capabilities_servico_e_sem_autenticacao(env):
    c = env.client.get(API + "/capabilities", headers=QA).json()["capabilities"]
    assert c["dial"]["enabled"] is False and "dial:write" in c["dial"]["reason"]
    assert c["callbacks"]["enabled"] is False and c["recordings"]["enabled"] is True
    assert env.client.get(API + "/capabilities").status_code == 401
    env.s.recording_url_secret = ""
    c = env.client.get(API + "/capabilities", headers=session(env)).json()["capabilities"]
    assert c["recordings"]["enabled"] is False and "RECORDING_URL_SECRET" in c["recordings"]["reason"]
