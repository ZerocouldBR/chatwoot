"""Configuração pelo painel (Configurações > Telefonia 55PBX): cofre, máscara, precedência tela > ambiente,
permissão (administrator da conta), recarga sem reiniciar, teste de conexão contra uma 55PBX falsa e auditoria.
Dados FICTÍCIOS."""
from __future__ import annotations

import hashlib
import hmac
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
import sqlalchemy as sa

from sd_ops import db
from sd_ops.settings_check import DIAL_PROBE_EMAIL
from sd_ops.settings_store import SettingsProvider, Vault, apply, new_key
from tests.sdops.conftest import SECRET, SECRET_OUTRO, URL, one, post, q, rt, run, session

pytestmark = pytest.mark.skipif(not URL, reason="SDOPS_TEST_DATABASE_URL não definido")
API = "/sd-ops/api/v1"
ST = API + "/admin/settings"
OUTRO = {"token": "tok-55pbx-outro"}           # o tenant "outro" exige o header token (conftest)


def _key(env):
    """Liga o cofre (equivale a SDOPS_SETTINGS_KEY no ambiente)."""
    env.svc.settings.vault = Vault(new_key())


def _put(env, h, **body):
    return env.client.put(ST, json=body, headers=h)


# ------------------------------------------------------------------ cofre e máscara
def test_vault_cifra_e_rotacao_de_chave():
    k1, k2 = new_key(), new_key()
    v1 = Vault(k1)
    tok = v1.encrypt("chave-secreta-1234")
    assert "chave-secreta" not in tok and v1.decrypt(tok) == "chave-secreta-1234"
    # rotação: nova chave na frente, antiga ainda decifra
    v2 = Vault("%s,%s" % (k2, k1))
    assert v2.decrypt(tok) == "chave-secreta-1234"
    assert Vault(k2).enabled and not Vault("").enabled
    bad = Vault("nao-e-chave-fernet")
    assert not bad.enabled and "SDOPS_SETTINGS_KEY inválida" in bad.error


def test_segredo_sem_chave_da_erro_claro_e_nao_secreto_salva(env):
    h = session(env, "tok-admin")
    r = _put(env, h, secrets={"pbx_api_key": "chave-webservice-ficticia-0001"})
    assert r.status_code == 422 and r.json()["error"] == "settings_key_missing"
    assert "SDOPS_SETTINGS_KEY" in r.json()["message"]
    assert one(env, "select count(*) from ops.tenant_settings") == 0
    r = _put(env, h, values={"pbx_api_key_header": "token", "poll_interval_min": 5})
    assert r.status_code == 200, r.text
    f = r.json()["fields"]
    assert f["pbx_api_key_header"] == {**f["pbx_api_key_header"], "value": "token", "source": "panel"}
    assert r.json()["vault"]["enabled"] is False


def test_get_mascara_segredos_e_put_vazio_mantem(env):
    _key(env)
    h = session(env, "tok-admin")
    plain = "chave-webservice-ficticia-ABCD"
    r = _put(env, h, secrets={"pbx_api_key": plain, "dial_jwt": "jwt.ficticio.WXYZ1234"})
    assert r.status_code == 200, r.text
    raw = one(env, "select secrets::text from ops.tenant_settings where tenant_id='dev55'")
    assert plain not in raw and "jwt.ficticio" not in raw                      # só cifrado no banco
    g = env.client.get(ST, headers=h)
    assert g.status_code == 200 and plain not in g.text and "jwt.ficticio" not in g.text
    k = g.json()["fields"]["pbx_api_key"]
    assert k["defined"] is True and k["last4"] == "ABCD" and k["source"] == "panel" and "value" not in k
    # segredo vazio = manter; null = apagar (volta ao ambiente, que aqui não tem)
    r = _put(env, h, version=g.json()["version"], secrets={"pbx_api_key": "", "dial_jwt": None})
    f = r.json()["fields"]
    assert f["pbx_api_key"]["last4"] == "ABCD" and f["dial_jwt"] == {**f["dial_jwt"], "defined": False, "source": "none"}
    assert env.svc.settings.effective("dev55").bridge.pbx_api_key == plain


