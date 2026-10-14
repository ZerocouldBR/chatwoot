"""sd-ops FALSO para desenvolvimento e capturas de tela do sd-console (dados FICTÍCIOS).

Reproduz o FORMATO das respostas do sd-ops real (sd_ops/api.py, commit a0f8e93717 do A2) nas rotas que o
sd-console usa. Não é o sd-ops: não fala com a 55PBX, não grava nada e se identifica como mock
(`/health` -> "mock": true, o console mostra a faixa "MODO MOCK"). Gravações e conversas vêm do último
relatório do dev/e2e.py (áudios sintéticos do Piper).

Sessões fixas de DEV (token do "Chatwoot" -> usuário fictício):
  dev-agente -> carla@exemplo.test (agente) · dev-supervisor -> sup@exemplo.test (supervisor, qa, admin)

  uvicorn dev.mock_sdops:app --host 0.0.0.0 --port 8081
"""
from __future__ import annotations

import glob
import json
import os
import random
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

P = "/sd-ops/api/v1"
HERE = os.path.dirname(os.path.abspath(__file__))
STORAGE = os.environ.get("MOCK_STORAGE", os.path.join(HERE, "run", "e2e-storage"))
USERS = {
    "dev-agente": {"kind": "user", "tenant_id": "dev55", "user_id": 101, "email": "carla@exemplo.test",
                   "name": "Carla Fictícia", "roles": ["agente"], "scopes": [], "service": None},
    "dev-supervisor": {"kind": "user", "tenant_id": "dev55", "user_id": 102, "email": "sup@exemplo.test",
                       "name": "Sofia Supervisora (fictícia)", "roles": ["admin", "qa", "supervisor"], "scopes": [],
                       "service": None},
}
SESSIONS: dict = {}
TOKENS: dict = {}
app = FastAPI(title="sd-ops MOCK (DEV)")
now = datetime.now(timezone.utc)


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def report() -> dict:
    files = sorted(glob.glob(os.path.join(HERE, "run", "e2e_report_*.json")), key=os.path.getmtime)
    return json.load(open(files[-1], encoding="utf-8")) if files else {}


def calls_for(conv: int | None):
    rep = report()
    out = []
    itens = (rep.get("parte_b") or {}).get("itens", [])
    known = {str(it.get("conversa")) for it in itens}
    # Conversa fora do e2e (ex.: conta Demo do Chatwoot DEV): usa as ligações sintéticas por rodízio.
    alias = None
    if conv is not None and str(conv) not in known and itens:
        alias = str(itens[int(conv) % len(itens)].get("conversa"))
    for i, it in enumerate(itens):
        if conv is not None and str(it.get("conversa")) != (alias or str(conv)):
            continue
        rid = f"qa-e2e-{rep['tag']}-{i + 1}"
        ext = "wav" if "cobranca" in it["audio"] else "mp3"
        started = now - timedelta(minutes=12 + 30 * i)
        out.append({
            "id": f"call-{rid}", "root_provider_call_id": f"1760380{i}.55", "direction": "receptivo", "state": "ended",
            "outcome": "answered", "number_e164": f"+5511900000{i:03d}", "contact_id": 900 + i,
            "conversation_id": int(it["conversa"]) if it.get("conversa") else None, "queue": "FILA_SUPORTE_1",
            "ura": "1-Reservas", "branch": "5005", "agent_email": "carla@exemplo.test", "talk_s": 81 - 15 * i,
            "wait_s": 18 + i, "total_s": 100, "disconnection": "cliente", "legs_count": 1,
            "started_at": iso(started), "answered_at": iso(started + timedelta(seconds=18)),
            "ended_at": iso(started + timedelta(seconds=100)),
            "tickets": [{"id": f"tk-{i}", "protocol": f"DEV-2026-00012{3 + i}", "status": "em_atendimento"}],
            "recordings": [{"id": rid, "status": "stored", "mime": f"audio/{'wav' if ext == 'wav' else 'mpeg'}",
                            "duration_s": it.get("duracao_s") or 80, "integrity": "ok", "storage_key":
                            f"recordings/dev55/2026/10/{rid}.{ext}"}],
            "callback": None})
    return out


def principal(authorization: str | None, request: Request) -> dict:
    tok = (authorization or "")[7:] if (authorization or "").lower().startswith("bearer ") else request.cookies.get("sdops_session")
    if not tok or tok not in SESSIONS:
        raise HTTPException(401, detail={"error": "unauthenticated", "message": "autenticação necessária"})
    return SESSIONS[tok]


@app.get(P + "/health")
def health():
    return {"status": "ok", "service": "sd-ops", "version": "mock", "enabled": True, "mock": True}


