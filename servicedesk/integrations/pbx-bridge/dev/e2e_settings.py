"""E2E no DEV da tela Telefonia 55PBX (configuração pelo painel), pela mesma rota que o navegador usa.

Pré-requisitos (ver docs/INTEGRACAO-55PBX.md, "Configuração pelo painel (admin)"):
- Chatwoot DEV (conta 4 "Teste 55PBX (dev)") com um administrador fictício (admin.telefonia@exemplo.test);
- sd-ops DEV com SDOPS_SETTINGS_KEY e ENABLED=false (dormente), atrás de um proxy de mesmo domínio que manda
  /sd-ops e /integracoes/55pbx para o sd-ops e o resto para o Rails (como o Traefik da demo);
- E2E_BASE (ex. http://proxy-dev:8081) e SDOPS_DATABASE_URL (o banco do Chatwoot DEV é o chatwoot_dev do mesmo
  Postgres). Os tokens dos usuários fictícios são lidos do banco do DEV e nunca impressos.

Fluxo: sem sessão 401, agente 403, admin 200 -> grava token de integração (cofre), ativa a integração pela tela
(o ambiente continua ENABLED=false), gera segredo A, webhook com A aceito, gera B, B aceito e A recusado, a ligação
vira conversa no Chatwoot real (token da tela), teste de conexão e auditoria sem segredos.
"""
from __future__ import annotations

import json
import os
import sys
import time

import httpx
import sqlalchemy as sa

BASE = os.environ.get("E2E_BASE", "http://proxy-dev:8081").rstrip("/")
API = BASE + "/sd-ops/api/v1"
OPS = os.environ["SDOPS_DATABASE_URL"]
CW = OPS.rsplit("/", 1)[0] + "/" + os.environ.get("E2E_CHATWOOT_DB", "chatwoot_dev")
ACCOUNT = int(os.environ.get("E2E_ACCOUNT", "4"))
results = []


def check(name, ok, info=""):
    results.append((name, bool(ok)))
    print("%s %s%s" % ("OK  " if ok else "FALHA", name, (" (%s)" % info) if info else ""))


def token_of(conn, email):
    return conn.execute(sa.text("""select t.token from access_tokens t join users u on u.id = t.owner_id
                                   where t.owner_type = 'User' and u.email = :e"""), {"e": email}).scalar()


def session(c, tok):
    r = c.post(API + "/auth/session", json={"chatwoot_token": tok, "account_id": ACCOUNT})
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["session_token"]}


def call(cid, phone="11999990077"):
    return {"central_id": "3855", "branch_mask": 5005, "call_id": cid, "call_date": "2026-10-14 10:00:00",
            "call_type": "receptive", "call_number": phone[2:], "call_area_code": phone[:2], "call_country_code": "55",
            "call_queue": "3855-FILA_SUPORTE_1", "call_status": "call_attended", "call_disconnection": "externo",
            "call_time": 40, "call_duration": 30, "call_time_waiting": 10, "branch_email": "ramal5005@pbx.test"}


