import hashlib
import hmac
import json
import time

from fastapi.testclient import TestClient

from pbx_bridge.app import Bridge, create_app, verify_chatwoot_signature
from pbx_bridge.store import Store
from tests.conftest import SECRET, report02_row

URL = "/integracoes/55pbx/webhook/" + SECRET


class FakePbx:
    def __init__(self, rows=None, error=None):
        self.rows = rows or []
        self.error = error
        self.calls = 0

    def report02(self, start, end):
        self.calls += 1
        if self.error:
            raise self.error
        return self.rows


def make(env, **kw):
    s, store, cw, proc, audio = env
    s.pbx_api_key = "chave-ficticia"
    for k, v in kw.items():
        setattr(s, k, v)
    br = Bridge(s, store=store, cw=cw, pbx=FakePbx(), processor=proc)
    return TestClient(create_app(s, bridge=br, start_threads=False)), br


def test_health(env):
    c, br = make(env)
    r = c.get("/integracoes/55pbx/health")
    assert r.status_code == 200 and r.json()["enabled"] is True and r.json()["calls"] == 0


def test_desativado(settings):
    settings.enabled = False
    c = TestClient(create_app(settings, start_threads=False))
    assert c.get("/integracoes/55pbx/health").json()["enabled"] is False
    assert c.post(URL, json=report02_row()).status_code == 503


def test_segredo_errado(env):
    c, br = make(env)
    assert c.post("/integracoes/55pbx/webhook/errado", json=report02_row()).status_code == 404
    assert c.post(URL[:-1] + "x", json=report02_row()).status_code == 404
    assert br.store.counts().get("events_pending") is None


def test_webhook_json_put_e_processamento(env):
    c, br = make(env)
    r = c.put(URL, json=report02_row())
    assert r.status_code == 200 and r.json() == {"ok": True, "queued": 1, "unparsed": 0}
    assert br.work_once() == 1
    assert br.store.counts()["events_done"] == 1 and br.store.counts()["calls"] == 1
    # payload bruto guardado, mas só no SQLite
    raw = br.store.db.execute("select raw from events").fetchone()[0]
    assert "999990001" in raw


def test_webhook_form(env):
    c, br = make(env)
    r = c.post(URL, content=b"call_id=7.7&type_call=receptivo&call_number=11999990003",
               headers={"content-type": "application/x-www-form-urlencoded"})
    assert r.json()["queued"] == 1


def test_webhook_nao_reconhecido_nao_vaza_em_log(env, caplog):
    c, br = make(env)
    r = c.post(URL, content=b'{"telefone": "11999990004", "cpf": "12345678900"}',
               headers={"content-type": "application/json"})
    assert r.json() == {"ok": True, "queued": 0, "unparsed": 1}
    assert "11999990004" not in caplog.text and "12345678900" not in caplog.text
    assert br.store.counts()["events_unparsed"] == 1


def test_limite_de_tamanho(env):
    c, br = make(env, max_body_bytes=100)
    assert c.post(URL, content=b"x" * 101).status_code == 413


def test_allowlist_ip(env):
    c, br = make(env, allowed_ips=["200.1.2.0/24"])
    assert c.post(URL, json=report02_row(), headers={"x-forwarded-for": "9.9.9.9"}).status_code == 403
    # cliente forjando XFF: vale o último salto (adicionado pelo proxy)
    assert c.post(URL, json=report02_row(), headers={"x-forwarded-for": "200.1.2.3, 9.9.9.9"}).status_code == 403
    assert c.post(URL, json=report02_row(), headers={"x-forwarded-for": "9.9.9.9, 200.1.2.3"}).status_code == 200


def test_poller(env):
    c, br = make(env)
    br.pbx.rows = [report02_row(), report02_row(call_id="8.8", type_call="ativo")]
    assert br.poll_once() == {"rows": 2, "queued": 2}
    br.work_once()
    assert br.store.counts()["calls"] == 2
    assert br.poll_once() == {"rows": 2, "queued": 0}  # já completas
    assert br.store.kv_get("last_poll_ok_at")


def test_poller_falha_55pbx(env):
    from pbx_bridge.pbx_api import PbxError
    c, br = make(env)
    br.pbx.error = PbxError("55PBX HTTP 502")
    assert br.poll_once() == {"error": 1}
    assert "502" in br.store.kv_get("last_poll_error")


def test_falha_do_servicedesk_volta_para_fila(env):
    c, br = make(env)
    s, store, cw, proc, audio = env

    def boom(*a, **k):
        raise RuntimeError("chatwoot fora do ar")
    orig = cw.create_conversation
    cw.create_conversation = boom
    c.post(URL, json=report02_row())
    br.work_once()
    row = store.db.execute("select status, attempts, next_attempt_at from events").fetchone()
    assert row["status"] == "pending" and row["attempts"] == 1 and row["next_attempt_at"] > time.time()
    cw.create_conversation = orig
    store.db.execute("update events set next_attempt_at=0")
    br.work_once()
    assert store.counts()["events_done"] == 1 and len(cw.convs) == 1


def test_eventos_servicedesk_assinatura(env):
    c, br = make(env, chatwoot_webhook_hmac_secret="segredo-da-inbox")
    body = json.dumps({"event": "message_created"}).encode()
    url = "/integracoes/55pbx/servicedesk-events/" + SECRET
    assert c.post(url, content=body).status_code == 401
    ts = str(int(time.time()))
    sig = "sha256=" + hmac.new(b"segredo-da-inbox", ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    r = c.post(url, content=body, headers={"x-chatwoot-timestamp": ts, "x-chatwoot-signature": sig})
    assert r.status_code == 200
    assert not verify_chatwoot_signature("segredo-da-inbox", body, str(int(time.time()) - 900), sig)


def test_retencao_apaga_payload_antigo(env):
    c, br = make(env)
    c.post(URL, json=report02_row())
    br.work_once()
    assert br.store.purge(30) == 0
    br.store.db.execute("update events set received_at = received_at - 31*86400")
    assert br.store.purge(30) == 1 and br.store.counts().get("events_done") is None
