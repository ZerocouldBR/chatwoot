"""Cenários obrigatórios do prompt mestre (§17) que são do A2: 1–17, 21–25, 28–30.
Postgres real de teste + Chatwoot/55PBX/stream falsos. Dados FICTÍCIOS."""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json

import httpx
import pytest
import sqlalchemy as sa

from pbx_bridge.audio import AudioError
from pbx_bridge.chatwoot import ChatwootError
from pbx_bridge.pbx_api import PbxApi
from sd_ops import models as m
from tests.sdops.conftest import (SECRET, SECRET_OUTRO, URL, due_now, one, post, q, rt, run, session, wav)

pytestmark = pytest.mark.skipif(not URL, reason="SDOPS_TEST_DATABASE_URL não definido")
API = "/sd-ops/api/v1"


def stream_types(env):
    return env.pub.types()


def conv_msgs(cw, conv):
    return [mm["source_id"] for mm in cw.msgs[conv]]


# ---------------------------------------------------------------- 1. cliente novo
def test_s01_cliente_novo(env, cw):
    assert post(env, rt("1760000001.1", "start")).status_code == 202
    r = post(env, rt("1760000001.1"))
    assert r.status_code == 202 and r.json()["accepted"] is True
    run(env)
    call = q(env, "select state, outcome, number_e164, talk_s, total_s, wait_s, contact_id, conversation_id from ops.calls")
    assert len(call) == 1
    state, outcome, num, talk, total, wait, contact_id, conv = call[0]
    assert (state, outcome, num, talk, total, wait) == ("ended", "answered", "+5511999990001", 30, 45, 15)
    assert len(cw.contacts) == 1 and cw.contacts[0]["phone_number"] == "+5511999990001"
    assert contact_id == cw.contacts[0]["id"] and conv in cw.convs
    t = q(env, "select protocol, protocol_numeric, status, contact_id, first_response_at, origin from ops.support_tickets")
    assert len(t) == 1
    protocol, numeric, status, t_contact, fr, origin = t[0]
    assert protocol.startswith("DEV-2026-") and len(numeric) == 11 and status == "novo" and t_contact == contact_id
    assert fr is not None and origin == "call_inbound"   # ligação atendida = primeira resposta
    ca = cw.convs[conv]["custom_attributes"]
    assert ca["sd_protocolo"] == protocol and ca["zd_status"] == "Novo" and ca["pbx_call_id"] == "1760000001.1"
    srcs = conv_msgs(cw, conv)
    assert "55pbx:1760000001.1:registro" in srcs and "55pbx:1760000001.1:atualizacao" in srcs
    types = stream_types(env)
    for tname in ("call.started", "call.ended", "ticket.created", "recording.stored"):
        assert tname in types, tname
    rs = [e for e in env.pub.events if e["type"] == "recording.stored"][0]["payload"]
    assert rs["mime"] == "audio/wav" and rs["integrity"] == "ok" and abs(rs["duration_s"] - 30) < 0.1
    assert rs["ticket_id"] and rs["conversation_id"] == conv and len(rs["sha256"]) == 64
    assert "+5511999990001" not in json.dumps(env.pub.events)   # número completo nunca vai ao stream
    assert env.storage.size(rs["storage_key"]) == rs["size_bytes"]
    # a gravação foi anexada à conversa (MP3 derivado) quando ficou disponível
    assert any(mm["attachments"] for mm in cw.msgs[conv])


# ---------------------------------------------------------------- 2/24. cliente existente (telefone + e-mail)
def test_s02_s24_cliente_existente_com_email(env, cw):
    cw.contacts.append({"id": 500, "name": "Cliente Antigo", "phone_number": "+551199990001",
                        "email": "cliente@exemplo.test"})          # sem o 9º dígito
    post(env, rt("1760000002.1"))
    run(env)
    assert len(cw.contacts) == 1
    t = q(env, "select contact_id, contact_email, contact_name from ops.support_tickets")[0]
    assert t == (500, "cliente@exemplo.test", "Cliente Antigo")
    h = session(env)
    ctx = env.client.get(API + "/context", params={"contact_id": 500}, headers=h).json()
    assert ctx["contact"]["email"] == "cliente@exemplo.test" and ctx["identification"] == "unique"
    assert len(ctx["open_tickets"]) == 1 and len(ctx["recent_calls"]) == 1
    # conversa de e-mail ligada ao mesmo ticket; resposta pública do agente para o SLA de 1ª resposta
    tid = ctx["open_tickets"][0]["id"]
    assert env.client.post(API + "/tickets/%s/links" % tid, json={"conversation_id": 9001}, headers=h).status_code == 200
    assert 9001 in env.client.get(API + "/tickets/" + tid, headers=h).json()["conversations"]