# ------------------------------------------------------------------ permissão
def test_permissao_so_administrador_da_conta(env):
    assert env.client.get(ST).status_code == 401                                 # sem sessão
    assert env.client.get(ST, headers=session(env, "tok-ana")).status_code == 403      # agente
    assert env.client.get(ST, headers=session(env, "tok-bruno")).status_code == 403    # supervisor (ops.user_roles)
    with env.engine.begin() as conn:                                              # "admin" só do ops.user_roles
        conn.execute(sa.text("insert into ops.user_roles (tenant_id, chatwoot_user_id, role) values ('dev55', 11, 'admin')"))
    ha = session(env, "tok-ana")
    assert env.client.get(API + "/admin/dlq", headers=ha).status_code == 200      # admin do sd-ops: sim
    assert env.client.get(ST, headers=ha).status_code == 403                      # configuração: não
    assert env.client.put(ST, json={"values": {"enabled": False}}, headers=ha).status_code == 403
    assert env.client.post(ST + "/test", headers=ha).status_code == 403
    assert env.client.post(ST + "/webhook-secret", headers=ha).status_code == 403
    assert env.client.get(ST, headers={"Authorization": "Bearer sdsvc_n8n", "X-SD-Tenant": "dev55"}).status_code == 403
    g = env.client.get(ST, headers=session(env, "tok-admin"))
    assert g.status_code == 200 and g.json()["tenant"]["id"] == "dev55"
    # o admin de OUTRA conta só vê o tenant dele
    assert env.client.get(ST, headers=session(env, "tok-outro", 99)).json()["tenant"]["id"] == "outro"


# ------------------------------------------------------------------ precedência e recarga
def test_precedencia_tela_vence_ambiente_e_null_volta(env):
    h = session(env, "tok-admin")
    ha = session(env)
    cap = lambda: env.client.get(API + "/capabilities", headers=ha).json()["capabilities"]  # noqa: E731
    assert cap()["dial"]["mode"] == "mock"                                       # ambiente (conftest)
    r = _put(env, h, values={"dial_mode": "disabled", "webphone_url": "https://fone.55pbx.test"})
    assert r.status_code == 200
    assert r.json()["fields"]["dial_mode"]["source"] == "panel"
    c = cap()
    assert c["dial"]["enabled"] is False and c["dial"]["mode"] == "disabled"
    assert c["webphone"]["url"] == "https://fone.55pbx.test"
    # null = remove da tela e volta ao valor do ambiente
    _put(env, h, values={"dial_mode": None, "webphone_url": None})
    assert cap()["dial"]["mode"] == "mock" and cap()["webphone"]["enabled"] is False
    # mock só no DEV
    env.s.env = "prod"
    r = _put(env, h, values={"dial_mode": "mock"})
    assert r.status_code == 422 and "mock" in r.json()["fields"]["dial_mode"]


def test_validacao_e_concorrencia(env):
    h = session(env, "tok-admin")
    r = _put(env, h, values={"allowed_ips": ["10.0.0.0/8", "nao-e-ip"], "pbx_api_url": "ftp://x", "nada": 1,
                             "poll_interval_min": 0})
    assert r.status_code == 422
    assert set(r.json()["fields"]) == {"allowed_ips", "pbx_api_url", "nada", "poll_interval_min"}
    v = _put(env, h, values={"default_team": "Suporte"}).json()["version"]
    assert _put(env, h, version=v, values={"default_team": "Financeiro"}).status_code == 200
    r = _put(env, h, version=v, values={"default_team": "Treinamento"})          # versão velha
    assert r.status_code == 409 and r.json()["error"] == "conflict"


def test_recarga_sem_reiniciar_ttl_e_invalidacao(env):
    prov = env.svc.settings
    assert prov.effective("dev55").bridge.pbx_api_key_header == "key"
    h = session(env, "tok-admin")
    _put(env, h, values={"pbx_api_key_header": "token"})
    assert prov.effective("dev55").bridge.pbx_api_key_header == "token"         # invalidação na gravação
    # outra réplica (outro provider) com TTL: vê a mudança feita direto no banco depois do TTL
    other = SettingsProvider(env.s, env.engine)
    assert other.effective("dev55").bridge.pbx_api_key_header == "token"
    with env.engine.begin() as conn:
        conn.execute(sa.text("""update ops.tenant_settings set values = jsonb_set(values, '{pbx_api_key_header}', '"x-key"'),
                                version = version + 1 where tenant_id = 'dev55'"""))
    assert other.effective("dev55").bridge.pbx_api_key_header == "token"        # ainda no cache
    env.s.settings_ttl_s = 0
    assert other.effective("dev55").bridge.pbx_api_key_header == "x-key"        # TTL vencido: recarregou