def main() -> int:
    cw = sa.create_engine(CW)
    ops = sa.create_engine(OPS)
    with cw.connect() as conn:
        t_admin = token_of(conn, "admin.telefonia@exemplo.test")
        t_ana = token_of(conn, "ana.teste@exemplo.test")
        t_integ = conn.execute(sa.text("select token from access_tokens where owner_type='User' and owner_id=12")).scalar()
    assert t_admin and t_ana and t_integ, "tokens do DEV não encontrados"
    c = httpx.Client(timeout=60)

    check("sem sessão -> 401", c.get(API + "/admin/settings").status_code == 401)
    ha = session(c, t_ana)
    check("agente (Ana) -> 403", c.get(API + "/admin/settings", headers=ha).status_code == 403)
    h = session(c, t_admin)
    r = c.get(API + "/admin/settings", headers=h)
    check("administrator -> 200", r.status_code == 200)
    g = r.json()
    check("cofre ativo (SDOPS_SETTINGS_KEY)", g["vault"]["enabled"])
    check("integração dormente no ambiente", g["env_enabled"] is False)
    before_ok = c.post(BASE + "/integracoes/55pbx/webhook/" + "x" * 64, json=call("1791000000.0")).status_code == 404
    check("segredo desconhecido -> 404", before_ok)

    body = {"version": g["version"],
            "values": {"enabled": True, "dial_mode": "mock", "queue_team_map": {"fila_suporte_1": "Suporte"},
                       "poll_interval_min": 15},
            "secrets": {"chatwoot_api_token": t_integ},
            "agent_mappings": [{"branch": "5005", "agent_email": "ana.teste@exemplo.test", "chatwoot_user_id": 9}]}
    r = c.put(API + "/admin/settings", json=body, headers=h)
    check("PUT pela tela -> 200", r.status_code == 200, r.text[:200] if r.status_code != 200 else "")
    d = r.json()
    tf = d["fields"]["chatwoot_api_token"]
    check("token mascarado (últimos 4, origem tela)", tf["last4"] == t_integ[-4:] and tf["source"] == "panel")
    check("resposta sem o token em claro", t_integ not in r.text)
    check("ativada pela tela", d["fields"]["enabled"]["value"] is True and d["fields"]["enabled"]["source"] == "panel")
    with ops.connect() as conn:
        raw = conn.execute(sa.text("select secrets::text from ops.tenant_settings where tenant_id='dev55'")).scalar()
    check("token só cifrado no banco", t_integ not in (raw or "") and "gAAAAA" in (raw or ""))

    a = c.post(API + "/admin/settings/webhook-secret", headers=h).json()
    sec_a = a["url"].rsplit("/", 1)[1]
    r1 = c.post(BASE + "/integracoes/55pbx/webhook/" + sec_a, json=call("1791000001.1"))
    check("webhook com o segredo A -> 202", r1.status_code == 202, str(r1.status_code))
    b = c.post(API + "/admin/settings/webhook-secret", headers=h).json()
    sec_b = b["url"].rsplit("/", 1)[1]
    r2 = c.post(BASE + "/integracoes/55pbx/webhook/" + sec_b, json=call("1791000001.2", "11999990078"))
    r3 = c.post(BASE + "/integracoes/55pbx/webhook/" + sec_a, json=call("1791000001.3"))
    check("segredo novo (B) aceito -> 202", r2.status_code == 202, str(r2.status_code))
    check("segredo antigo (A) recusado -> 404", r3.status_code == 404, str(r3.status_code))
    check("URL completa só na geração", sec_b not in c.get(API + "/admin/settings", headers=h).text)

    conv = None
    for _ in range(60):
        with ops.connect() as conn:
            conv = conn.execute(sa.text("""select conversation_id from ops.calls where tenant_id='dev55'
                                           and root_provider_call_id='1791000001.2'
                                           and conversation_id is not null""")).scalar()
        if conv:
            break
        time.sleep(2)
    check("ligação processada com a config da tela -> conversa no Chatwoot", bool(conv), "conversa #%s" % conv)
    if conv:
        with cw.connect() as conn:
            n = conn.execute(sa.text("select count(*) from messages where conversation_id = (select id from "
                                     "conversations where display_id=:d and account_id=:a)"), {"d": conv, "a": ACCOUNT}).scalar()
        check("notas criadas na conversa real", (n or 0) >= 1, "%s mensagem(ns)" % n)

    t = c.post(API + "/admin/settings/test", headers=h).json()
    st = {x["id"]: x["status"] for x in t["items"]}
    print("    teste de conexão:", json.dumps(st, ensure_ascii=False))
    for x in t["items"]:
        print("      - %s: %s — %s" % (x["id"], x["status"], x["detail"]))
    check("teste de conexão: Chatwoot ok com o token da tela", st.get("chatwoot") == "ok")
    check("teste de conexão: Report02 sem chave = falta (D1)", st.get("report02") == "missing")
    with ops.connect() as conn:
        aud = conn.execute(sa.text("""select action, actor_id, data::text from ops.audit_events
                                      where action like 'admin.settings%' order by id desc limit 10""")).fetchall()
    check("auditoria com o admin e sem segredos",
          aud and all(x[1] for x in aud) and not any(t_integ in x[2] or sec_a in x[2] or sec_b in x[2] for x in aud),
          ", ".join(sorted({x[0] for x in aud})))
    ok = sum(1 for _, v in results if v)
    print("E2E_SETTINGS %d/%d" % (ok, len(results)))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
