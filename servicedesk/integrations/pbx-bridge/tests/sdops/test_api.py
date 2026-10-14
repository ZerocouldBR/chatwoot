"""API: URA (módulo 10), gravação assinada, métricas, retorno do A3, n8n (HMAC/anti-loop), idempotência, saúde."""
from __future__ import annotations

import hashlib
import hmac
import json
import time

import httpx
import pytest
import sqlalchemy as sa

from tests.sdops.conftest import URL, due_now, one, post, q, rt, run, session

pytestmark = pytest.mark.skipif(not URL, reason="SDOPS_TEST_DATABASE_URL não definido")
API = "/sd-ops/api/v1"
URA = {"X-SD-URA-Token": "u" * 32}


def _flow(env, cid="1760000100.1", **kw):
    post(env, rt(cid, **kw))
    run(env)


def test_ura_consulta_protocolo(env):
    _flow(env)
    num, prot = q(env, "select protocol_numeric, protocol from ops.support_tickets")[0]
    r = env.client.get(API + "/ura/tickets/" + num, params={"ani": "11999990001"}, headers=URA)
    assert r.status_code == 200
    assert r.json() == {"encontrado": "sim", "verificado": "sim", "protocolo": prot, "situacao": "novo",
                        "situacao_fala": "registrado e aguardando triagem", "proxima_acao": "aguarde o contato da equipe",
                        "fila": "3855-FILA_SUPORTE_1"}
    assert all(isinstance(v, str) for v in r.json().values())           # objeto plano de strings
    r = env.client.get(API + "/ura/tickets/" + num, params={"ani": "11988887777"}, headers=URA).json()
    assert r["verificado"] == "nao" and "situacao" not in r and r["proxima_acao"] == "transferir"
    bad = num[:-1] + str((int(num[-1]) + 1) % 10)
    assert env.client.get(API + "/ura/tickets/" + bad, headers=URA).json()["encontrado"] == "nao"
    # POST com corpo JSON simples (formato aceito pelo menu dinâmico) e Basic/token
    r = env.client.post(API + "/ura/tickets/" + num, json={"ani": "+5511999990001"}, headers=URA).json()
    assert r["verificado"] == "sim"
    assert one(env, "select count(*) from ops.audit_events where action='ura.lookup'") == 4
    assert "999990001" not in json.dumps([x[0] for x in q(env, "select data from ops.audit_events where action='ura.lookup'")])


