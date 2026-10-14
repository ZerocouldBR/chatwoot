"""E2E do sd-ops no ambiente DEV (dados e áudio FICTÍCIOS).

Sobe, no host: uma 55PBX falsa (gravações WAV, Report02 com chave no header e API de discagem que confere
client_code/api_key/Bearer) e o sd-ops (uvicorn + workers) apontando para o Chatwoot DEV (conta 4 "Teste 55PBX
(dev)"), o Postgres DEV (banco servicedesk_ops) e o Redis DEV (DB 7, stream sd:events). Confere tudo pela API do
Chatwoot, pela API do sd-ops, pelo banco e pelo stream.

  set -a; . dev/run/dev.env; . dev/run/sdops.env; set +a; .venv/bin/python dev/e2e_sdops.py
"""
from __future__ import annotations

import base64
import http.server
import io
import json
import os
import random
import secrets
import sys
import threading
import time
import wave
from urllib.parse import urlparse

import httpx
import redis
import sqlalchemy as sa
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pbx_bridge.config import Settings  # noqa: E402
from sd_ops import db  # noqa: E402
from sd_ops import models as m  # noqa: E402
from sd_ops.app import create_app  # noqa: E402
from sd_ops.bootstrap import migrate, seed_tenant  # noqa: E402
from sd_ops.config import OpsSettings  # noqa: E402

FAKE, PORT = 18091, 18090
BASE = "http://127.0.0.1:%d" % PORT
API = BASE + "/sd-ops/api/v1"
RUN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run")
TAG = str(int(time.time()))[-6:]
R = random.Random(int(TAG))
PBX_KEY = "chave-ficticia-" + secrets.token_hex(4)
DIAL = {"client_code": "cc-dev", "api_key": "ak-" + secrets.token_hex(4), "jwt": "jwt-" + secrets.token_hex(8)}
RESULTS = []
AUDIO_HITS = {}
REPORT_ROWS = []
DIAL_HITS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok)))
    print(("OK   " if ok else "FALHA") + " " + name + (" — " + str(detail) if detail else ""), flush=True)


def wav(seconds, rate=8000):
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(R.getrandbits(8) for _ in range(256)) * int(seconds * rate * 2 / 256))
    return b.getvalue()


AUDIO = {}


