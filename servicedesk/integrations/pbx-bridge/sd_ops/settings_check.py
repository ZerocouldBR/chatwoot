"""Teste de conexão da tela "Telefonia 55PBX" (POST /admin/settings/test).

Só usa endpoints documentados (docs/integrations/55PBX_API_MAPPING.md, PROVIDER_CAPABILITIES.md) e a API pública
do Chatwoot. Cada item devolve status ok | error | warning | missing | skipped e o motivo em pt-BR, sem segredos.

- report02: GET do Report02 (janela dos últimos 5 min) com a chave no header configurado → valida conectividade E
  autenticação (401/403 = chave recusada).
- recordings: alcance HTTPS do host de gravações (qualquer resposta HTTP = alcançável; time-out = IP não liberado,
  §9 da INTEGRACAO-55PBX.md) e, se houver uma gravação recente, HEAD nela com a autenticação configurada.
- dial: só com credenciais (client_code, api_key, JWT) e modo live. POST documentado com um ramal que não pode
  existir (domínio reservado .invalid, RFC 2606): 404 {status:"ERROR"} = credenciais aceitas; 401/403 = recusadas.
  Nenhuma ligação é feita.
- chatwoot: GET /api/v1/profile com o token do usuário de integração.
- webhook, ura, n8n, storage: configuração local (+ alcance do n8n, se houver URL).
"""
from __future__ import annotations

import datetime as dt
import ipaddress
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx
import sqlalchemy as sa

from pbx_bridge.audio import host_allowed
from pbx_bridge.normalize import mask as mask_text
from pbx_bridge.pbx_api import PbxApi, PbxError

from . import models as m
from .config import OpsSettings

DIAL_PROBE_EMAIL = "teste-conexao@sdops.invalid"
DIAL_PROBE_PHONE = "+5511900000000"


def _item(key: str, status: str, detail: str, **extra: Any) -> Dict[str, Any]:
    return dict({"id": key, "status": status, "detail": detail}, **extra)


def _transport(e: Exception) -> str:
    return "sem conexão (%s)" % type(e).__name__


class ConnectionTester:
    def __init__(self, http: Optional[httpx.Client] = None, timeout: float = 10.0,
                 storage_ping: Optional[Callable[[OpsSettings], bool]] = None):
        self.http = http or httpx.Client(timeout=timeout, follow_redirects=False)
        self.timeout = timeout
        self.storage_ping = storage_ping

    # ------------------------------------------------------------------ itens
    def report02(self, cfg: OpsSettings) -> Dict[str, Any]:
        b = cfg.bridge
        if not b.pbx_api_key:
            return _item("report02", "missing", "chave Webservice (API) não cadastrada (D1)")
        api = PbxApi(b.pbx_api_url, b.pbx_api_key, b.pbx_api_key_header, b.pbx_queue, b.pbx_number, b.pbx_agent,
                     b.tz_offset_hours, self.timeout, retries=0, client=self.http, sleep=lambda _s: None)
        end = dt.datetime.now(dt.timezone.utc)
        try:
            rows = api.report02(end - dt.timedelta(minutes=5), end)
        except PbxError as e:
            msg = str(e)
            if "recusou a chave" in msg:
                return _item("report02", "error", "a 55PBX recusou a chave (confira a chave e o nome do header)")
            return _item("report02", "error", "Report02 falhou: %s" % mask_text(msg)[:200])
        return _item("report02", "ok", "Report02 respondeu com a chave (%d registro(s) nos últimos 5 min)" % len(rows))

    def recordings(self, cfg: OpsSettings, host: str, sample_url: Optional[str]) -> Dict[str, Any]:
        b = cfg.bridge
        if not host:
            return _item("recordings", "missing", "host de gravações não informado")
        url = "https://%s/" % host
        if not host_allowed(url, b.audio_allowed_hosts):
            return _item("recordings", "error", "o host %s não está nos hosts permitidos para download" % host)
        try:
            r = self.http.get(url)
        except httpx.TransportError as e:
            return _item("recordings", "error", "host %s não alcançável: %s (pedir à 55PBX a liberação do IP da VPS, "
                                                "D3)" % (host, _transport(e)))
        detail = "host %s alcançável (HTTP %d na raiz)" % (host, r.status_code)
        if not sample_url:
            return _item("recordings", "ok", detail + "; sem gravação recente para conferir a autenticação")
        headers = {b.pbx_api_key_header: b.pbx_api_key} if (b.audio_send_api_key and b.pbx_api_key) else {}
        try:
            h = self.http.head(sample_url, headers=headers)
        except httpx.TransportError as e:
            return _item("recordings", "warning", detail + "; HEAD na gravação recente falhou: " + _transport(e))
        if h.status_code in (401, 403):
            return _item("recordings", "error", detail + "; a gravação exige autenticação (HTTP %d)" % h.status_code)
        if h.status_code == 200:
            return _item("recordings", "ok", detail + "; gravação recente acessível")
        return _item("recordings", "warning", detail + "; HEAD na gravação recente: HTTP %d" % h.status_code)

    def dial(self, cfg: OpsSettings) -> Dict[str, Any]:
        if cfg.dial_mode == "disabled":
            return _item("dial", "skipped", "click-to-call desativado (modo disabled)")
        if cfg.dial_mode == "mock":
            return _item("dial", "warning", "modo mock (só DEV): nenhuma ligação real")
        missing = [n for n, v in (("client_code", cfg.dial_client_code), ("api_key", cfg.dial_api_key),
                                  ("JWT", cfg.dial_jwt)) if not v]
        if missing:
            return _item("dial", "missing", "faltam credenciais da discagem: %s (D4)" % ", ".join(missing))
        headers = {"client_code": cfg.dial_client_code, "api_key": cfg.dial_api_key,
                   "Authorization": "Bearer " + cfg.dial_jwt, "Content-Type": "application/json"}
        try:
            r = self.http.post(cfg.dial_url, json={"email": DIAL_PROBE_EMAIL, "phone": DIAL_PROBE_PHONE},
                               headers=headers)
        except httpx.TransportError as e:
            return _item("dial", "error", "API de discagem não alcançável: " + _transport(e))
        try:
            body = r.json() if r.content else {}
        except ValueError:
            body = {}
        status = str((body or {}).get("status", "")).upper() if isinstance(body, dict) else ""
        if r.status_code in (401, 403):
            return _item("dial", "error", "a 55PBX recusou as credenciais da discagem (HTTP %d)" % r.status_code)
        if r.status_code == 404 and status == "ERROR":
            return _item("dial", "ok", "credenciais aceitas (ramal de teste inexistente, como esperado; nada foi discado)")
        if r.status_code == 404:
            return _item("dial", "error", "URL da discagem não encontrada (HTTP 404): confira a URL (D9)")
        return _item("dial", "warning", "resposta inesperada da discagem: HTTP %d" % r.status_code)

    def chatwoot(self, cfg: OpsSettings, token: str) -> Dict[str, Any]:
        base = cfg.bridge.chatwoot_url
        if not base:
            return _item("chatwoot", "missing", "CHATWOOT_URL não configurada no sd-ops")
        if not token:
            return _item("chatwoot", "missing", "token do usuário de integração não cadastrado")
        try:
            r = self.http.get(base.rstrip("/") + "/api/v1/profile", headers={"api_access_token": token})
        except httpx.TransportError as e:
            return _item("chatwoot", "error", "Chatwoot não alcançável: " + _transport(e))
        if r.status_code in (401, 403):
            return _item("chatwoot", "error", "o Chatwoot recusou o token do usuário de integração")
        if r.status_code != 200:
            return _item("chatwoot", "error", "Chatwoot respondeu HTTP %d" % r.status_code)
        accs = [a for a in (r.json().get("accounts") or []) if int(a.get("id") or 0) == int(cfg.bridge.chatwoot_account_id)]
        if not accs:
            return _item("chatwoot", "error", "o usuário de integração não pertence a esta conta")
        return _item("chatwoot", "ok", "token válido (usuário de integração, papel %s)" % (accs[0].get("role") or "?"))

    def n8n(self, cfg: OpsSettings) -> Dict[str, Any]:
        p = cfg.panel or {}
        base = p.get("n8n_base_url") or ""
        if not base:
            return _item("n8n", "skipped", "URL do n8n não informada (as rotas usam URL completa)")
        try:
            r = self.http.get(base)
        except httpx.TransportError as e:
            return _item("n8n", "error", "n8n não alcançável a partir do sd-ops: " + _transport(e))
        sec = "com" if p.get("n8n_hmac_secret") else "SEM"
        return _item("n8n", "ok" if p.get("n8n_hmac_secret") else "warning",
                     "n8n alcançável (HTTP %d); %s segredo HMAC na tela" % (r.status_code, sec))

    def storage(self, cfg: OpsSettings) -> Dict[str, Any]:
        if self.storage_ping is None:
            return _item("storage", "skipped", "sem verificação de storage")
        try:
            ok = self.storage_ping(cfg)
        except Exception as e:  # noqa: BLE001
            return _item("storage", "error", "storage %s indisponível: %s" % (cfg.storage_backend, type(e).__name__))
        return _item("storage", "ok" if ok else "error",
                     "storage %s %s" % (cfg.storage_backend, "gravável" if ok else "sem permissão de escrita"))