def test_ativacao_por_tenant_e_teto_global(env):
    h = session(env, "tok-admin")
    assert post(env, rt("1760000900.1")).status_code == 202
    r = _put(env, h, values={"enabled": False})
    assert r.status_code == 200 and r.json()["fields"]["enabled"]["value"] is False
    assert post(env, rt("1760000900.2")).status_code == 503                      # dev55 desligado pela tela
    assert post(env, rt("1760000900.3"), secret=SECRET_OUTRO, headers=OUTRO).status_code == 202  # outro tenant segue ativo
    # ambiente dormente (ENABLED=false): a tela liga o tenant sem reiniciar
    env.s.bridge.enabled = False
    assert post(env, rt("1760000900.4"), secret=SECRET_OUTRO, headers=OUTRO).status_code == 503
    _put(env, h, values={"enabled": True})
    assert post(env, rt("1760000900.5")).status_code == 202
    assert env.svc.worker.active() is True and env.client.get("/sd-ops/health").json()["enabled"] is True
    # teto global do operador: SDOPS_FORCE_DISABLED desliga tudo, vença o que vencer
    env.s.force_disabled = True
    assert post(env, rt("1760000900.6")).status_code == 503 and env.svc.worker.active() is False


def test_ativar_exige_token_e_segredo(env):
    env.s.bridge.chatwoot_api_token = ""
    env.s.bridge.enabled = False
    with env.engine.begin() as conn:
        conn.execute(sa.text("delete from ops.integration_credentials_refs"))
    h = session(env, "tok-admin")
    r = _put(env, h, values={"enabled": True})
    assert r.status_code == 422 and r.json()["error"] == "enable_blocked"
    assert any("token" in x for x in r.json()["missing"])


# ------------------------------------------------------------------ webhook: segredo novo aceito, antigo recusado
def test_webhook_segredo_novo_aceito_antigo_recusado(env):
    h = session(env, "tok-admin")
    assert post(env, rt("1760000901.1")).status_code == 202                      # segredo do seed (hash)
    r = env.client.post(ST + "/webhook-secret", headers=h)
    assert r.status_code == 200 and r.json()["shown_once"] is True and r.headers["cache-control"] == "no-store"
    url = r.json()["url"]
    new = url.rsplit("/", 1)[1]
    assert url.startswith("http://testserver/integracoes/55pbx/webhook/") and len(new) == 64
    assert post(env, rt("1760000901.2"), secret=new).status_code == 202
    assert post(env, rt("1760000901.3")).status_code == 404                      # o antigo deixou de valer
    assert post(env, rt("1760000901.4"), secret=SECRET_OUTRO, headers=OUTRO).status_code == 202  # outro tenant intacto
    g = env.client.get(ST, headers=h).json()["webhook"]
    assert g["defined"] and g["last4"] == new[-4:] and g["source"] == "panel" and new not in json.dumps(g)
    assert new not in env.client.get(ST, headers=h).text
    # só o hash fica no banco (compatível com o seed-tenant)
    assert one(env, "select webhook_secret_sha256 from ops.integration_accounts where tenant_id='dev55'") == db.sha256(new)
    assert new not in one(env, "select values::text from ops.tenant_settings")
    # apagar (null) volta ao segredo anterior (rollback)
    _put(env, h, secrets={"webhook_secret": None})
    assert post(env, rt("1760000901.5")).status_code == 202
    assert post(env, rt("1760000901.6"), secret=new).status_code == 404


def test_webhook_token_header_e_ips_da_tela(env):
    _key(env)
    h = session(env, "tok-admin")
    _put(env, h, values={"allowed_ips": ["10.9.9.0/24"]}, secrets={"webhook_token": "token-55pbx-ficticio"})
    assert post(env, rt("1760000902.1")).status_code == 403                      # IP do TestClient fora da lista
    _put(env, h, values={"allowed_ips": None})
    assert post(env, rt("1760000902.2")).status_code == 401                      # header token ausente
    assert post(env, rt("1760000902.3"), headers={"token": "token-55pbx-ficticio"}).status_code == 202