class FakePbx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body=b"", ctype="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = urlparse(self.path).path
        if p.startswith("/audio/"):
            name = os.path.basename(p)
            AUDIO_HITS[name] = AUDIO_HITS.get(name, 0) + 1
            if name.startswith("late-") and AUDIO_HITS[name] == 1:
                return self._send(404, b"not ready")
            data = AUDIO.get(name)
            return self._send(200, data, "audio/x-wav") if data else self._send(404, b"")
        if p.startswith("/api/pbx/reports/metrics/"):
            if self.headers.get("key") != PBX_KEY:
                return self._send(401, b'{"error":"key"}')
            return self._send(200, json.dumps({"data_report02": REPORT_ROWS}).encode())
        self._send(404)

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("content-length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        if p == "/api/webphone/dial":
            DIAL_HITS.append((dict(self.headers), body))
            if (self.headers.get("client_code") != DIAL["client_code"] or self.headers.get("api_key") != DIAL["api_key"]
                    or self.headers.get("Authorization") != "Bearer " + DIAL["jwt"]):
                return self._send(401, b'{"status":"ERROR"}')
            if not str(body.get("phone", "")).startswith("+"):
                return self._send(404, json.dumps({"status": "ERROR", "phone": "Telefone inválido"}).encode())
            cid = "17%s.%d" % (TAG, 900 + len(DIAL_HITS))
            return self._send(200, json.dumps({"status": "OK", "call_id": cid, "message": "Ligação efetuada com sucesso"}).encode())
        self._send(404)


def rec(cid, phase="end", audio=None, **kw):
    d = {"central_id": "3855", "branch_mask": 5005, "call_id": cid, "call_date": "2026-10-13 10:00:00",
         "call_type": "receptive", "call_number": NUM, "call_area_code": "11", "call_country_code": "55",
         "call_ura": "", "call_queue": "3855-FILA_SUPORTE_1", "call_status": "", "branch_email": "ramal5005@exemplo.test"}
    if phase == "end":
        d.update(call_status="call_attended", call_disconnection="externo", call_time=40, call_duration=25,
                 call_time_waiting=15)
        if audio:
            AUDIO[audio] = wav(25)
            d["call_url_audio"] = "http://127.0.0.1:%d/audio/%s" % (FAKE, audio)
    d.update(kw)
    return d


def wait(fn, timeout=40, every=0.5):
    t = time.time()
    while time.time() - t < timeout:
        v = fn()
        if v:
            return v
        time.sleep(every)
    return fn()


NUM = "9%04d%04d" % (R.randint(0, 9999), int(TAG) % 10000)   # número FICTÍCIO único por execução


def main() -> int:
    cw_url, cw_tok, acc = os.environ["CHATWOOT_URL"], os.environ["CHATWOOT_API_TOKEN"], int(os.environ["CHATWOOT_ACCOUNT_ID"])
    dburl, rurl = os.environ["SDOPS_DATABASE_URL"], os.environ["SDOPS_REDIS_URL"]
    secret = secrets.token_hex(32)
    os.environ.update({"E2E_CW_TOKEN": cw_tok, "E2E_URA_TOKEN": "ura-" + secrets.token_hex(16)})
    migrate(dburl)
    eng = db.make_engine(dburl)
    cw = httpx.Client(base_url="%s/api/v1/accounts/%d" % (cw_url, acc), headers={"api_access_token": cw_tok}, timeout=30)
    agents = {a["email"]: a for a in cw.get("/agents").json()}
    ana = agents.get("ana.teste@exemplo.test")
    with eng.begin() as conn:
        seed_tenant(conn, "dev55", "Teste 55PBX (dev)", acc, int(os.environ["PBX_INBOX_ID"]),
                    int(os.environ["INTEGRATION_USER_ID"]), "DEV", secret, None, "E2E_CW_TOKEN",
                    {"type": "token", "header": "X-SD-URA-Token", "ref": "E2E_URA_TOKEN"})
        conn.execute(m.agent_phone_mappings.update().where(m.agent_phone_mappings.c.tenant_id == "dev55").values(active=False))
        conn.execute(m.agent_phone_mappings.insert().values(tenant_id="dev55", branch="5005", agent_email="ana.teste@exemplo.test",
                                                            pbx_email="ramal5005@exemplo.test",
                                                            chatwoot_user_id=int(os.environ["INTEGRATION_USER_ID"])))
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        conn.execute(pg_insert(m.user_roles).values(tenant_id="dev55", chatwoot_user_id=int(os.environ["INTEGRATION_USER_ID"]),
                                                    role="supervisor").on_conflict_do_nothing())
    check("migrations + tenant dev55 (conta %d)" % acc, True)

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", FAKE), FakePbx)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    b = Settings.from_env()
    b.enabled, b.webhook_secret, b.chatwoot_url = True, "", cw_url
    b.audio_allowed_hosts = ["127.0.0.1", "*.55pbx.com"]
    b.pbx_api_url, b.pbx_api_key, b.pbx_http_timeout = "http://127.0.0.1:%d/api/pbx/reports/metrics" % FAKE, PBX_KEY, 30
    b.branch_agent_map = {"5005": "ana.teste@exemplo.test", "5010": "bruno.ficticio@exemplo.test"}
    b.trust_proxy = False
    s = OpsSettings.from_env()
    s.bridge, s.env, s.database_url, s.redis_url, s.default_tenant = b, "dev", dburl, rurl, "dev55"
    s.recording_url_secret, s.recording_initial_delay_s, s.storage_dir = secrets.token_hex(32), 0, os.path.join(RUN, "recordings")
    s.cookie_secure, s.dial_mode, s.dial_url = False, "live", "http://127.0.0.1:%d/api/webphone/dial" % FAKE
    s.dial_client_code, s.dial_api_key, s.dial_jwt, s.dial_pending_s = DIAL["client_code"], DIAL["api_key"], DIAL["jwt"], 0
    s.outbox_base_delay_s, s.log_json = 2, True
    app = create_app(s, start_workers=True)
    svc = app.state.services
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning", access_log=False))
    threading.Thread(target=server.run, daemon=True).start()
    wait(lambda: httpx.get(BASE + "/sd-ops/health").status_code == 200 if _up() else False, 20)
    r = httpx.get(API + "/ready").json()
    check("ready (banco, Redis DB 7, storage, migration 0001)", r["status"] == "ok" and r["migration"] == "0001", r)
    rd = redis.Redis.from_url(rurl)
    start_id = (rd.xrevrange("sd:events", count=1) or [(b"0-0", {})])[0][0]
    hook = BASE + "/integracoes/55pbx/webhook/" + secret

    def send(d, method="POST"):
        return httpx.request(method, hook, json=d, timeout=10)

    def q(sql, **kw):
        import uuid as _u
        with eng.begin() as conn:
            rows = conn.execute(sa.text(sql), kw).fetchall()
        return [tuple(str(v) if isinstance(v, _u.UUID) else v for v in r) for r in rows]

    def call(pcid):
        rows = q("select c.state, c.outcome, c.conversation_id, c.contact_id, c.legs_count, c.id from ops.calls c "
                 "join ops.call_legs l on l.call_id=c.id where l.provider_call_id=:p", p=pcid)
        return rows[0] if rows else None

    # ---------------------------------------------------------------- 1. receptiva (cliente novo)
    c1 = "17%s.101" % TAG
    send(rec(c1, "start"))
    r = send(rec(c1, audio="a-%s.WAV" % TAG))
    check("webhook responde 202 após persistir", r.status_code == 202 and r.json()["accepted"], r.text[:120])
    row = wait(lambda: (lambda c: c if c and c[2] else None)(call(c1)))
    check("receptiva: chamada encerrada e atendida", row and row[0] == "ended" and row[1] == "answered", row)
    conv = row[2] if row else None
    tk = wait(lambda: q("select t.protocol, t.protocol_numeric, t.status, t.id from ops.support_tickets t join ops.ticket_calls tc "
                        "on tc.ticket_id=t.id where tc.call_id=:c", c=row[5]))
    check("receptiva: ticket criado (protocolo legível + numérico)", tk and tk[0][0].startswith("DEV-2026-") and len(tk[0][1]) == 11, tk)
    tid, prot, pnum = tk[0][3], tk[0][0], tk[0][1]
    cv = wait(lambda: (lambda c: c if (c.get("custom_attributes") or {}).get("sd_protocolo") else None)(cw.get("/conversations/%d" % conv).json()))
    ca = (cv or {}).get("custom_attributes") or {}
    check("Chatwoot: conversa com sd_protocolo, zd_status e pbx_call_id", ca.get("sd_protocolo") == prot and ca.get("zd_status") == "Novo"
          and ca.get("pbx_call_id") == c1, {k: ca.get(k) for k in ("sd_protocolo", "zd_status", "pbx_call_id")})
    msgs = wait(lambda: (lambda ms: ms if any(mm.get("attachments") for mm in ms) else None)(
        cw.get("/conversations/%d/messages" % conv).json()["payload"]), 60)
    srcs = [mm.get("source_id") for mm in msgs or []]
    check("Chatwoot: notas da ligação (registro/atualização) + MP3 anexado", "55pbx:%s:registro" % c1 in srcs
          and "55pbx:%s:atualizacao" % c1 in srcs and any(mm.get("attachments") for mm in msgs or []), srcs)
    rr = wait(lambda: q("select status, mime, duration_s, sha256, storage_key, id from ops.call_recordings where call_id=:c", c=row[5])
              if q("select 1 from ops.call_recordings where call_id=:c and status='stored'", c=row[5]) else None)
    check("gravação: baixada, validada (WAV 25 s) e guardada", rr and rr[0][1] == "audio/wav" and abs(rr[0][2] - 25) < 0.2, rr and rr[0][:3])
    rec_id = rr[0][5] if rr else None

    # ---------------------------------------------------------------- 2. duplicado + fora de ordem
    r = send(rec(c1, audio="a-%s.WAV" % TAG), "PUT")
    check("evento final duplicado: 200 duplicate", r.status_code == 200 and r.json()["duplicate"], r.text[:80])
    c2 = "17%s.102" % TAG
    num2 = "9%08d" % R.randint(0, 99999999)
    send(rec(c2, call_number=num2))
    send(rec(c2, "start", call_number=num2))
    row2 = wait(lambda: (lambda c: c if c and c[2] else None)(call(c2)))
    check("final antes do inicial: encerrada, sem regredir", row2 and row2[0] == "ended", row2)

    # ---------------------------------------------------------------- 3. transferência entre ramais
    c3a, c3b = "17%s.103" % TAG, "17%s.104" % TAG
    send(rec(c3a, "start"))
    send(rec(c3a, call_transfer_id=c3b))
    send(rec(c3b, "start", branch_mask=5010))
    send(rec(c3b, branch_mask=5010, audio="b-%s.WAV" % TAG))
    row3 = wait(lambda: (lambda c: c if c and c[0] == "ended" and c[2] else None)(call(c3b)))
    check("transferência: 1 chamada lógica, 2 pernas", row3 and row3[4] == 2 and call(c3a)[5] == row3[5], row3)
    if row3:
        ms3 = wait(lambda: (lambda ms: ms if "55pbx:%s:perna:%s" % (c3a, c3b) in [x.get("source_id") for x in ms] else None)(
            cw.get("/conversations/%d/messages" % row3[2]).json()["payload"]), 40)
        check("transferência: nota 'Transferência 55PBX' na mesma conversa", bool(ms3))

    # ---------------------------------------------------------------- 4. abandonada na fila -> retorno
    c4 = "17%s.105" % TAG
    num4 = "9%08d" % R.randint(0, 99999999)
    send(rec(c4, "start", call_number=num4))
    send(rec(c4, "start", call_number=num4, call_time=50, call_duration=0, call_time_waiting=45, call_disconnection="cliente"))
    row4 = wait(lambda: (lambda c: c if c and c[0] == "ended" else None)(call(c4)))
    cb = q("select reason, status from ops.callback_tasks where call_id=:c", c=row4[5]) if row4 else []
    check("abandonada na fila: outcome + tarefa de retorno", row4 and row4[1] == "abandoned_queue" and cb == [("abandoned_queue", "pending")], (row4, cb))

    # ---------------------------------------------------------------- 5. áudio atrasado
    c5 = "17%s.106" % TAG
    send(rec(c5, audio="late-%s.WAV" % TAG, call_number="9%08d" % R.randint(0, 99999999)))
    st5 = wait(lambda: (lambda x: x if x and x[0][1] >= 1 else None)(
        q("select status, attempts from ops.call_recordings r join ops.call_legs l on l.id=r.leg_id where l.provider_call_id=:p", p=c5)))
    check("áudio atrasado: 1ª tentativa 404 -> pendente com backoff", st5 and st5[0][0] == "pending" and st5[0][1] == 1, st5)
    with eng.begin() as conn:
        conn.execute(sa.text("update ops.outbox set next_attempt_at=now() where kind='recording.fetch' and status='pending'"))
        conn.execute(sa.text("update ops.call_recordings set next_attempt_at=now() where status='pending'"))
    svc.worker.wake.set()
    st5 = wait(lambda: (lambda x: x if x and x[0][0] == "stored" else None)(
        q("select r.status from ops.call_recordings r join ops.call_legs l on l.id=r.leg_id where l.provider_call_id=:p", p=c5)))
    check("áudio atrasado: armazenado na 2ª tentativa", bool(st5))

    # ---------------------------------------------------------------- 6. sessão do CTI com o Chatwoot REAL
    bad = httpx.post(API + "/auth/session", json={"chatwoot_token": "token-errado", "account_id": acc})
    check("CTI: token inválido do Chatwoot -> 401", bad.status_code == 401, bad.text[:80])
    ses = httpx.post(API + "/auth/session", json={"chatwoot_token": cw_tok, "account_id": acc})
    check("CTI: GET /api/v1/profile valida o token e emite sessão", ses.status_code == 200 and ses.json()["tenant"]["id"] == "dev55",
          ses.json().get("roles") if ses.status_code == 200 else ses.text[:100])
    H = {"Authorization": "Bearer " + ses.json()["session_token"]} if ses.status_code == 200 else {}
    ctx = httpx.get(API + "/context", params={"conversation_id": conv}, headers=H).json()
    check("CTI: contexto da conversa (ticket aberto, chamadas, SLA)", ctx.get("open_tickets") and ctx["recent_calls"]
          and ctx["open_tickets"][0]["sla"], {"tickets": len(ctx.get("open_tickets") or []), "calls": len(ctx.get("recent_calls") or [])})

    # ---------------------------------------------------------------- 7. click-to-call
    d = httpx.post(API + "/dial", json={"phone": "+55" + "11" + NUM, "ticket_id": tid, "conversation_id": conv}, headers=H)
    ok = d.status_code == 200 and d.json()["status"] == "accepted"
    hdr = DIAL_HITS[-1][0] if DIAL_HITS else {}
    check("click-to-call: API de discagem com client_code/api_key/Bearer e {email, phone}", ok and DIAL_HITS[-1][1] ==
          {"email": "ramal5005@exemplo.test", "phone": "+5511" + NUM}, d.text[:120])
    if ok:
        pc = d.json()["provider_call_id"]
        send(rec(pc, call_type="active"))
        row7 = wait(lambda: (lambda c: c if c and c[2] else None)(call(pc)))
        rel = q("select relation from ops.ticket_calls where call_id=:c and ticket_id=:t", c=row7[5], t=tid) if row7 else []
        check("click-to-call: ligação do webhook ligada ao mesmo ticket e conversa", row7 and row7[2] == conv and rel == [("dial",)], (row7, rel))

    # ---------------------------------------------------------------- 8. estados do ticket -> conversa
    for to in ("em_atendimento", "aguardando_cliente"):
        httpx.post(API + "/tickets/%s/transitions" % tid, json={"to": to}, headers=H)
    st8 = wait(lambda: (lambda c: c if c.get("status") == "snoozed" else None)(cw.get("/conversations/%d" % conv).json()))
    check("ticket aguardando_cliente -> conversa snoozed + zd_status Pendente", st8 and st8["custom_attributes"].get("zd_status") == "Pendente",
          st8 and st8.get("status"))
    httpx.post(API + "/tickets/%s/transitions" % tid, json={"to": "resolvido"}, headers=H)
    st8 = wait(lambda: (lambda c: c if c.get("status") == "resolved" else None)(cw.get("/conversations/%d" % conv).json()))
    check("ticket resolvido -> conversa resolved", bool(st8))
    bad_tr = httpx.post(API + "/tickets/%s/transitions" % tid, json={"to": "novo"}, headers=H)
    check("transição inválida -> 409", bad_tr.status_code == 409)

    # ---------------------------------------------------------------- 9. URA (menu dinâmico)
    ura = httpx.get(API + "/ura/tickets/" + pnum, params={"ani": "11" + NUM}, headers={"X-SD-URA-Token": os.environ["E2E_URA_TOKEN"]}).json()
    check("URA: protocolo numérico + telefone confere -> situação", ura.get("encontrado") == "sim" and ura.get("verificado") == "sim"
          and ura.get("situacao") == "resolvido", ura)
    ura2 = httpx.get(API + "/ura/tickets/" + pnum, params={"ani": "11900000000"}, headers={"X-SD-URA-Token": os.environ["E2E_URA_TOKEN"]}).json()
    check("URA: telefone diferente -> sem detalhes", ura2.get("verificado") == "nao" and "situacao" not in ura2, ura2)

    # ---------------------------------------------------------------- 10. gravação por URL temporária
    if rec_id:
        u = httpx.get(API + "/recordings/%s/url" % rec_id, headers=H).json()
        a = httpx.get(BASE + u["url"], headers={"Range": "bytes=0-43"})
        check("gravação: URL assinada de 300 s, Range 206, sem URL da 55PBX", a.status_code == 206 and a.content[:4] == b"RIFF"
              and "127.0.0.1:%d" % FAKE not in u["url"], (u.get("expires_in"), a.status_code))

    # ---------------------------------------------------------------- 11. reconciliação pelo Report02
    c11 = "17%s.111" % TAG
    REPORT_ROWS[:] = [{"call_id": c11, "name": "Ana Teste", "call_time_total_duration": "00:00:50", "call_time_waiting": "00:00:20",
                       "call_time_spoken": "00:00:00", "branch_number_agent": "", "call_number": "9%08d" % R.randint(0, 99999999),
                       "call_area_code": "11", "wg_country_code": "55", "call_date": "13/10/2026", "wb_call_hour": "11:00:00",
                       "queue_name": "3855-FILA_SUPORTE_1", "type_call": "receptivo"},
                      {"call_id": c1, "name": "Ana Teste", "call_time_total_duration": "00:00:40", "call_time_waiting": "00:00:15",
                       "call_time_spoken": "00:00:25", "branch_number_agent": "5005", "call_number": NUM, "call_area_code": "11",
                       "wg_country_code": "55", "call_date": "13/10/2026", "wb_call_hour": "10:00:00",
                       "queue_name": "3855-FILA_SUPORTE_1", "type_call": "receptivo"}]
    rc = svc.worker.poll_once()
    check("reconciliação: Report02 com chave no header", rc.get("rows") == 2, rc)
    r11 = wait(lambda: (lambda c: c if c and c[0] == "ended" else None)(call(c11)))
    check("reconciliação: ligação perdida no tempo real criada pelo relatório", r11 and r11[1] == "abandoned_queue", r11)
    n1 = q("select count(*) from ops.calls c join ops.call_legs l on l.call_id=c.id where l.provider_call_id=:p", p=c1)[0][0]
    check("reconciliação: ligação já conhecida não duplica", n1 == 1)

    # ---------------------------------------------------------------- 12. métricas e stream
    mt = httpx.get(API + "/metrics/telephony", params={"from": "2026-10-13T00:00:00Z"}, headers=H)
    check("métricas de telefonia (supervisor)", mt.status_code == 200 and mt.json()["groups"]["total"]["recebidas"] >= 4,
          mt.json()["groups"]["total"] if mt.status_code == 200 else mt.text[:80])
    time.sleep(3)
    evs = rd.xrange("sd:events", min="(" + start_id.decode() if isinstance(start_id, bytes) else "-")
    types = {}
    payload_txt = ""
    for _id, f in evs:
        env = json.loads(f[b"data"])
        if env["tenant_id"] != "dev55":
            continue
        types[env["type"]] = types.get(env["type"], 0) + 1
        payload_txt += f[b"data"].decode()
    need = {"call.started", "call.ended", "call.transferred", "call.missed", "recording.stored", "ticket.created",
            "ticket.status_changed", "callback.created"}
    check("stream sd:events (Redis DB 7): tipos publicados", need <= set(types), types)
    check("stream: sem número completo do cliente", NUM not in payload_txt)
    h = httpx.get(BASE + "/sd-ops/health").json()
    check("health: nada em DLQ", h["outbox_dead"] == 0 and h["inbox_dead"] == 0, h)

    server.should_exit = True
    svc.worker.shutdown()
    srv.shutdown()
    ok = sum(1 for _, o in RESULTS if o)
    print("\nRESULTADO: %d/%d verificações OK (TAG %s)" % (ok, len(RESULTS), TAG))
    return 0 if ok == len(RESULTS) else 1


def _up():
    try:
        return httpx.get(BASE + "/sd-ops/health", timeout=1)
    except httpx.HTTPError:
        return None


if __name__ == "__main__":
    sys.exit(main())