def test_s24_telefone_ambiguo_nao_mescla(env, cw):
    cw.contacts += [{"id": 601, "name": "A", "phone_number": "+5511999990001"},
                    {"id": 602, "name": "B", "phone_number": "+551199990001"}]
    post(env, rt("1760000024.1"))
    run(env)
    assert len(cw.contacts) == 2       # nada criado, nada mesclado
    assert one(env, "select needs_identification from ops.support_tickets") is True


# ---------------------------------------------------------------- 3. chamadas sucessivas
def test_s03_sucessivas_reaproveita_ticket(env, cw):
    post(env, rt("1760000003.1"))
    run(env)
    post(env, rt("1760000003.2", call_date="2026-10-13 10:20:00"))
    run(env)
    assert one(env, "select count(*) from ops.calls") == 2
    assert one(env, "select count(*) from ops.support_tickets") == 1
    assert one(env, "select count(*) from ops.ticket_calls") == 2
    assert one(env, "select count(*) from ops.ticket_conversations") == 2
    assert one(env, "select ticket_policy from ops.calls where root_provider_call_id='1760000003.2'").startswith("reused:")


def test_s03_sucessivas_politica_nova_ocorrencia(env):
    with env.engine.begin() as conn:
        conn.execute(sa.text("update ops.ticket_open_rules set reuse='new' where tenant_id='dev55'"))
    post(env, rt("1760000003.3"))
    post(env, rt("1760000003.4", call_date="2026-10-13 10:20:00"))
    run(env)
    assert one(env, "select count(*) from ops.support_tickets") == 2


# ---------------------------------------------------------------- 4. duas simultâneas
def test_s04_duas_simultaneas(env, cw):
    post(env, rt("1760000004.1", "start"))
    post(env, rt("1760000004.2", "start", call_number="999990002", branch_mask=5010))
    run(env)
    assert one(env, "select count(*) from ops.calls where state='active'") == 2
    post(env, rt("1760000004.2", call_number="999990002", branch_mask=5010))
    post(env, rt("1760000004.1"))
    run(env)
    rows = q(env, "select root_provider_call_id, number_e164, state, branch from ops.calls order by 1")
    assert rows == [("1760000004.1", "+5511999990001", "ended", "5005"), ("1760000004.2", "+5511999990002", "ended", "5010")]
    assert one(env, "select count(*) from ops.support_tickets") == 2
    assert len(cw.convs) == 2 and len(cw.contacts) == 2
    assert one(env, "select count(distinct ticket_id) from ops.ticket_calls") == 2


# ---------------------------------------------------------------- 5/6/7. duplicados e fora de ordem
def test_s05_inicial_duplicado(env, cw):
    r1 = post(env, rt("1760000005.1", "start"))
    r2 = post(env, rt("1760000005.1", "start"), method="PUT")
    assert r1.status_code == 202 and r2.status_code == 200 and r2.json()["duplicate"] is True
    assert r1.json()["id"] == r2.json()["id"]
    run(env)
    assert one(env, "select count(*) from ops.call_events") == 1
    assert stream_types(env).count("call.started") == 1


def test_s06_final_duplicado(env, cw):
    post(env, rt("1760000006.1"))
    run(env)
    # mesmo conteúdo com formatação diferente (passa pela inbox, cai na chave da call_events)
    env.client.post("/integracoes/55pbx/webhook/" + SECRET, content=json.dumps(rt("1760000006.1"), indent=2),
                    headers={"content-type": "application/json"})
    run(env)
    assert one(env, "select count(*) from ops.webhook_inbox") == 2
    assert one(env, "select count(*) from ops.call_events") == 1
    assert stream_types(env).count("call.ended") == 1
    assert one(env, "select count(*) from ops.call_recordings") == 1
    conv = one(env, "select conversation_id from ops.calls")
    srcs = conv_msgs(cw, conv)
    assert len(srcs) == len(set(srcs))


def test_s07_final_antes_do_inicial(env, cw):
    post(env, rt("1760000007.1"))
    run(env)
    post(env, rt("1760000007.1", "start"))
    run(env)
    st, talk, total, legs = q(env, "select state, talk_s, total_s, legs_count from ops.calls")[0]
    assert (st, talk, total, legs) == ("ended", 30, 45, 1)
    assert one(env, "select count(*) from ops.call_events") == 2
    t = stream_types(env)
    assert t.count("call.started") == 1 and t.count("call.ended") == 1
    assert one(env, "select count(*) from ops.support_tickets") == 1