@app.post(P + "/auth/session")
async def session(request: Request):
    body = await request.json()
    u = USERS.get(str(body.get("chatwoot_token", "")))
    if not u:
        raise HTTPException(401, detail={"error": "invalid_chatwoot_token", "message": "token do Chatwoot inválido"})
    tok = secrets.token_urlsafe(24)
    SESSIONS[tok] = u
    resp = JSONResponse({"session_token": tok, "csrf_token": secrets.token_hex(8), "expires_at": iso(now + timedelta(hours=8)),
                         "user": {"email": u["email"], "name": u["name"]}, "tenant": u["tenant_id"], "roles": u["roles"]})
    resp.set_cookie("sdops_session", tok, httponly=True, samesite="lax", path="/")
    return resp


@app.get(P + "/auth/me")
def me(request: Request, authorization: str | None = Header(None)):
    return principal(authorization, request)


@app.get(P + "/context")
def context(request: Request, conversation_id: int | None = None, authorization: str | None = Header(None)):
    principal(authorization, request)
    calls = calls_for(conversation_id)
    i = calls[0]["contact_id"] - 900 if calls else 0
    names = ["Roberto Fictício (Viagens Horizonte)", "Agência Serra Fictícia", "Marcos Cliente Fictício"]
    active = None
    if i == 0 and calls:
        active = {**calls[0], "id": "call-ativa", "state": "active", "ended_at": None,
                  "answered_at": iso(datetime.now(timezone.utc) - timedelta(seconds=95)), "recordings": []}
    return {"contact": {"id": 900 + i, "name": names[i % 3], "phone_number": f"+5511900000{i:03d}", "email": None,
                        "identifier": None},
            "phone_e164": f"+5511900000{i:03d}", "identification": "unique",
            "open_tickets": [{"id": f"tk-{i}", "protocol": f"DEV-2026-00012{3 + i}", "protocol_numeric": f"20260012{3 + i}",
                              "status": "em_atendimento", "subject": ["Voucher não recebido", "Reserva cancelada", "Atualizar cartão"][i % 3],
                              "category": "Reservas", "priority": "alta" if i == 1 else "normal",
                              "sla": [{"metric": "resolution", "status": "running", "breached": i == 1,
                                       "due_at": iso(datetime.now(timezone.utc) + timedelta(minutes=40 if i == 0 else 300)),
                                       "stopped_at": None, "target_min": 480}]}],
            "recent_calls": calls, "active_call": active, "callbacks_pending": [],
            "dial": {"available": True, "reason": None}}


@app.get(P + "/capabilities")
def capabilities(request: Request, authorization: str | None = Header(None)):
    """Mesmo formato do sd-ops real (GET /capabilities, WEBHOOK_CONTRACTS.md §8.4)."""
    principal(authorization, request)
    return {"tenant_id": "dev55", "env": "dev", "integration_enabled": True, "capabilities": {
        "dial": {"enabled": True, "mode": "mock", "reason": "MODO MOCK (DEV): nenhuma ligação real", "branch": "5005"},
        "webphone": {"enabled": False, "mode": "external", "url": None,
                     "reason": "webphone da 55PBX não configurado no sd-ops (PBX_WEBPHONE_URL)"},
        "callbacks": {"enabled": True, "reason": None},
        "recordings": {"enabled": True, "mode": "local", "reason": None},
        "ura": {"enabled": False, "mode": "menu_dinamico", "reason": "Menu Dinâmico (URA) sem credencial configurada"}}}


@app.get(P + "/calls")
def calls(request: Request, conversation_id: int | None = None, authorization: str | None = Header(None)):
    principal(authorization, request)
    return {"items": calls_for(conversation_id)}


@app.get(P + "/calls/{call_id}")
def call(call_id: str):
    for c in calls_for(None):
        if c["id"] == call_id:
            return c
    raise HTTPException(404, detail={"error": "not_found", "message": "chamada não encontrada"})


@app.get(P + "/callbacks")
def callbacks(request: Request, authorization: str | None = Header(None)):
    principal(authorization, request)
    return {"items": []}


@app.post(P + "/callbacks", status_code=201)
async def new_callback(request: Request, authorization: str | None = Header(None)):
    principal(authorization, request)
    return {"id": secrets.token_hex(4), "status": "pending", "due_at": (await request.json()).get("due_at")}


@app.post(P + "/dial")
def dial(request: Request, authorization: str | None = Header(None)):
    principal(authorization, request)
    return {"dial_id": secrets.token_hex(4), "status": "mock", "simulated": True,
            "message": "MODO MOCK (DEV): nenhuma ligação foi feita"}


@app.post(P + "/tickets/{ref}/notes", status_code=201)
def note(ref: str, request: Request, authorization: str | None = Header(None)):
    principal(authorization, request)
    return {"id": secrets.token_hex(4), "kind": "registro", "created_at": iso(datetime.now(timezone.utc)),
            "mirrored_to_chatwoot": False}


