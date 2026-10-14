"""Teste de ponta a ponta no ambiente DEV (dados FICTÍCIOS, áudio sintético gerado com ffmpeg).

Sobe, no host: um servidor falso da 55PBX (gravações WAV + Report02) e o pbx-bridge (uvicorn), ambos em
127.0.0.1, apontando para o Chatwoot DEV em http://127.0.0.1:3000. Envia 5 ligações (receptiva, ativa em 2
etapas, interna pelo poller, sem áudio e uma repetida), testa o gatilho de atribuição e o backfill, e confere
tudo pela API do ServiceDesk.

  set -a; . dev/run/dev.env; set +a; .venv/bin/python dev/e2e.py
(dev.env: CHATWOOT_URL, CHATWOOT_API_TOKEN, CHATWOOT_ACCOUNT_ID, PBX_INBOX_ID, INTEGRATION_USER_ID, FFMPEG_BIN)
"""
from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

import httpx
import uvicorn

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pbx_bridge import backfill  # noqa: E402
from pbx_bridge.app import create_app  # noqa: E402
from pbx_bridge.config import Settings  # noqa: E402

RUN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run")
AUDIO_DIR = os.path.join(RUN, "audio")
FAKE_PORT, BRIDGE_PORT = 18081, 18080
FFMPEG = os.environ.get("FFMPEG_BIN", "ffmpeg")
PBX_KEY = "chave-ficticia-" + secrets.token_hex(4)
REPORT_ROWS = []
REPORT_HITS = []
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("OK   " if ok else "FALHA") + " " + name + (" — " + detail if detail else ""), flush=True)


# ------------------------------------------------------------------ 55PBX falsa
class FakePbx(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _audio(self, head):
        name = os.path.basename(urlparse(self.path).path)
        p = os.path.join(AUDIO_DIR, name)
        if not os.path.exists(p):
            self.send_response(404)
            self.end_headers()
            return
        data = open(p, "rb").read()
        self.send_response(200)
        self.send_header("Content-Type", "audio/x-wav")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if not head:
            self.wfile.write(data)

    def do_HEAD(self):
        self._audio(True)

    def do_GET(self):
        if self.path.startswith("/audio/"):
            return self._audio(False)
        if self.path.startswith("/api/pbx/reports/metrics/"):
            REPORT_HITS.append(self.path)
            if self.headers.get("key") != PBX_KEY:
                self.send_response(401)
                self.end_headers()
                return
            body = json.dumps({"data_report02": REPORT_ROWS, "reportCount": len(REPORT_ROWS), "uuid": "fake"}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


def make_wav(name, seconds, freq):
    os.makedirs(AUDIO_DIR, exist_ok=True)
    p = os.path.join(AUDIO_DIR, name)
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i",
                    "sine=frequency=%d:duration=%d" % (freq, seconds), "-ar", "8000", "-ac", "1", "-c:a", "pcm_s16le", p],
                   check=True)
    return os.path.getsize(p)


def row(call_id, **kw):
    r = {"call_id": call_id, "ws_ticket_id": "", "name": "", "call_disconnection": "", "call_time_total_duration": "",
         "call_time_waiting": "", "call_time_spoken": "", "call_url_audio": "", "branch_number_agent": "",
         "call_number": "", "call_area_code": "", "wg_country_code": "55", "wf_states": "SP",
         "call_date": time.strftime("%d/%m/%Y"), "wb_call_hour": time.strftime("%H:%M:%S"), "queue_name": "undefined",
         "type_call": "", "call_number_input": "", "call_document": "", "call_order": "undefined", "way_ura": "",
         "call_time_URA": "", "wl_time_attended": "", "call_id_origin": ""}
    r.update(kw)
    return r