def test_ura_limite(env):
    env.s.ura_rate_limit_per_min = 3
    codes = [env.client.get(API + "/ura/tickets/20260000000", params={"ani": "11911112222"}, headers=URA).status_code
             for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


def test_gravacao_url_assinada(env):
    _flow(env)
    rid = one(env, "select id from ops.call_recordings")
    ha = session(env)                                                   # Ana foi a agente da chamada
    r = env.client.get(API + "/recordings/%s/url" % rid, headers=ha)
    assert r.status_code == 200 and r.json()["expires_in"] == 300
    url = r.json()["url"]
    assert "55pbx" not in url
    full = env.client.get(url)
    assert full.status_code == 200 and full.headers["content-type"] == "audio/wav" and full.content[:4] == b"RIFF"
    part = env.client.get(url, headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100
    assert env.client.get(url[:-2] + "00").status_code == 403           # adulterado
    assert one(env, "select count(*) from ops.audit_events where action='recording.url_issued'") == 1
    assert one(env, "select count(*) from ops.audit_events where action='recording.accessed'") == 2
    # Bruno (agente sem vínculo com a chamada) não ouve; supervisor ouve
    with env.engine.begin() as conn:
        conn.execute(sa.text("delete from ops.user_roles"))
    assert env.client.get(API + "/recordings/%s/url" % rid, headers=session(env, "tok-bruno")).status_code == 403
    assert env.client.get(API + "/recordings/%s/url" % rid, headers=session(env, "tok-admin")).status_code == 200
    env.s.recording_url_ttl_s = -1
    exp = env.client.get(API + "/recordings/%s/url" % rid, headers=ha).json()["url"]
    assert env.client.get(exp).status_code == 410
    meta = env.client.get(API + "/recordings/" + rid, headers={"Authorization": "Bearer sdsvc_qa"}).json()
    assert meta["storage_key"].startswith("recordings/dev55/") and meta["status"] == "stored"


def test_metricas_e_formulas(env):
    from tests.sdops.test_scenarios import _miss
    _flow(env, "1760000101.1")                                            # atendida, espera 15
    _flow(env, "1760000101.2", call_number="999990002", call_time_waiting=30)   # atendida, espera 30 (> 20)
    post(env, _miss("1760000101.3", call_number="999990003", call_time_waiting=40))   # abandono na fila
    post(env, _miss("1760000101.4", call_number="999990004", call_queue="", call_time_waiting=0))   # perdida
    post(env, rt("1760000101.5", call_type="active", call_number="999990005"))    # efetuada
    run(env)
    h = session(env, "tok-bruno")                                         # supervisor
    r = env.client.get(API + "/metrics/telephony", params={"from": "2026-10-13T00:00:00Z", "detail": "true"},
                       headers=h).json()
    t = r["groups"]["total"]
    assert (t["recebidas"], t["atendidas"], t["abandonadas"], t["perdidas"], t["efetuadas"]) == (4, 2, 1, 1, 1)
    assert t["tme_s"] == 22.5 and t["tma_receptivo_s"] == 30.0
    assert t["nivel_servico"] == round(1 / 3, 4)                          # 1 em ≤20 s ÷ (2 atendidas + 1 abandono > 5 s)
    assert t["taxa_abandono"] == 0.25 and len(t["ids"]["atendidas"]) == 2
    assert r["callbacks"]["criados"] == 2
    assert env.client.get(API + "/metrics/telephony", headers=session(env)).status_code == 403   # agente não vê
    tk = env.client.get(API + "/metrics/tickets", params={"from": "2026-10-01T00:00:00Z"}, headers=h).json()
    assert tk["criados"] == 5 and tk["backlog_agora"] == 5 and tk["sla"]["first_response"]["instancias"] == 5
    s = env.client.get(API + "/reports/summary", headers={"Authorization": "Bearer sdsvc_n8n", "X-SD-Tenant": "dev55"})
    assert s.status_code == 200 and s.json()["tickets"]["criados"] == 5


def test_retorno_analise_a3(env):
    _flow(env)
    rid, call_id = q(env, "select id, call_id from ops.call_recordings")[0]
    svc = {"Authorization": "Bearer sdsvc_qa"}
    body = {"kind": "qa", "status": "completed", "recording_id": rid, "external_id": "qa.evaluations:7", "score": 87.5,
            "data": {"rubric_version": "v1"}}
    r1 = env.client.post(API + "/analysis-results", json=body, headers=svc)
    r2 = env.client.post(API + "/analysis-results", json=body, headers=svc)
    assert r1.status_code == 200 and r1.json()["duplicate"] is False and r2.json()["duplicate"] is True
    assert one(env, "select count(*) from ops.ticket_activities where kind='analise'") == 1
    assert one(env, "select call_id from ops.analysis_refs") == call_id
    assert env.client.post(API + "/analysis-results", json=dict(body, score=120, external_id="x"), headers=svc).status_code == 422
    assert env.client.post(API + "/analysis-results", json=body, headers=session(env)).status_code == 403


def test_n8n_hmac_e_anti_loop(env, monkeypatch):
    monkeypatch.setenv("N8N_TOKEN", "tok-n8n")
    monkeypatch.setenv("N8N_SECRET", "segredo-hmac")
    got = []

    def handler(req):
        got.append(req)
        return httpx.Response(200)
    env.svc.worker.http = httpx.Client(transport=httpx.MockTransport(handler))
    ha = session(env, "tok-admin")
    for name, types in (("WF06", ["ticket.created"]), ("WF04", ["ticket.*"])):
        r = env.client.post(API + "/admin/automation-routes", json={"name": name, "event_types": types,
                            "url": "https://n8n.exemplo.test/webhook/sd/" + name.lower(), "token_ref": "N8N_TOKEN",
                            "secret_ref": "N8N_SECRET"}, headers=ha)
        assert r.status_code == 201
    # ticket criado pelo n8n (WF06): não volta para o WF06, vai para o WF04
    svc = {"Authorization": "Bearer sdsvc_n8n", "X-SD-Tenant": "dev55", "X-SD-Origin": "n8n", "X-SD-Workflow": "WF06",
           "Idempotency-Key": "exec-1:no-3"}
    r1 = env.client.post(API + "/tickets", json={"subject": "Teste n8n", "contact_e164": "11999990001"}, headers=svc)
    r2 = env.client.post(API + "/tickets", json={"subject": "Teste n8n", "contact_e164": "11999990001"}, headers=svc)
    assert r1.status_code == 201 and r2.status_code == 201 and r1.json()["id"] == r2.json()["id"]
    assert r2.headers.get("idempotent-replay") == "true"
    run(env)
    assert [g.url.path for g in got] == ["/webhook/sd/wf04"]
    req = got[0]
    body = req.content
    exp = "sha256=" + hmac.new(b"segredo-hmac", req.headers["x-sd-timestamp"].encode() + b"." + body, hashlib.sha256).hexdigest()
    assert req.headers["x-sd-signature"] == exp and req.headers["x-sd-webhook-token"] == "tok-n8n"
    env_ = json.loads(body)
    assert env_["type"] == "ticket.created" and env_["caused_by"] == "n8n:WF06" and env_["payload"]["protocol"]
    st = dict(q(env, "select r.name, e.status from ops.automation_executions e join ops.automation_routes r on r.id=e.route_id"))
    assert st == {"WF06": "skipped_loop", "WF04": "ok"}


def test_saude_e_metricas(env):
    _flow(env)
    h = env.client.get("/sd-ops/api/v1/ready").json()
    assert h["status"] == "ok" and h["migration"] == "0001" and h["redis"] == "ok"
    assert env.client.get("/integracoes/55pbx/health").json()["enabled"] is True
    txt = env.client.get("/sd-ops/metrics").text
    assert "sdops_webhook_received_total" in txt and "sdops_outbox_processed_total" in txt
    assert "sdops_inbox_pending 0" in txt
    r = env.client.get("/sd-ops/health", headers={"X-Request-ID": "abc-123"})
    assert r.headers["x-request-id"] == "abc-123"


def test_sla_vencido_publica(env):
    _flow(env)
    with env.engine.begin() as conn:
        conn.execute(sa.text("update ops.sla_instances set due_at = now() - interval '1 minute' where metric='resolution'"))
    env.svc.worker.maintenance_once()
    run(env)
    assert one(env, "select breached from ops.sla_instances where metric='resolution'") is True
    assert "sla.breached" in env.pub.types()
    ar = env.client.get(API + "/sla/at-risk", params={"within": 0}, headers=session(env, "tok-bruno")).json()
    assert ar["items"][0]["breached"] is True


def test_classificacao_humana_politica_ask(env):
    with env.engine.begin() as conn:
        conn.execute(sa.text("update ops.ticket_open_rules set reuse='ask' where tenant_id='dev55'"))
    _flow(env)
    assert one(env, "select count(*) from ops.support_tickets") == 0
    h = session(env)
    items = env.client.get(API + "/calls", params={"needs_classification": "true"}, headers=h).json()["items"]
    assert len(items) == 1
    r = env.client.post(API + "/tickets", json={"subject": "Classificado", "call_id": items[0]["id"]}, headers=h)
    assert r.status_code == 201
    assert env.client.get(API + "/calls", params={"needs_classification": "true"}, headers=h).json()["items"] == []