@app.post(P + "/tickets/{ref}/transitions")
def transition(ref: str, request: Request, authorization: str | None = Header(None)):
    principal(authorization, request)
    return {"id": ref, "status": "resolvido"}


@app.get(P + "/recordings/{rid}/url")
def rec_url(rid: str, request: Request, authorization: str | None = Header(None)):
    principal(authorization, request)
    tok = secrets.token_urlsafe(16)
    TOKENS[tok] = rid
    return {"url": f"{P}/recordings/stream/{tok}", "expires_at": iso(datetime.now(timezone.utc) + timedelta(seconds=300)),
            "expires_in": 300}


@app.get(P + "/recordings/stream/{tok}")
def stream(tok: str):
    rid = TOKENS.get(tok)
    for c in calls_for(None):
        for r in c["recordings"]:
            if r["id"] == rid:
                path = os.path.join(STORAGE, r["storage_key"])
                return FileResponse(path, media_type=r["mime"])
    raise HTTPException(404, detail={"error": "not_found", "message": "token inválido"})


def _tel(rnd: random.Random, scale: float = 1.0):
    rec = int(rnd.randint(40, 70) * scale)
    ab = int(rec * rnd.uniform(0.04, 0.12))
    lost = int(rec * rnd.uniform(0.01, 0.04))
    ans = rec - ab - lost
    return {"recebidas": rec, "atendidas": ans, "abandonadas": ab, "perdidas": lost, "efetuadas": int(rnd.randint(120, 180) * scale),
            "efetuadas_atendidas": int(rnd.randint(80, 110) * scale), "tma_receptivo_s": rnd.randint(140, 210),
            "tma_ativo_s": rnd.randint(90, 160), "tme_s": rnd.randint(12, 35), "tme_abandono_s": rnd.randint(40, 90),
            "nivel_servico": round(rnd.uniform(0.72, 0.93), 3), "taxa_abandono": round(ab / rec, 3) if rec else None,
            "transferidas": rnd.randint(2, 9), "por_resultado": {"answered": ans, "abandoned_queue": ab - 1, "abandoned_ura": 1,
                                                                  "missed": lost}}


@app.get(P + "/metrics/telephony")
def m_tel(request: Request, group_by: str | None = None, queue: str | None = None, authorization: str | None = Header(None)):
    principal(authorization, request)
    rnd = random.Random(42)
    groups = {"total": _tel(rnd, 14)}
    if group_by == "queue":
        for q in ("FILA_SUPORTE_1", "CHECKOUT_N2", "FILA_FINANCEIRO_1", "FILA_NOVOS_NEGOCIOS"):
            if not queue or queue == q:
                groups[f"queue={q}"] = _tel(rnd, 3.5)
    elif group_by == "day":
        for d in range(14):
            day = (datetime.now(timezone.utc) - timedelta(days=13 - d)).date().isoformat()
            groups[f"day={day}"] = _tel(rnd, 1.0 if (d % 7) < 5 else 0.3)
    elif group_by == "branch":
        for b, a in (("5005", "carla@exemplo.test"), ("5010", "bruno@exemplo.test"), ("5012", "marcos@exemplo.test")):
            groups[f"branch={b}"] = {**_tel(rnd, 4), "agente": a}
    return {"from": iso(datetime.now(timezone.utc) - timedelta(days=30)), "to": iso(datetime.now(timezone.utc)),
            "sl_threshold_s": 20, "short_abandon_s": 5, "groups": groups,
            "callbacks": {"criados": 21, "concluidos": 17, "pendentes": 3, "cancelados": 1, "vencidos_agora": 1},
            "fonte": "MOCK (dados fictícios)"}


@app.get(P + "/metrics/tickets")
def m_tk(request: Request, authorization: str | None = Header(None)):
    principal(authorization, request)
    return {"criados": 412, "resolvidos": 371, "backlog_agora": 96, "reaberturas": 14, "tempo_resolucao_medio_s": 30240,
            "tempo_resolucao_mediana_s": 14400,
            "sla": {"first_response": {"instancias": 412, "paradas": 398, "cumpridas": 371, "cumprimento": 0.932, "vencidas": 27},
                    "resolution": {"instancias": 412, "paradas": 371, "cumpridas": 326, "cumprimento": 0.879, "vencidas": 19}},
            "fcr": 0.64, "por_canal": {"telefone": 188, "email": 131, "whatsapp": 77, "chat": 16},
            "por_prioridade": {"normal": 301, "alta": 92, "urgente": 19},
            "por_equipe": {"Suporte": 210, "Novos Negócios": 88, "Treinamento": 61, "Financeiro": 53},
            "por_categoria": {"Reservas": 160, "Financeiro": 74, "Integrações": 71, "Acesso": 58, "Tarifas": 49}}


@app.post(P + "/analysis-results")
async def analysis(request: Request):
    return {"id": secrets.token_hex(4), "duplicate": False}