def main():
    base = os.environ["CHATWOOT_URL"].rstrip("/")
    acc = int(os.environ["CHATWOOT_ACCOUNT_ID"])
    inbox = int(os.environ["PBX_INBOX_ID"])
    api = httpx.Client(base_url="%s/api/v1/accounts/%d" % (base, acc),
                       headers={"api_access_token": os.environ["CHATWOOT_API_TOKEN"]}, timeout=60)
    os.makedirs(RUN, exist_ok=True)
    sizes = {n: make_wav(n, s, f) for n, s, f in (("a.wav", 30, 440), ("b.wav", 60, 523), ("c.wav", 12, 659),
                                                  ("h.wav", 20, 392))}
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", FAKE_PORT), FakePbx)
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    secret = secrets.token_urlsafe(40)
    evsecret = secrets.token_hex(16)
    agents = {a["email"]: a["id"] for a in api.get("/agents").json()}
    env = {
        "ENABLED": "true", "WEBHOOK_SECRET": secret, "CHATWOOT_WEBHOOK_HMAC_SECRET": evsecret,
        "PBX_API_URL": "http://127.0.0.1:%d/api/pbx/reports/metrics" % FAKE_PORT, "PBX_API_KEY": PBX_KEY,
        "PBX_API_KEY_HEADER": "key", "POLL_INTERVAL_MIN": "60", "AUDIO_ALLOWED_HOSTS": "127.0.0.1",
        "BRANCH_AGENT_MAP": json.dumps({"5005": "ana.teste@exemplo.test", "5010": "bruno.ficticio@exemplo.test"}),
        "DB_PATH": os.path.join(RUN, "e2e-%d.sqlite3" % int(time.time())), "FFMPEG_BIN": FFMPEG, "TRUST_PROXY": "false",
    }
    os.environ.update(env)
    s = Settings.from_env()
    app = create_app(s)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=BRIDGE_PORT, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    br = app.state.bridge
    bridge = httpx.Client(base_url="http://127.0.0.1:%d/integracoes/55pbx" % BRIDGE_PORT, timeout=30)
    for _ in range(50):
        try:
            if bridge.get("/health").status_code == 200:
                break
        except httpx.TransportError:
            time.sleep(0.2)
    h = bridge.get("/health").json()
    check("health responde e ENABLED=true", h["status"] == "ok" and h["enabled"] is True)

    t0 = int(time.time())
    A, B, C, D = ("%d.%d" % (t0, n) for n in (101, 202, 303, 404))
    au = "http://127.0.0.1:%d/audio/" % FAKE_PORT
    rA = row(A, name="Ana Teste", type_call="receptivo", branch_number_agent="5005", call_number="11999990001",
             queue_name="3855-FILA_SUPORTE_1", call_time_total_duration="00:00:41", call_time_waiting="00:00:08",
             call_time_spoken="00:00:30", call_disconnection="client", call_url_audio=au + "a.wav", way_ura="Opcao - 2")
    rC = row(C, name="Ana Teste", type_call="interno", branch_number_agent="5005", call_number="5010",
             call_time_total_duration="00:00:15", call_time_spoken="00:00:12", call_url_audio=au + "c.wav",
             call_disconnection="operator")
    url = "/webhook/" + secret

    # segurança
    check("webhook com segredo errado -> 404", bridge.post("/webhook/errado", json=rA).status_code == 404)
    r = bridge.post(url, content=b'{"telefone":"11999990009"}', headers={"content-type": "application/json"})
    check("payload sem call_id fica 'não reconhecido'", r.json().get("unparsed") == 1)

    # 1) receptiva completa (JSON, POST)
    check("ligação 1 receptiva (JSON/POST) aceita", bridge.post(url, json=rA).json().get("queued") == 1)
    # 2) ativa em 2 etapas (form-urlencoded, PUT): início e fim
    start = {"call_id": B, "type_call": "ativo", "branch_number_agent": "5010", "call_number": "21988880002",
             "name": "Bruno Fictício", "queue_name": "3855-ativo"}
    end = dict(start, call_time_total_duration="00:01:10", call_time_spoken="00:01:00", call_time_waiting="00:00:10",
               call_disconnection="operator", call_url_audio=au + "b.wav", humor="4")
    check("ligação 2 ativa: início (form/PUT)", bridge.put(url, data=start).json().get("queued") == 1)
    time.sleep(3)
    check("ligação 2 ativa: fim (form/PUT)", bridge.put(url, data=end).json().get("queued") == 1)
    # 4) sem áudio, ramal sem agente mapeado (fixo)
    rD = row(D, type_call="receptivo", branch_number_agent="7777", call_number="1130000004", queue_name="undefined",
             call_time_total_duration="00:00:20", call_time_spoken="00:00:05", call_disconnection="client")
    check("ligação 4 sem áudio aceita", bridge.post(url, json=rD).json().get("queued") == 1)
    # 3) interna chega só pelo Report02 (poller); 5) a 1 repetida também vem no Report02
    REPORT_ROWS[:] = [rA, rC]
    pr = br.poll_once()
    check("poller: Report02 com a chave no header", REPORT_HITS and pr.get("rows") == 2,
          "%s, URL %s" % (pr, re.sub(r"/metrics/.*?/all_queues", "/metrics/<datas>/all_queues", REPORT_HITS[-1])))
    # 5) repetida pelo webhook
    check("ligação 5 = repetição da 1 aceita", bridge.post(url, json=rA).json().get("queued") == 1)

    deadline = time.time() + 120
    while time.time() < deadline:
        br.wake.set()
        c = br.store.counts()
        if not c.get("events_pending"):
            break
        time.sleep(1)
    c = br.store.counts()
    check("fila vazia sem erros", not c.get("events_pending") and not c.get("events_error"), json.dumps(c))

    # ------------------------------------------------------------------ conferência no ServiceDesk
    def conv_of(cid):
        body = {"payload": [{"attribute_key": "pbx_call_id", "attribute_model": "customAttributes",
                             "custom_attribute_type": "conversation_attribute", "filter_operator": "equal_to",
                             "values": [cid], "query_operator": None}]}
        items = api.post("/conversations/filter?page=1", json=body).json()["payload"]
        return items

    def msgs(conv_id):
        return api.get("/conversations/%d/messages" % conv_id).json()["payload"]

    report = {}
    for label, cid in (("1-receptiva", A), ("2-ativa", B), ("3-interna", C), ("4-sem-audio", D)):
        items = conv_of(cid)
        check("%s: exatamente 1 conversa" % label, len(items) == 1, "achadas %d" % len(items))
        if not items:
            continue
        cv = api.get("/conversations/%d" % items[0]["id"]).json()
        ms = [m for m in msgs(cv["id"]) if m.get("message_type") != 2]
        srcs = [m.get("source_id") for m in ms]
        audios = [a for m in ms for a in (m.get("attachments") or []) if a.get("file_type") == "audio"]
        report[label] = {"conversa": cv["id"], "status": cv["status"], "time": (cv["meta"].get("team") or {}).get("name"),
                         "responsavel": (cv["meta"].get("assignee") or {}).get("name"), "etiquetas": cv.get("labels"),
                         "notas": len(ms), "privadas": all(m.get("private") for m in ms), "audios": len(audios),
                         "atributos": {k: v for k, v in cv["custom_attributes"].items()
                                       if k.startswith("pbx_") or k in ("zd_area_interna", "zd_onboarding_relacionamento",
                                                                        "zd_novos_negocios", "zd_status")},
                         "assunto": (cv.get("additional_attributes") or {}).get("mail_subject")}
        check("%s: sem notas duplicadas" % label, len(srcs) == len(set(srcs)), str(srcs))
        check("%s: notas privadas" % label, report[label]["privadas"])
        report[label]["_audios"] = audios
        report[label]["_inbox"] = cv["inbox_id"]
    r1, r2, r3, r4 = (report.get(k, {}) for k in ("1-receptiva", "2-ativa", "3-interna", "4-sem-audio"))
    check("1: inbox Telefone (55PBX)", r1.get("_inbox") == inbox)
    check("1: time Suporte pela fila, responsável Ana (ramal 5005)", (r1.get("time") or "").lower() == "suporte"
          and r1.get("responsavel") == "Ana Teste", "%s / %s" % (r1.get("time"), r1.get("responsavel")))
    check("1: 3 notas (registro, atualização+áudio, ação) e 1 áudio", r1.get("notas") == 3 and r1.get("audios") == 1)
    check("1: etiquetas 55pbx e 55pbx_receptivo", sorted(r1.get("etiquetas") or []) == ["55pbx", "55pbx_receptivo"])
    at = r1.get("atributos", {})
    check("1: atributos de ligação", at.get("pbx_tipo") == "receptivo" and at.get("pbx_duracao_total") == 41
          and at.get("pbx_tempo_falado") == 30 and at.get("pbx_numero") == "+5511999990001"
          and at.get("zd_area_interna") == "Suporte" and at.get("zd_onboarding_relacionamento") == "Ligação", json.dumps(at, ensure_ascii=False))
    check("2: time Novos Negócios (do agente), 4 notas, 1 áudio", "neg" in (r2.get("time") or "").lower()
          and r2.get("notas") == 4 and r2.get("audios") == 1, "%s, %s notas" % (r2.get("time"), r2.get("notas")))
    check("2: gatilho 'Encerra ATIVOS Novos Negócios' (resolvido + Prospecção)", r2.get("status") == "resolved"
          and r2.get("atributos", {}).get("zd_novos_negocios") == "Prospecção"
          and r2.get("atributos", {}).get("zd_status") == "Resolvido")
    check("2: humor 4/5 registrado", r2.get("atributos", {}).get("pbx_humor") == 4)
    check("3: interna pelo poller, etiqueta 55pbx_interno, 1 áudio", "55pbx_interno" in (r3.get("etiquetas") or [])
          and r3.get("audios") == 1)
    check("4: sem áudio, sem responsável (ramal sem mapa)", r4.get("audios") == 0 and r4.get("responsavel") is None)

    # áudio MP3 de verdade (baixa o anexo e mede)
    for label, wav in (("1-receptiva", "a.wav"), ("2-ativa", "b.wav")):
        a = (report.get(label, {}).get("_audios") or [None])[0]
        if not a:
            continue
        u = urlparse(a["data_url"])
        data = httpx.get(base + u.path + ("?" + u.query if u.query else ""), follow_redirects=True, timeout=30).content
        p = subprocess.run([FFMPEG, "-hide_banner", "-i", "pipe:0", "-f", "null", "-"], input=data,
                           stderr=subprocess.PIPE, stdout=subprocess.PIPE)
        info = p.stderr.decode(errors="replace")
        mono = "mono" in info and "mp3" in info
        br_ = re.search(r"(\d+) kb/s", info)
        report[label]["mp3"] = {"bytes": len(data), "wav_bytes": sizes[wav], "kbps": br_ and int(br_.group(1)),
                                "reducao": round(sizes[wav] / max(1, len(data)), 1)}
        check("%s: anexo é MP3 mono ~32 kbps" % label, mono and br_ and int(br_.group(1)) == 32,
              "%d bytes (WAV %d, %sx menor)" % (len(data), sizes[wav], report[label]["mp3"]["reducao"]))

    # gatilho 1: agente escreve nota numa ligação sem responsável -> vira responsável
    if r4.get("conversa"):
        ana = agents.get("ana.teste@exemplo.test")
        payload = {"event": "message_created", "message_type": "outgoing", "private": True,
                   "sender": {"id": ana, "type": "user", "name": "Ana Teste"},
                   "conversation": {"id": r4["conversa"], "inbox_id": inbox, "labels": r4.get("etiquetas"),
                                    "meta": {"assignee": None}}}
        body = json.dumps(payload).encode()
        ts = str(int(time.time()))
        sig = "sha256=" + hmac.new(evsecret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
        bad = bridge.post("/servicedesk-events/" + secret, content=body)
        ok = bridge.post("/servicedesk-events/" + secret, content=body,
                         headers={"x-chatwoot-timestamp": ts, "x-chatwoot-signature": sig})
        time.sleep(2)
        cv = api.get("/conversations/%d" % r4["conversa"]).json()
        check("gatilho 'Atribui o usuário responsável': assinatura inválida recusada", bad.status_code == 401)
        check("gatilho 'Atribui o usuário responsável': Ana virou responsável",
              ok.status_code == 200 and (cv["meta"].get("assignee") or {}).get("id") == ana)

    # backfill: conversa "importada" com a URL do Áudio numa nota
    ct = api.post("/contacts", json={"name": "Contato histórico (teste)", "phone_number": "+5511999990077"})
    contact_id = (ct.json().get("payload") or {}).get("contact", {}).get("id") if ct.status_code < 300 else None
    if contact_id is None:
        contact_id = [x for x in api.get("/contacts/search", params={"q": "+5511999990077"}).json()["payload"]][0]["id"]
    cvh = api.post("/conversations", json={"inbox_id": inbox, "contact_id": contact_id,
                                           "source_id": "e2e-hist-%d" % t0}).json()
    hist = api.post("/conversations/%d/messages" % cvh["id"], json={
        "content": "Atualização de ligação da  55PBX:    Tipo de ligaçãoativoTempo falado18Tempo total de ligação20URL do Áudio"
                   + au + "h.wav", "private": True, "source_id": "zd:comment:e2e-%d" % t0}).json()
    lbl = "hist_e2e_%d" % t0
    api.post("/conversations/%d/labels" % cvh["id"], json={"labels": [lbl]})
    b1 = backfill.run(s, br.store, br.cw, sleep=0, label=lbl, dry_run=True)
    b2 = backfill.run(s, br.store, br.cw, sleep=0, label=lbl)
    b3 = backfill.run(s, br.store, br.cw, sleep=0, label=lbl)
    hm = msgs(cvh["id"])
    reply = [m for m in hm if (m.get("source_id") or "").startswith("55pbx:backfill:")]
    check("backfill dry-run não baixa nada", b1["mensagens_com_audio"] == 1 and b1["anexadas"] == 0)
    check("backfill anexa 1 gravação como resposta à mensagem", b2["anexadas"] == 1 and len(reply) == 1
          and (reply[0].get("content_attributes") or {}).get("in_reply_to") == hist["id"]
          and any(a.get("file_type") == "audio" for a in reply[0].get("attachments") or []))
    check("backfill re-executado é idempotente", b3["anexadas"] == 0 and b3["ja_feitas"] == 1)

    h = bridge.get("/health").json()
    print("\nHEALTH", json.dumps(h, ensure_ascii=False))
    for k, v in report.items():
        v = {kk: vv for kk, vv in v.items() if not kk.startswith("_")}
        print("RESUMO", k, json.dumps(v, ensure_ascii=False))
    print("BACKFILL", json.dumps({"dry": b1, "1a": b2, "2a": b3}, ensure_ascii=False))
    ok = sum(1 for r in RESULTS if r[1])
    print("\nE2E: %d/%d verificações OK" % (ok, len(RESULTS)))
    server.should_exit = True
    br.shutdown()
    srv.shutdown()
    return 0 if ok == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