# ---------------------------------------------------------------- 8/9. transferências
def test_s08_transferencia_entre_ramais_multipla(env, cw):
    post(env, rt("1760000008.1", "start"))
    post(env, rt("1760000008.1", call_transfer_id="1760000008.2"))          # 3º envio (transferência)
    post(env, rt("1760000008.2", "start", branch_mask=5010))
    post(env, rt("1760000008.2", branch_mask=5010, call_transfer_id="1760000008.3"))
    post(env, rt("1760000008.3", branch_mask=5005, call_time=70, call_duration=60))
    run(env)
    assert one(env, "select count(*) from ops.calls where state <> 'merged'") == 1
    st, legs, branch, talk = q(env, "select state, legs_count, branch, talk_s from ops.calls")[0]
    assert (st, legs, branch, talk) == ("ended", 3, "5005", 120)
    seqs = q(env, "select seq, provider_call_id, state from ops.call_legs order by seq")
    assert [s[1] for s in seqs] == ["1760000008.1", "1760000008.2", "1760000008.3"]
    assert one(env, "select count(*) from ops.support_tickets") == 1
    assert stream_types(env).count("call.transferred") == 2 and stream_types(env).count("call.ended") == 1
    conv = one(env, "select conversation_id from ops.calls")
    srcs = conv_msgs(cw, conv)
    assert "55pbx:1760000008.1:perna:1760000008.2" in srcs and "55pbx:1760000008.1:perna:1760000008.3" in srcs
    assert len(cw.convs) == 1


def test_s08_transferencia_fora_de_ordem_mescla(env, cw):
    with env.engine.begin() as conn:
        conn.execute(sa.text("update ops.ticket_open_rules set reuse='new' where tenant_id='dev55'"))
    post(env, rt("1760000018.2", branch_mask=5010))                       # perna nova chega antes
    run(env)
    post(env, rt("1760000018.1", call_transfer_id="1760000018.2"))
    run(env)
    live = q(env, "select id, legs_count from ops.calls where state <> 'merged'")
    assert len(live) == 1 and live[0][1] == 2
    assert one(env, "select count(*) from ops.calls where state='merged'") == 1
    assert q(env, "select status from ops.support_tickets") == [("novo",)]     # o ticket da perna é herdado
    assert len(cw.convs) == 1
    # as duas pernas já tinham ticket próprio (inicial da original chegou antes da transferência): mescla e cancela 1
    post(env, rt("1760000019.2", branch_mask=5010, call_number="999990019"))
    post(env, rt("1760000019.1", "start", call_number="999990019"))
    run(env)
    post(env, rt("1760000019.1", call_transfer_id="1760000019.2", call_number="999990019"))
    run(env)
    st = q(env, "select status, cancel_reason from ops.support_tickets where contact_e164='+5511999990019'")
    assert sorted(x[0] for x in st) == ["cancelado", "novo"]
    assert any("mesclado" in (x[1] or "") for x in st)


def test_s09_transferencia_entre_filas_pelo_report02(env, cw):
    rows = [
        {"call_id": "1760000009.1", "name": "Ana Teste", "call_time_total_duration": "00:00:40", "call_time_waiting": "00:00:05",
         "call_time_spoken": "00:00:30", "branch_number_agent": "5005", "call_number": "999990009", "call_area_code": "11",
         "wg_country_code": "55", "call_date": "13/10/2026", "wb_call_hour": "10:00:00", "queue_name": "3855-FILA_SUPORTE_1",
         "type_call": "receptivo", "call_id_origin": ""},
        {"call_id": "1760000009.2", "name": "Bruno Ficticio", "call_time_total_duration": "00:01:00", "call_time_waiting": "00:00:10",
         "call_time_spoken": "00:00:50", "branch_number_agent": "5010", "call_number": "999990009", "call_area_code": "11",
         "wg_country_code": "55", "call_date": "13/10/2026", "wb_call_hour": "10:01:00", "queue_name": "3855-FILA_FINANCEIRO_1",
         "type_call": "receptivo", "call_id_origin": "1760000009.1"},
    ]
    with env.engine.begin() as conn:
        from sd_ops.worker import accept
        for r in rows:
            accept(conn, "dev55", "report02", json.dumps(r).encode(), "application/json")
    run(env)
    legs = q(env, "select seq, queue, transferred_from_leg_id is not null from ops.call_legs order by seq")
    assert legs == [(1, "3855-FILA_SUPORTE_1", False), (2, "3855-FILA_FINANCEIRO_1", True)]
    assert one(env, "select count(*) from ops.calls where state <> 'merged'") == 1
    assert "call.transferred" in stream_types(env)


# ---------------------------------------------------------------- 10/11. perdidas e abandonadas
def _miss(call_id, **kw):
    d = rt(call_id, "start", **kw)
    d.update(call_status="", call_time=kw.pop("dur", 20), call_duration=0, call_time_waiting=kw.get("call_time_waiting", 20),
             call_disconnection="cliente")
    d.update(kw)
    return d


