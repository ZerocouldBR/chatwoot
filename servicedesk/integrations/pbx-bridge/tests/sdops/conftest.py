"""Fixtures do sd-ops: Postgres de TESTE real (SDOPS_TEST_DATABASE_URL, banco servicedesk_ops_test no DEV),
Chatwoot falso em memória, stream em memória, storage local temporário e 55PBX falsa. Dados FICTÍCIOS."""
from __future__ import annotations

import io
import os
import threading
import wave

import httpx
import pytest
import sqlalchemy as sa

from pbx_bridge.audio import AudioError
from pbx_bridge.chatwoot import ChatwootError
from pbx_bridge.config import Settings
from pbx_bridge.normalize import slug
from sd_ops import db
from sd_ops import models as m
from sd_ops.app import Services, create_app
from sd_ops.bootstrap import migrate, seed_tenant
from sd_ops.config import OpsSettings
from sd_ops.dial import DialAdapter
from sd_ops.events import MemoryPublisher
from sd_ops.storage import LocalStorage
from tests.fakes import AGENTS, FakeCW

URL = os.environ.get("SDOPS_TEST_DATABASE_URL")
SECRET = "w" * 40
SECRET_OUTRO = "o" * 40
FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")

pytestmark = pytest.mark.skipif(not URL, reason="SDOPS_TEST_DATABASE_URL não definido")