# ------------------------------------------------------------------ mapas, política, horário/SLA
def test_mapas_politica_horario_e_sla(env):
    h = session(env, "tok-admin")
    g = env.client.get(ST, headers=h).json()
    rules, pols = g["ticket_open_rules"], g["sla_policies"]
    assert len(rules) == 3 and len(pols) == 4 and g["business_hours"]["timezone"] == "America/Sao_Paulo"
    rules[1]["reuse"] = "new"
    pols[0]["first_response_min"] = 15
    r = _put(env, h, version=g["version"],
             values={"queue_team_map": {"fila_suporte_1": "Financeiro"}, "team_area_map": {"financeiro": "Financeiro"}},
             agent_mappings=[{"branch": "5010", "agent_email": "Bruno.Ficticio@exemplo.test", "chatwoot_user_id": 12}],
             ticket_open_rules=rules, sla_policies=pols,
             business_hours={"timezone": "America/Sao_Paulo", "schedule": {"0": [["08:00", "17:00"]]},
                             "holidays": ["2026-11-02"]})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["agent_mappings"] == [{"branch": "5010", "agent_email": "bruno.ficticio@exemplo.test",
                                    "chatwoot_user_id": 12, "pbx_email": None}]
    assert d["business_hours"]["schedule"] == {"0": [["08:00", "17:00"]]} and d["business_hours"]["holidays"] == ["2026-11-02"]
    assert one(env, "select b.name from ops.business_hours b join ops.tenants t on t.business_hours_id=b.id where t.id='dev55'") \
        == "tenant:dev55"
    assert one(env, "select count(*) from ops.tenants t join ops.business_hours b on b.id=t.business_hours_id "
                    "where t.id='outro' and b.name='Padrão B2B'") == 1                # o outro tenant não mudou
    assert one(env, "select first_response_min from ops.sla_policies where id=%d" % pols[0]["id"]) == 15
    # a fila da tela decide o time do ticket da chamada receptiva
    post(env, rt("1760000903.1"))
    run(env)
    assert one(env, "select team_name from ops.support_tickets") == "Financeiro"
    # ramal 5005 saiu do mapa: a chamada dele não tem responsável pelo mapa; 5010 tem
    with env.engine.begin() as conn:
        assert env.svc.calls._agent_email(conn, "dev55", "5005", {}) == "ana.teste@exemplo.test"   # BRANCH_AGENT_MAP do env
        assert env.svc.calls._agent_email(conn, "dev55", "5010", {}) == "bruno.ficticio@exemplo.test"
    bad = _put(env, h, agent_mappings=[{"branch": "1", "agent_email": "a@x.test"}, {"branch": "1", "agent_email": "b@x.test"}])
    assert bad.status_code == 422 and "repetido" in bad.json()["message"]
    bad = _put(env, h, business_hours={"timezone": "America/Sao_Paulo", "schedule": {"0": [["18:00", "09:00"]]}})
    assert bad.status_code == 422


# ------------------------------------------------------------------ auditoria
def test_auditoria_sem_valores_secretos(env):
    _key(env)
    h = session(env, "tok-admin")
    _put(env, h, values={"poll_interval_min": 7}, secrets={"pbx_api_key": "chave-auditoria-ficticia-9999"})
    env.client.post(ST + "/webhook-secret", headers=h)
    env.client.post(ST + "/test", headers=h)
    rows = q(env, "select action, actor_id, data::text from ops.audit_events where action like 'admin.settings%' order by id")
    assert [x[0] for x in rows] == ["admin.settings_updated", "admin.settings_webhook_rotated", "admin.settings_tested"]
    assert all(x[1] == "1" for x in rows)                                         # quem: o admin (id 1)
    upd = json.loads(rows[0][2])
    assert upd["changed"] == ["poll_interval_min"] and upd["secrets_set"] == ["pbx_api_key"]
    assert "chave-auditoria" not in json.dumps(rows)
    assert one(env, "select updated_by_email from ops.tenant_settings") == "admin@exemplo.test"


# ------------------------------------------------------------------ n8n pela tela
def test_n8n_url_base_e_hmac_da_tela(env, monkeypatch):
    _key(env)
    monkeypatch.setenv("N8N_SECRET", "segredo-do-ambiente")
    got = []

    def handler(req):
        got.append(req)
        return httpx.Response(200)
    env.svc.worker.http = httpx.Client(transport=httpx.MockTransport(handler))
    h = session(env, "tok-admin")
    assert env.client.post(API + "/admin/automation-routes", headers=h, json={
        "name": "WF06", "event_types": ["ticket.created"], "url": "/webhook/sd/wf06", "secret_ref": "N8N_SECRET"}
    ).status_code == 201
    _put(env, h, values={"n8n_base_url": "https://n8n.exemplo.test"},
         secrets={"n8n_hmac_secret": "segredo-da-tela", "n8n_webhook_token": "token-da-tela"})
    post(env, rt("1760000904.1"))
    run(env)
    assert [str(g.url) for g in got] == ["https://n8n.exemplo.test/webhook/sd/wf06"]
    req = got[0]
    exp = "sha256=" + hmac.new(b"segredo-da-tela", req.headers["x-sd-timestamp"].encode() + b"." + req.content,
                               hashlib.sha256).hexdigest()
    assert req.headers["x-sd-signature"] == exp and req.headers["x-sd-webhook-token"] == "token-da-tela"