def test_s10_perdida_gera_callback(env, cw):
    post(env, _miss("1760000010.1", call_queue="", call_ura=""))
    run(env)
    outcome = one(env, "select outcome from ops.calls")
    assert outcome == "missed"
    cb = q(env, "select reason, status, due_at > now() from ops.callback_tasks")
    assert cb == [("missed", "pending", True)]
    assert "call.missed" in stream_types(env) and "callback.created" in stream_types(env)
    cat = q(env, "select category, subcategory from ops.support_tickets")[0]
    assert cat == ("ligacao_perdida", "missed")
    assert one(env, "select first_response_at from ops.support_tickets") is None


def test_s10_fora_do_expediente(env):
    post(env, _miss("1760000010.2", call_queue="", call_date="2026-10-17 21:00:00"))   # sábado
    run(env)
    assert one(env, "select outcome from ops.calls") == "after_hours"
    due = one(env, "select due_at from ops.callback_tasks")
    from sd_ops.sla import BusinessHours
    assert BusinessHours().is_open(due - dt.timedelta(seconds=1))      # prazo do retorno cai em horário comercial


def test_s10_recusa_de_operador_nao_e_perdida(env):
    post(env, _miss("1760000010.3", call_status="rejected", call_transfer_id="1760000010.4"))
    post(env, rt("1760000010.4", branch_mask=5010))
    run(env)
    assert one(env, "select outcome from ops.calls where state='ended'") == "answered"
    assert one(env, "select count(*) from ops.callback_tasks") == 0


def test_s11_abandonadas(env):
    post(env, _miss("1760000011.1", call_queue="3855-FILA_SUPORTE_1", call_time_waiting=40))
    post(env, _miss("1760000011.2", call_queue="", call_ura="Opcao - 2", call_time_waiting=0, call_time=2,
                    call_number="999990011"))
    run(env)
    rows = dict(q(env, "select root_provider_call_id, outcome from ops.calls"))
    assert rows == {"1760000011.1": "abandoned_queue", "1760000011.2": "abandoned_ura"}
    # abandono curto na URA (2 s) não gera retorno; abandono na fila sim
    assert q(env, "select reason from ops.callback_tasks") == [("abandoned_queue",)]