def wav(seconds: float, rate: int = 8000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x01" * int(seconds * rate))
    return buf.getvalue()


def rt(call_id, phase="end", **kw):
    """Registro FICTÍCIO no formato do manual 'Integração REST' (tempo real)."""
    d = {"central_id": "3855", "branch_mask": 5005, "call_id": call_id, "call_date": "2026-10-13 10:00:00",
         "call_terminal": "", "call_type": "receptive", "call_number": "999990001", "call_area_code": "11",
         "call_country_code": "55", "call_document": "", "call_order": "", "call_ura": "",
         "call_queue": "3855-FILA_SUPORTE_1", "call_status": "", "call_disconnection": "",
         "branch_email": "ramal5005@pbx.test"}
    if phase == "end":
        d.update(call_status="call_attended", call_disconnection="externo", call_time=45, call_duration=30,
                 call_time_waiting=15,
                 call_url_audio="https://vsa19.55pbx.com/webphone/webphone-0000/2026/10/13/audio-%s.WAV" % call_id,
                 call_audio_file="audio-%s.WAV" % call_id)
    d.update(kw)
    return d


class FakeCW2(FakeCW):
    """Chatwoot falso com as leituras usadas pelo sd-ops e simulação de indisponibilidade."""

    def __init__(self):
        super().__init__()
        self.down = False
        self.lock = threading.RLock()

    def _chk(self):
        if self.down:
            raise ChatwootError(503, "Chatwoot fora do ar (simulado)")

    def __getattribute__(self, name):
        a = object.__getattribute__(self, name)
        if callable(a) and not name.startswith("_") and name not in ("down",):
            def w(*args, **kw):
                object.__getattribute__(self, "_chk")()
                with object.__getattribute__(self, "lock"):
                    return a(*args, **kw)
            return w
        return a

    def search_contacts(self, q):
        return [c for c in self.contacts if c.get("phone_number") == q or c.get("identifier") == q]

    def get_contact(self, cid):
        return next((c for c in self.contacts if c["id"] == cid), None)

    def get_conversation(self, cid):
        c = self.convs[cid]
        c.setdefault("meta", {})["sender"] = {"id": c["contact_id"]}
        return c

    def teams_of_agent(self, agent_id):
        return super().teams_of_agent(agent_id)


class FakeDownloader:
    def __init__(self):
        self.plan = {}       # url -> lista de respostas (bytes ou AudioError); última se repete
        self.default = wav(30)
        self.calls = 0

    def __call__(self, url, max_bytes, timeout=120.0, headers=None, client=None):
        self.calls += 1
        seq = self.plan.get(url)
        if seq:
            r = seq.pop(0) if len(seq) > 1 else seq[0]
            if isinstance(r, Exception):
                raise r
            return r
        return self.default


PROFILES = {
    "tok-ana": {"id": 11, "name": "Ana Teste", "email": "ana.teste@exemplo.test", "accounts": [{"id": 4, "role": "agent"}]},
    "tok-bruno": {"id": 12, "name": "Bruno Ficticio", "email": "bruno.ficticio@exemplo.test",
                  "accounts": [{"id": 4, "role": "agent"}]},
    "tok-admin": {"id": 1, "name": "Admin Dev", "email": "admin@exemplo.test", "accounts": [{"id": 4, "role": "administrator"}]},
    "tok-outro": {"id": 50, "name": "Outro", "email": "outro@exemplo.test", "accounts": [{"id": 99, "role": "administrator"}]},
}


def profile_fn(tok):
    from sd_ops.auth import AuthError
    if tok not in PROFILES:
        raise AuthError("invalid_chatwoot_token", "token do Chatwoot inválido", 401)
    return PROFILES[tok]


@pytest.fixture(scope="session")
def engine():
    eng = db.make_engine(URL)
    with eng.begin() as conn:
        conn.execute(sa.text("DROP SCHEMA IF EXISTS ops CASCADE"))
    migrate(URL)
    return eng


def _truncate(engine):
    names = ", ".join("ops.%s" % t.name for t in m.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE %s RESTART IDENTITY CASCADE" % names))


class Env:
    pass


@pytest.fixture
def env(engine, tmp_path, monkeypatch):
    _truncate(engine)
    monkeypatch.setenv("CW_TOKEN_DEV55", "t-dev55")
    monkeypatch.setenv("URA_TOKEN_DEV55", "u" * 32)
    monkeypatch.setenv("URA_TOKEN_OUTRO", "x" * 32)
    monkeypatch.setenv("PBX_TOKEN_OUTRO", "tok-55pbx-outro")
    b = Settings(enabled=True, chatwoot_url="http://cw.test", chatwoot_api_token="t", chatwoot_account_id=4,
                 pbx_inbox_id=7, integration_user_id=99, webhook_secret=SECRET, audio_allowed_hosts=["*.55pbx.com"],
                 trigger_close_teams=["Novos Negócios"], trigger_close_types=["ativo"], ffmpeg_bin=FFMPEG,
                 trust_proxy=False)
    b2 = Settings.from_env()
    b.queue_team_map, b.team_area_map, b.trigger_close_attrs = b2.queue_team_map, b2.team_area_map, b2.trigger_close_attrs
    b.branch_agent_map = {"5005": "ana.teste@exemplo.test", "5010": "bruno.ficticio@exemplo.test"}
    s = OpsSettings(bridge=b, env="dev", database_url=URL, default_tenant="dev55", recording_url_secret="r" * 40,
                    recording_initial_delay_s=0, recording_max_attempts=4, outbox_base_delay_s=1, outbox_max_attempts=3,
                    inbox_max_attempts=3, cookie_secure=False, storage_dir=str(tmp_path / "rec"), dial_mode="mock",
                    dial_pending_s=0, breaker_threshold=1000,
                    service_tokens={"qa-pipeline": {"sha256": db.sha256("sdsvc_qa"), "tenants": ["dev55"],
                                                    "scopes": ["calls:read", "recordings:read", "analysis:write", "tickets:read"]},
                                    "n8n": {"sha256": db.sha256("sdsvc_n8n"), "tenants": ["*"],
                                            "scopes": ["calls:read", "tickets:read", "tickets:write", "callbacks:write",
                                                       "reconcile:run", "notify:send", "reports:read"]}})
    with engine.begin() as conn:
        seed_tenant(conn, "dev55", "Teste 55PBX (dev)", 4, 7, 99, "DEV", SECRET, None, "CW_TOKEN_DEV55",
                    {"type": "token", "header": "X-SD-URA-Token", "ref": "URA_TOKEN_DEV55"})
        seed_tenant(conn, "outro", "Outro tenant", 99, 70, 990, "OUT", SECRET_OUTRO, "PBX_TOKEN_OUTRO", "CW_TOKEN_DEV55",
                    {"type": "token", "header": "X-SD-URA-Token", "ref": "URA_TOKEN_OUTRO"})
        conn.execute(m.agent_phone_mappings.insert().values(tenant_id="dev55", branch="5005", agent_email="ana.teste@exemplo.test",
                                                            pbx_email="ramal5005@pbx.test", chatwoot_user_id=11))
        conn.execute(m.user_roles.insert().values(tenant_id="dev55", chatwoot_user_id=12, role="supervisor"))
    e = Env()
    e.s, e.engine = s, engine
    e.cws = {}

    def cw_factory(bs):
        return e.cws.setdefault(bs.chatwoot_account_id, FakeCW2())
    e.pub = MemoryPublisher()
    e.storage = LocalStorage(s.storage_dir)
    e.dl = FakeDownloader()
    e.dial_http = []
    e.dial_resp = [httpx.Response(200, json={"status": "OK", "call_id": "1760000000.999", "message": "Ligação efetuada com sucesso"})]

    def handler(req):
        e.dial_http.append(req)
        r = e.dial_resp[0] if len(e.dial_resp) == 1 else e.dial_resp.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    e.dial = DialAdapter(s, httpx.Client(transport=httpx.MockTransport(handler)))
    e.svc = Services(s, engine=engine, publisher=e.pub, storage=e.storage, cw_factory=cw_factory,
                     profile_fn=profile_fn, dial=e.dial, downloader=e.dl)
    e.app = create_app(s, services=e.svc, start_workers=False)
    from fastapi.testclient import TestClient
    with TestClient(e.app) as c:
        e.client = c
        yield e


@pytest.fixture
def cw(env):
    return env.svc.sync.tenant("dev55").cw


def post(env, rec, secret=SECRET, method="POST", headers=None):
    import json as _j
    return env.client.request(method, "/integracoes/55pbx/webhook/" + secret, content=_j.dumps(rec),
                              headers=dict({"content-type": "application/json"}, **(headers or {})))


def run(env, n=60):
    return env.svc.worker.run_until_idle(n)


def q(env, sql, **kw):
    import uuid as _u
    with env.engine.begin() as conn:
        rows = conn.execute(sa.text(sql), kw).fetchall()
    return [tuple(str(v) if isinstance(v, _u.UUID) else v for v in r) for r in rows]


def one(env, sql, **kw):
    r = q(env, sql, **kw)
    return r[0][0] if r else None


def session(env, tok="tok-ana", account=4):
    r = env.client.post("/sd-ops/api/v1/auth/session", json={"chatwoot_token": tok, "account_id": account})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["session_token"]}


def due_now(env):
    """Antecipa itens com backoff (simula a passagem do tempo)."""
    with env.engine.begin() as conn:
        conn.execute(sa.text("UPDATE ops.outbox SET next_attempt_at = now() WHERE status = 'pending'"))
        conn.execute(sa.text("UPDATE ops.webhook_inbox SET next_attempt_at = now() WHERE status = 'pending'"))
        conn.execute(sa.text("UPDATE ops.call_recordings SET next_attempt_at = now() WHERE status = 'pending'"))
    env.svc.worker.breaker.open_until.clear()