# ------------------------------------------------------------------ URA pela tela
def test_ura_token_da_tela(env, monkeypatch):
    _key(env)
    monkeypatch.delenv("URA_TOKEN_DEV55")
    h = session(env, "tok-admin")
    assert env.client.get(API + "/ura/tickets/123", headers={"X-SD-URA-Token": "u" * 32}).status_code == 401
    _put(env, h, values={"ura_auth_type": "token", "ura_header": "X-URA"}, secrets={"ura_token": "t" * 20})
    assert env.client.get(API + "/ura/tickets/123", headers={"X-URA": "t" * 20}).status_code == 200
    g = env.client.get(ST, headers=h).json()
    assert g["ura_ready"] is True and g["fields"]["ura_token"]["source"] == "panel"


# ------------------------------------------------------------------ teste de conexão contra 55PBX falsa
class _Fake(BaseHTTPRequestHandler):
    good_key = "chave-boa-ficticia"

    def log_message(self, *a):
        pass

    def _send(self, code, body=None):
        data = json.dumps(body).encode() if body is not None else b""
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_GET(self):
        orig = self.headers.get("X-Orig-Host", "")
        if self.path.startswith("/api/pbx/reports/metrics/"):
            assert "report_02" in self.path
            if self.headers.get("key") == self.good_key:
                return self._send(200, {"data_report02": [{"call_id": "1.1"}], "reportCount": 1})
            return self._send(401, {"error": "unauthorized"})
        if self.path == "/api/v1/profile":
            if self.headers.get("api_access_token") == "token-integracao-ficticio":
                return self._send(200, {"id": 99, "accounts": [{"id": 4, "role": "agent"}]})
            return self._send(401, {})
        if orig.endswith("55pbx.com") and self.path == "/":
            return self._send(404, {})                       # host de gravações vivo (404 na raiz)
        if self.path == "/n8n":
            return self._send(200, {})
        return self._send(404, {})

    def do_HEAD(self):
        return self._send(200 if self.headers.get("key") == self.good_key else 403)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if self.path == "/api/webphone/dial":
            ok = (self.headers.get("client_code") == "cc-ficticio" and self.headers.get("api_key") == "ak-ficticio"
                  and self.headers.get("Authorization") == "Bearer jwt-ficticio")
            if not ok:
                return self._send(401, {"error": "não autorizado"})
            assert body["email"] == DIAL_PROBE_EMAIL                # nunca um ramal real
            return self._send(404, {"status": "ERROR", "email": "e-mail não encontrado"})
        return self._send(404, {})


class _Forward(httpx.BaseTransport):
    """Cliente do teste de conexão: tudo vai para o servidor falso local (HTTP de verdade), guardando o host."""

    def __init__(self, port):
        self.port, self.real = port, httpx.HTTPTransport()

    def handle_request(self, req):
        headers = dict(req.headers)
        headers["X-Orig-Host"] = req.url.host
        url = req.url.copy_with(scheme="http", host="127.0.0.1", port=self.port)
        return self.real.handle_request(httpx.Request(req.method, url, headers=headers, content=req.read()))


@pytest.fixture
def fake55():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Fake)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()