# ---------------------------------------------------------------- 12. click-to-call
def test_s12_click_to_call_live(env, cw):
    env.s.dial_mode, env.s.dial_client_code, env.s.dial_api_key, env.s.dial_jwt = "live", "cc", "ak", "jwt"
    h = session(env)
    post(env, rt("1760000012.0"))
    run(env)
    tid = one(env, "select id from ops.support_tickets")
    conv = one(env, "select conversation_id from ops.calls")
    r = env.client.post(API + "/dial", json={"phone": "+5511999990001", "ticket_id": tid, "conversation_id": conv}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted" and r.json()["provider_call_id"] == "1760000000.999"
    req = env.dial_http[-1]
    assert req.headers["client_code"] == "cc" and req.headers["api_key"] == "ak"
    assert req.headers["authorization"] == "Bearer jwt"
    assert json.loads(req.content) == {"email": "ramal5005@pbx.test", "phone": "+5511999990001"}
    # a chamada chega depois pelo webhook e fica no mesmo ticket e conversa
    post(env, rt("1760000000.999", call_type="active"))
    run(env)
    rel = one(env, "select relation from ops.ticket_calls tc join ops.calls c on c.id=tc.call_id "
                   "where c.root_provider_call_id='1760000000.999'")
    assert rel == "dial"
    assert one(env, "select conversation_id from ops.calls where root_provider_call_id='1760000000.999'") == conv
    assert len(cw.convs) == 1
    assert "55pbx:1760000000.999:registro" in conv_msgs(cw, conv)


def test_s12_click_to_call_erros(env):
    h = session(env)
    env.s.dial_mode = "disabled"
    assert env.client.post(API + "/dial", json={"phone": "+5511999990001"}, headers=h).status_code == 503
    env.s.dial_mode = "mock"
    r = env.client.post(API + "/dial", json={"phone": "+5511999990001"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "mock" and r.json()["simulated"] is True
    assert env.client.post(API + "/dial", json={"phone": "123"}, headers=h).status_code == 422
    hb = session(env, "tok-bruno")
    assert env.client.post(API + "/dial", json={"phone": "+5511999990001"}, headers=hb).status_code == 403
    env.s.dial_mode, env.s.dial_client_code, env.s.dial_api_key, env.s.dial_jwt = "live", "cc", "ak", "jwt"
    env.dial_resp[:] = [httpx.Response(404, json={"status": "ERROR", "email": "E-mail inválido."})]
    r = env.client.post(API + "/dial", json={"phone": "+5511999990001"}, headers=h)
    assert r.status_code == 502 and r.json()["status"] == "rejected" and r.json()["message"] == "E-mail inválido."
    env.dial_resp[:] = [httpx.Response(500, json={"error": "Usuário com requisição pendente."})]
    r = env.client.post(API + "/dial", json={"phone": "+5511999990001"}, headers=h)
    assert r.status_code == 502 and r.json()["status"] == "error"
    # 15. 55PBX indisponível na discagem: erro real, nunca sucesso simulado
    env.dial_resp[:] = [httpx.ConnectError("sem rota")]
    r = env.client.post(API + "/dial", json={"phone": "+5511999990001"}, headers=h)
    assert r.status_code == 502 and "indisponível" in r.json()["message"]
    assert one(env, "select count(*) from ops.audit_events where action='dial.requested'") == 4


# ---------------------------------------------------------------- 13. falhas de autenticação
def test_s13_falhas_de_autenticacao(env, cw):
    assert post(env, rt("1760000013.1"), secret="x" * 40).status_code == 404
    # tenant "outro" exige o header token (manual: "Chave (token)" no header)
    assert post(env, rt("1760000013.1"), secret=SECRET_OUTRO).status_code == 401
    assert post(env, rt("1760000013.1"), secret=SECRET_OUTRO, headers={"token": "errado"}).status_code == 401
    assert post(env, rt("1760000013.1"), secret=SECRET_OUTRO, headers={"token": "tok-55pbx-outro"}).status_code == 202
    assert env.client.post(API + "/auth/session", json={"chatwoot_token": "nada", "account_id": 4}).status_code == 401
    assert env.client.post(API + "/auth/session", json={"chatwoot_token": "tok-outro", "account_id": 4}).status_code == 403
    assert env.client.get(API + "/tickets").status_code == 401
    assert env.client.get(API + "/tickets", headers={"Authorization": "Bearer sdsvc_errado"}).status_code == 401
    assert env.client.get(API + "/tickets", headers={"Authorization": "Bearer lixo"}).status_code == 401
    # cookie sem CSRF não muda estado
    r = env.client.post(API + "/auth/session", json={"chatwoot_token": "tok-ana", "account_id": 4})
    env.client.cookies.set("sdops_session", r.json()["session_token"], path="/sd-ops")
    assert env.client.get(API + "/auth/me").status_code == 200
    assert env.client.post(API + "/tickets", json={"subject": "x"}).status_code == 403
    assert env.client.post(API + "/tickets", json={"subject": "x"},
                           headers={"X-SD-CSRF": r.json()["csrf_token"]}).status_code == 201
    env.client.cookies.clear()
    assert env.client.get(API + "/ura/tickets/123", headers={"X-SD-URA-Token": "errado"}).status_code == 401
    assert one(env, "select count(*) from ops.audit_events where action='auth.failed'") >= 2


# ---------------------------------------------------------------- 14. Chatwoot indisponível
def test_s14_chatwoot_indisponivel(env, cw):
    cw.down = True
    assert post(env, rt("1760000014.1")).status_code == 202
    run(env)
    assert one(env, "select status from ops.webhook_inbox") == "done"
    assert one(env, "select count(*) from ops.support_tickets") == 1      # domínio não depende do Chatwoot
    pend = q(env, "select kind, status from ops.outbox where kind = 'chatwoot.sync_call' order by id")
    assert pend and all(s == "pending" for _, s in pend)
    assert one(env, "select count(*) from ops.integration_sync_logs where target='chatwoot' and status='retry'") >= 1
    cw.down = False
    due_now(env)
    run(env)
    assert len(cw.convs) == 1 and one(env, "select conversation_id from ops.calls") in cw.convs
    assert one(env, "select count(*) from ops.outbox where status<>'done'") == 0


def test_s14_dlq_e_reprocessamento(env, cw):
    cw.down = True
    post(env, rt("1760000014.2"))
    for _ in range(5):
        run(env)
        due_now(env)
    assert one(env, "select count(*) from ops.outbox where status='dead'") >= 1
    h = session(env, "tok-admin")
    dlq = env.client.get(API + "/admin/dlq", headers=h).json()
    assert dlq["outbox"]
    cw.down = False
    for it in dlq["outbox"]:
        assert env.client.post(API + "/admin/dlq/outbox/%d/retry" % it["id"], headers=h).json()["requeued"] == 1
    run(env)
    due_now(env)
    run(env)
    assert len(cw.convs) == 1


# ---------------------------------------------------------------- 15. 55PBX indisponível (Report02)
def test_s15_report02_indisponivel(env):
    def handler(req):
        raise httpx.ConnectError("timeout")
    env.s.bridge.pbx_api_key = "chave-ficticia"
    env.svc.worker.pbx = PbxApi("https://reportapi02.55pbx.com:50500/api/pbx/reports/metrics", "chave-ficticia",
                                client=httpx.Client(transport=httpx.MockTransport(handler)), retries=1, sleep=lambda s: None)
    res = env.svc.worker.poll_once()
    assert "error" in res
    assert one(env, "select status from ops.reconciliation_runs") == "error"
    assert env.client.get("/sd-ops/health").json()["last_poll_error"]


def test_s15_gravacao_rede_falha_e_retenta(env, cw):
    url = rt("1760000015.1")["call_url_audio"]
    env.dl.plan[url] = [AudioError("falha de rede ao baixar gravação: ConnectError"), wav(30)]
    post(env, rt("1760000015.1"))
    run(env)
    assert q(env, "select status, attempts from ops.call_recordings") == [("pending", 1)]
    due_now(env)
    run(env)
    assert one(env, "select status from ops.call_recordings") == "stored"


# ---------------------------------------------------------------- 16/17. áudio inexistente e atrasado
def test_s16_audio_inexistente(env, cw):
    rec = rt("1760000016.1")
    rec["call_url_audio"] = ""
    post(env, rec)
    run(env)
    assert one(env, "select count(*) from ops.call_recordings") == 0
    ended = [e for e in env.pub.events if e["type"] == "call.ended"][0]
    assert ended["payload"]["has_recording_url"] is False
    # URL que nunca fica disponível: esgota as tentativas e falha de vez (sem loop infinito)
    url = rt("1760000016.2")["call_url_audio"]
    env.dl.plan[url] = [AudioError("gravação não encontrada (HTTP 404)")]
    post(env, rt("1760000016.2", call_number="999990016"))
    for _ in range(6):
        run(env)
        due_now(env)
    assert one(env, "select status from ops.call_recordings") == "failed"
    assert "recording.failed" in stream_types(env)


def test_s17_audio_atrasado(env, cw):
    url = rt("1760000017.1")["call_url_audio"]
    env.dl.plan[url] = [AudioError("gravação não encontrada (HTTP 404)"), wav(30)]
    post(env, rt("1760000017.1"))
    run(env)
    assert one(env, "select status from ops.call_recordings") == "pending"
    conv = one(env, "select conversation_id from ops.calls")
    assert not any(mm["attachments"] for mm in cw.msgs[conv])
    due_now(env)
    run(env)
    assert one(env, "select status from ops.call_recordings") == "stored"
    assert "recording.stored" in stream_types(env)
    assert "55pbx:1760000017.1:gravacao" in conv_msgs(cw, conv)


def test_s17_audio_incompleto_espera_e_marca(env):
    url = rt("1760000017.2")["call_url_audio"]
    env.dl.plan[url] = [wav(5)]          # 5 s de áudio para 30 s falados
    post(env, rt("1760000017.2"))
    for _ in range(4):
        run(env)
        due_now(env)
    st, integ = q(env, "select status, integrity from ops.call_recordings")[0]
    assert (st, integ) == ("stored", "short")


# ---------------------------------------------------------------- 21. reprocessamento sem duplicação
def test_s21_reprocessamento_sem_duplicacao(env, cw):
    post(env, rt("1760000021.1", "start"))
    post(env, rt("1760000021.1"))
    run(env)
    snap = (one(env, "select count(*) from ops.calls"), one(env, "select count(*) from ops.support_tickets"),
            len(cw.convs), sum(len(v) for v in cw.msgs.values()), one(env, "select count(*) from ops.call_recordings"))
    ids = {e["id"] for e in env.pub.events}
    with env.engine.begin() as conn:          # reprocessa TUDO (inbox e outbox)
        conn.execute(sa.text("update ops.webhook_inbox set status='pending', attempts=0"))
        conn.execute(sa.text("update ops.outbox set status='pending', attempts=0"))
    run(env)
    from sd_ops.worker import accept
    with env.engine.begin() as conn:          # o mesmo dado vindo do Report02
        accept(conn, "dev55", "report02", json.dumps(rt("1760000021.1")).encode(), "application/json")
    run(env)
    snap2 = (one(env, "select count(*) from ops.calls"), one(env, "select count(*) from ops.support_tickets"),
             len(cw.convs), sum(len(v) for v in cw.msgs.values()), one(env, "select count(*) from ops.call_recordings"))
    assert snap == snap2
    assert {e["id"] for e in env.pub.events} == ids        # reentregas usam o mesmo id (consumidor deduplica)


# ---------------------------------------------------------------- 22/23. status e reabertura
def test_s22_mudanca_de_status_e_sla(env, cw):
    post(env, rt("1760000022.1"))
    run(env)
    h = session(env)
    tid = one(env, "select id from ops.support_tickets")
    conv = one(env, "select conversation_id from ops.calls")

    def go(to, hh=h, reason=""):
        return env.client.post(API + "/tickets/%s/transitions" % tid, json={"to": to, "reason": reason}, headers=hh)
    assert go("em_atendimento").status_code == 200
    assert go("aguardando_cliente").status_code == 200
    run(env)
    assert cw.convs[conv]["status"] == "waiting_on_customer" and cw.convs[conv]["custom_attributes"]["zd_status"] == "Pendente"
    assert one(env, "select status from ops.sla_instances where metric='resolution'") == "paused"
    assert go("em_atendimento").status_code == 200
    assert one(env, "select status from ops.sla_instances where metric='resolution'") == "running"
    assert go("novo").status_code == 409                                     # transição inexistente
    assert go("cancelado").status_code == 403                                # agente não cancela
    assert go("cancelado", session(env, "tok-bruno")).status_code == 422     # supervisor, mas sem motivo
    assert go("resolvido").status_code == 200
    run(env)
    assert cw.convs[conv]["status"] == "resolved"
    assert go("encerrado").status_code == 403                                # agente não encerra
    assert go("encerrado", session(env, "tok-bruno")).status_code == 200     # supervisor encerra
    ev = [e["kind"] for e in env.client.get(API + "/tickets/%s/events" % tid, headers=h).json()["events"]]
    assert ev.count("status_changed") == 5
    # eco do Chatwoot (status que nós mesmos aplicamos) é ignorado
    env.svc.sync.handle_event("dev55", {"event": "conversation_status_changed", "id": conv, "status": "resolved"})
    assert one(env, "select status from ops.support_tickets") == "encerrado"


def test_s23_reabertura(env, cw):
    post(env, rt("1760000023.1"))
    run(env)
    h = session(env)
    hs = session(env, "tok-bruno")
    tid = one(env, "select id from ops.support_tickets")
    conv = one(env, "select conversation_id from ops.calls")
    env.client.post(API + "/tickets/%s/transitions" % tid, json={"to": "resolvido"}, headers=h)
    run(env)
    # agente reabre pelo Chatwoot (conversa resolvida -> aberta)
    env.svc.sync.handle_event("dev55", {"event": "conversation_status_changed", "id": conv, "status": "open"})
    st, n = q(env, "select status, reopen_count from ops.support_tickets")[0]
    assert (st, n) == ("em_atendimento", 1)
    assert one(env, "select status from ops.sla_instances where metric='resolution'") == "running"
    env.client.post(API + "/tickets/%s/transitions" % tid, json={"to": "resolvido"}, headers=h)
    env.client.post(API + "/tickets/%s/transitions" % tid, json={"to": "encerrado"}, headers=hs)
    r = env.client.post(API + "/tickets/%s/reopen" % tid, json={"to": "x", "reason": "cliente voltou"}, headers=h).json()
    assert r["followup_created"] is True and r["parent_ticket_id"] == tid and r["status"] == "em_atendimento"
    assert conv in r["conversations"]
    run(env)
    assert "ticket.reopened" in stream_types(env)


# ---------------------------------------------------------------- 25. acesso cruzado entre tenants
def test_s25_acesso_cruzado(env, cw):
    post(env, rt("1760000025.1"))
    run(env)
    tid = one(env, "select id from ops.support_tickets")
    call_id = one(env, "select id from ops.calls")
    rec_id = one(env, "select id from ops.call_recordings")
    proto = one(env, "select protocol_numeric from ops.support_tickets")
    ho = session(env, "tok-outro", 99)
    assert env.client.get(API + "/tickets/" + tid, headers=ho).status_code == 404
    assert env.client.get(API + "/calls/" + call_id, headers=ho).status_code == 404
    assert env.client.get(API + "/recordings/%s/url" % rec_id, headers=ho).status_code == 404
    assert env.client.post(API + "/tickets/%s/transitions" % tid, json={"to": "triagem"}, headers=ho).status_code == 404
    assert env.client.get(API + "/tickets", headers=ho).json()["items"] == []
    # token de serviço restrito ao tenant dev55
    assert env.client.get(API + "/tickets", headers={"Authorization": "Bearer sdsvc_qa", "X-SD-Tenant": "outro"}).status_code == 403
    # URA do outro tenant não enxerga o protocolo
    r = env.client.get(API + "/ura/tickets/" + proto, params={"ani": "11999990001"}, headers={"X-SD-URA-Token": "x" * 32})
    assert r.json() == {"encontrado": "nao", "proxima_acao": "repetir"}


# ---------------------------------------------------------------- 28. reconciliação histórica
def test_s28_reconciliacao_historica(env):
    seen = []

    def handler(req):
        seen.append(req.url.path)
        assert req.headers["key"] == "chave-ficticia"
        rows = []
        if len(seen) == 1:
            rows = [{"call_id": "1760000028.%d" % i, "name": "Ana Teste", "call_time_total_duration": "00:01:00",
                     "call_time_waiting": "00:00:05", "call_time_spoken": "00:00:50" if i % 2 else "00:00:00",
                     "branch_number_agent": "5005", "call_number": "99999%04d" % i, "call_area_code": "11",
                     "wg_country_code": "55", "call_date": "12/10/2026", "wb_call_hour": "10:%02d:00" % i,
                     "queue_name": "3855-FILA_SUPORTE_1", "type_call": "receptivo"} for i in range(1, 7)]
        return httpx.Response(200, json={"data_report02": rows})
    env.s.bridge.pbx_api_key = "chave-ficticia"
    env.svc.worker.pbx = PbxApi("https://reportapi02.55pbx.com:50500/api/pbx/reports/metrics", "chave-ficticia",
                                client=httpx.Client(transport=httpx.MockTransport(handler)), sleep=lambda s: None)
    h = session(env, "tok-admin")
    r = env.client.post(API + "/reconciliations", json={"from": "2026-10-12T00:00:00Z", "to": "2026-10-13T00:00:00Z"},
                        headers=h)
    assert r.status_code == 202 and r.json() == {"rows": 6, "new": 6}
    assert len(seen) == 4 and "report_02" in seen[0]                      # blocos de 6 h
    run(env)
    assert one(env, "select count(*) from ops.calls") == 6
    assert dict(q(env, "select outcome, count(*) from ops.calls group by 1")) == {"answered": 3, "abandoned_queue": 3}
    # o webhook atrasado da mesma ligação não cria outra
    post(env, rt("1760000028.1", call_number="999990001"))
    run(env)
    assert one(env, "select count(*) from ops.calls") == 6
    assert one(env, "select count(*) from ops.reconciliation_runs where status='ok'") == 4


# ---------------------------------------------------------------- 29. carga concorrente
def test_s29_carga_concorrente(env, cw):
    recs = []
    for i in range(20):
        cid = "1760000029.%d" % i
        num = "99998%04d" % i
        recs += [rt(cid, "start", call_number=num), rt(cid, call_number=num), rt(cid, call_number=num)]
    with cf.ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda r: post(env, r).status_code, recs))
    assert codes.count(202) == 40 and codes.count(200) == 20
    with cf.ThreadPoolExecutor(4) as ex:      # 4 workers em paralelo
        for _ in range(6):
            list(ex.map(lambda _: env.svc.worker.run_until_idle(20), range(4)))
    assert one(env, "select count(*) from ops.calls") == 20
    assert one(env, "select count(*) from ops.call_legs") == 20
    assert one(env, "select count(*) from ops.call_events") == 40
    assert one(env, "select count(*) from ops.support_tickets") == 20
    assert one(env, "select count(*) from ops.call_recordings where status='stored'") == 20
    assert len(cw.convs) == 20 and len(cw.contacts) == 20
    for conv, msgs in cw.msgs.items():
        srcs = [mm["source_id"] for mm in msgs]
        assert len(srcs) == len(set(srcs))
    assert len({e["id"] for e in env.pub.events}) == len(env.pub.events)
    nums = q(env, "select protocol_numeric from ops.support_tickets")
    assert len({n[0] for n in nums}) == 20


# ---------------------------------------------------------------- 30. recuperação após reinício
def test_s30_recuperacao_apos_reinicio(env, cw):
    post(env, rt("1760000030.1"))
    claimed = env.svc.worker._claim(m.webhook_inbox, limit=10)      # o processo "morre" com o item reservado
    assert len(claimed) == 1
    assert env.svc.worker.inbox_once() == 0                          # lease ainda vale: ninguém pega
    with env.engine.begin() as conn:
        conn.execute(sa.text("update ops.webhook_inbox set locked_until = now() - interval '1 second'"))
    from sd_ops.worker import Worker
    w2 = Worker(env.s, env.engine, env.svc.calls, env.svc.sync, env.svc.recordings, env.pub)   # "novo processo"
    w2.run_until_idle()
    assert one(env, "select status from ops.webhook_inbox") == "done"
    assert one(env, "select count(*) from ops.calls") == 1 and len(cw.convs) == 1
    # outbox presa em "processing" também volta
    with env.engine.begin() as conn:
        conn.execute(sa.text("update ops.outbox set status='processing', locked_until = now() - interval '1 second' "
                             "where kind='chatwoot.sync_ticket'"))
    w2.run_until_idle()
    assert one(env, "select count(*) from ops.outbox where status <> 'done'") == 0