def webhook_item(cfg: OpsSettings, secret_defined: bool) -> Dict[str, Any]:
    if not secret_defined:
        return _item("webhook", "missing", "segredo do webhook não definido (gere um novo e cadastre a URL na 55PBX, D2)")
    for n in cfg.bridge.allowed_ips or []:
        ipaddress.ip_network(n, strict=False)
    ips = ("restrito a %d IP/CIDR" % len(cfg.bridge.allowed_ips)) if cfg.bridge.allowed_ips else "sem restrição de IP"
    state = "ativo" if cfg.enabled else "integração DESATIVADA (webhook responde 503)"
    return _item("webhook", "ok" if cfg.enabled else "warning", "URL configurada, %s; %s" % (ips, state))


def ura_item(ura: Dict[str, Any]) -> Dict[str, Any]:
    if not ura.get("type"):
        return _item("ura", "skipped", "Menu Dinâmico (URA) não configurado")
    if not ura.get("ready"):
        return _item("ura", "missing", "Menu Dinâmico sem credencial (%s)" % ura["type"])
    return _item("ura", "ok", "autenticação %s configurada" % ura["type"])


def latest_recording(conn, tenant_id: str) -> Optional[str]:
    return conn.execute(sa.select(m.call_recordings.c.source_url).where(
        m.call_recordings.c.tenant_id == tenant_id, m.call_recordings.c.source_url.isnot(None))
        .order_by(m.call_recordings.c.created_at.desc()).limit(1)).scalar()


def host_of(url: Optional[str]) -> str:
    try:
        return (urlparse(url).hostname or "") if url else ""
    except ValueError:
        return ""


def run_all(tester: ConnectionTester, cfg: OpsSettings, *, chatwoot_token: str, secret_defined: bool,
            ura: Dict[str, Any], recordings_host: str, sample_url: Optional[str]) -> List[Dict[str, Any]]:
    return [tester.report02(cfg), webhook_item(cfg, secret_defined),
            tester.recordings(cfg, recordings_host, sample_url), tester.dial(cfg), ura_item(ura),
            tester.chatwoot(cfg, chatwoot_token), tester.n8n(cfg), tester.storage(cfg)]