def test_teste_de_conexao_contra_servidor_falso(env, fake55):
    _key(env)
    base = "http://127.0.0.1:%d" % fake55
    env.svc.tester.http = httpx.Client(transport=_Forward(fake55), timeout=5)
    env.s.bridge.chatwoot_url = base
    h = session(env, "tok-admin")
    r = _put(env, h, values={"pbx_api_url": base + "/api/pbx/reports/metrics", "dial_mode": "live",
                             "dial_url": base + "/api/webphone/dial", "dial_client_code": "cc-ficticio",
                             "n8n_base_url": base + "/n8n", "audio_send_api_key": True},
             secrets={"pbx_api_key": _Fake.good_key, "dial_api_key": "ak-ficticio", "dial_jwt": "jwt-ficticio",
                      "chatwoot_api_token": "token-integracao-ficticio", "n8n_hmac_secret": "segredo-n8n"})
    assert r.status_code == 200, r.text
    res = env.client.post(ST + "/test", headers=h)
    assert res.status_code == 200
    items = {x["id"]: x for x in res.json()["items"]}
    assert set(items) == {"report02", "webhook", "recordings", "dial", "ura", "chatwoot", "n8n", "storage"}
    st = {k: v["status"] for k, v in items.items()}
    assert st == {"report02": "ok", "webhook": "ok", "recordings": "ok", "dial": "ok", "ura": "ok", "chatwoot": "ok",
                  "n8n": "ok", "storage": "ok"}, items
    assert "1 registro" in items["report02"]["detail"] and "nada foi discado" in items["dial"]["detail"]
    # com uma gravação recente, confere a autenticação do download (HEAD com a chave)
    post(env, rt("1760000905.1"))
    run(env)
    items = {x["id"]: x for x in env.client.post(ST + "/test", headers=h).json()["items"]}
    assert items["recordings"]["status"] == "ok" and "acessível" in items["recordings"]["detail"]
    # valores NÃO salvos no corpo: chave errada e credenciais da discagem erradas -> erro com motivo; nada gravado
    bad = env.client.post(ST + "/test", headers=h, json={"secrets": {"pbx_api_key": "chave-errada", "dial_jwt": "x"},
                                                         "values": {"audio_send_api_key": False}})
    items = {x["id"]: x for x in bad.json()["items"]}
    assert items["report02"]["status"] == "error" and "recusou a chave" in items["report02"]["detail"]
    assert items["dial"]["status"] == "error" and "recusou" in items["dial"]["detail"]
    assert env.svc.settings.effective("dev55").bridge.pbx_api_key == _Fake.good_key
    assert "chave-errada" not in bad.text and _Fake.good_key not in bad.text
    # sem credenciais: itens "missing" (D1/D4), sem chamar a 55PBX
    _put(env, h, secrets={"pbx_api_key": None, "dial_jwt": None})
    items = {x["id"]: x for x in env.client.post(ST + "/test", headers=h).json()["items"]}
    assert items["report02"]["status"] == "missing" and items["dial"]["status"] == "missing"


def test_teste_de_conexao_host_inalcancavel(env):
    def handler(req):
        raise httpx.ConnectTimeout("time-out")
    env.svc.tester.http = httpx.Client(transport=httpx.MockTransport(handler))
    items = {x["id"]: x for x in env.client.post(ST + "/test", headers=session(env, "tok-admin")).json()["items"]}
    assert items["recordings"]["status"] == "error" and "D3" in items["recordings"]["detail"]
    assert items["dial"]["status"] == "warning"                                  # mock (DEV)
    assert items["chatwoot"]["status"] == "error"


def test_checklist_d1_a_d4(env):
    _key(env)
    h = session(env, "tok-admin")
    ck = {x["id"]: x for x in env.client.get(ST, headers=h).json()["checklist"]}
    assert [ck[k]["done"] for k in ("D1", "D2", "D3", "D4")] == [False, False, False, False]
    post(env, rt("1760000906.1"))
    run(env)
    _put(env, h, values={"dial_mode": "live", "dial_client_code": "cc"},
         secrets={"pbx_api_key": "chave-ficticia-0001", "dial_api_key": "ak-ficticio", "dial_jwt": "jwt-ficticio"})
    ck = {x["id"]: x for x in env.client.get(ST, headers=h).json()["checklist"]}
    assert [ck[k]["done"] for k in ("D1", "D2", "D3", "D4", "MAPS", "ENABLED")] == [True, True, True, True, True, True]
    assert ck["D3"]["info"]["recordings_stored"] == 1


def test_apply_nao_altera_o_ambiente(env):
    eff = apply(env.s, {"pbx_api_key_header": "token", "dial_mode": "live", "n8n_base_url": "https://n8n.test"},
                {"pbx_api_key": "k"}, 3)
    assert eff.bridge.pbx_api_key_header == "token" and eff.dial_mode == "live" and eff.panel["n8n_base_url"]
    assert eff.settings_version == 3 and env.s.bridge.pbx_api_key_header == "key" and env.s.dial_mode == "mock"
    assert SECRET  # o segredo do seed continua no conftest
