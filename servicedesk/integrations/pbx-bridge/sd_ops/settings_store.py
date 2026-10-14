"""Configuração da integração 55PBX feita pelo painel do Chatwoot (Configurações > Telefonia 55PBX).

Fonte da verdade por tenant: ops.tenant_settings. Precedência de cada campo: valor da tela > variável de ambiente
(compatibilidade com o .env de antes) > padrão do código. O ambiente continua obrigatório só para a infraestrutura
(banco, Redis, chave do cofre, tokens de serviço).

- Segredos ficam SÓ cifrados (Fernet, chave SDOPS_SETTINGS_KEY; várias chaves separadas por vírgula = rotação, a
  1ª cifra). Sem a chave, segredos não podem ser gravados (erro claro) e a tela continua servindo os não secretos.
- Recarga sem reiniciar: cache por tenant com TTL curto (SDOPS_SETTINGS_TTL_S, 15 s) e invalidação imediata na
  gravação. `effective()` recalcula a mesclagem a cada chamada sobre o OpsSettings atual (barato).
- A API devolve segredos mascarados: definido (bool), últimos 4 caracteres (só com 12+) e a origem
  (panel | env | none). Nenhum segredo vai para log, auditoria ou resposta.

Ver docs/INTEGRACAO-55PBX.md, "Configuração pelo painel (admin)".
"""
from __future__ import annotations

import dataclasses
import ipaddress
import logging
import os
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import sqlalchemy as sa

from . import models as m
from .config import OpsSettings

log = logging.getLogger("sd_ops.settings")

WEBHOOK_PATH = "/integracoes/55pbx/webhook/"
URA_DEFAULT_HEADER = "X-SD-URA-Token"


class SettingsError(Exception):
    def __init__(self, code: str, message: str, http: int = 422, extra: Optional[dict] = None):
        super().__init__(message)
        self.code, self.message, self.http, self.extra = code, message, http, extra or {}


@dataclass(frozen=True)
class Field:
    key: str                  # nome no painel / JSON da API
    section: str              # status | api | webhook | recordings | dial | ura | maps | n8n
    kind: str                 # bool | int | float | str | url | enum | list | map | secret
    target: str               # bridge.<attr> | ops.<attr> | panel.<nome> (só existe no painel)
    env: str = ""             # variável de ambiente equivalente (compatibilidade)
    choices: Tuple[str, ...] = ()
    lo: Optional[float] = None
    hi: Optional[float] = None
    default: Any = None       # padrão dos campos panel.* (os demais vêm do OpsSettings)

    @property
    def secret(self) -> bool:
        return self.kind == "secret"


FIELDS: List[Field] = [
    # status / ativação
    Field("enabled", "status", "bool", "bridge.enabled", "ENABLED"),
    Field("chatwoot_api_token", "status", "secret", "bridge.chatwoot_api_token", "CHATWOOT_API_TOKEN"),
    # credenciais da API (Webservice / Report02)
    Field("pbx_api_key", "api", "secret", "bridge.pbx_api_key", "PBX_API_KEY"),
    Field("pbx_api_key_header", "api", "str", "bridge.pbx_api_key_header", "PBX_API_KEY_HEADER"),
    Field("pbx_api_url", "api", "url", "bridge.pbx_api_url", "PBX_API_URL"),
    Field("pbx_tz_offset", "api", "int", "bridge.tz_offset_hours", "PBX_TZ_OFFSET", lo=-12, hi=14),
    Field("poll_interval_min", "api", "int", "bridge.poll_interval_min", "POLL_INTERVAL_MIN", lo=1, hi=1440),
    Field("poll_lookback_min", "api", "int", "bridge.poll_lookback_min", "POLL_LOOKBACK_MIN", lo=10, hi=10080),
    # webhook "Tempo real por URL"
    Field("public_base_url", "webhook", "url", "ops.public_url", "SDOPS_PUBLIC_URL"),
    Field("webhook_secret", "webhook", "secret", "bridge.webhook_secret", "WEBHOOK_SECRET"),
    Field("webhook_token", "webhook", "secret", "panel.webhook_token", "integration_accounts.webhook_token_ref"),
    Field("allowed_ips", "webhook", "list", "bridge.allowed_ips", "ALLOWED_IPS"),
    Field("chatwoot_webhook_hmac_secret", "webhook", "secret", "bridge.chatwoot_webhook_hmac_secret",
          "CHATWOOT_WEBHOOK_HMAC_SECRET"),
    # gravações
    Field("download_recordings", "recordings", "bool", "bridge.download_recordings", "DOWNLOAD_RECORDINGS"),
    Field("recordings_host", "recordings", "str", "panel.recordings_host", "", default="vsa19.55pbx.com"),
    Field("audio_allowed_hosts", "recordings", "list", "bridge.audio_allowed_hosts", "AUDIO_ALLOWED_HOSTS"),
    Field("audio_send_api_key", "recordings", "bool", "bridge.audio_send_api_key", "AUDIO_SEND_API_KEY"),
    Field("audio_max_mb", "recordings", "int", "bridge.audio_max_mb", "AUDIO_MAX_MB", lo=1, hi=500),
    Field("audio_bitrate", "recordings", "enum", "bridge.audio_bitrate", "AUDIO_BITRATE",
          choices=("16k", "24k", "32k", "48k", "64k")),
    Field("chatwoot_attach_recording", "recordings", "bool", "ops.chatwoot_attach_recording", "CHATWOOT_ATTACH_RECORDING"),
    Field("storage_backend", "recordings", "enum", "ops.storage_backend", "SDOPS_STORAGE_BACKEND", choices=("local", "s3")),
    Field("s3_endpoint_url", "recordings", "url", "ops.s3_endpoint_url", "S3_ENDPOINT_URL"),
    Field("s3_bucket", "recordings", "str", "ops.s3_bucket", "S3_BUCKET"),
    Field("s3_region", "recordings", "str", "ops.s3_region", "S3_REGION"),
    Field("s3_access_key_id", "recordings", "secret", "ops.s3_access_key_id", "S3_ACCESS_KEY_ID"),
    Field("s3_secret_access_key", "recordings", "secret", "ops.s3_secret_access_key", "S3_SECRET_ACCESS_KEY"),
    Field("raw_retention_days", "recordings", "int", "ops.raw_retention_days", "RETENTION_DAYS", lo=1, hi=3650),
    # discagem (click-to-call)
    Field("dial_mode", "dial", "enum", "ops.dial_mode", "PBX_DIAL_MODE", choices=("disabled", "live", "mock")),
    Field("dial_url", "dial", "url", "ops.dial_url", "PBX_DIAL_URL"),
    Field("dial_client_code", "dial", "str", "ops.dial_client_code", "PBX_DIAL_CLIENT_CODE"),
    Field("dial_api_key", "dial", "secret", "ops.dial_api_key", "PBX_DIAL_API_KEY"),
    Field("dial_jwt", "dial", "secret", "ops.dial_jwt", "PBX_DIAL_JWT"),
    Field("dial_timeout_s", "dial", "float", "ops.dial_timeout_s", "PBX_DIAL_TIMEOUT_S", lo=1, hi=120),
    Field("webphone_url", "dial", "url", "ops.webphone_url", "PBX_WEBPHONE_URL"),
    # URA / Menu Dinâmico
    Field("ura_auth_type", "ura", "enum", "panel.ura_auth_type", "integration_accounts.ura_auth",
          choices=("token", "bearer", "basic"), default="token"),
    Field("ura_header", "ura", "str", "panel.ura_header", "integration_accounts.ura_auth", default=URA_DEFAULT_HEADER),
    Field("ura_token", "ura", "secret", "panel.ura_token", "integration_accounts.ura_auth"),
    Field("ura_user", "ura", "str", "panel.ura_user", "integration_accounts.ura_auth"),
    Field("ura_password", "ura", "secret", "panel.ura_password", "integration_accounts.ura_auth"),
    Field("ura_require_caller_match", "ura", "bool", "ops.ura_require_caller_match", "URA_REQUIRE_CALLER_MATCH"),
    Field("ura_rate_limit_per_min", "ura", "int", "ops.ura_rate_limit_per_min", "URA_RATE_LIMIT_PER_MIN", lo=1, hi=600),
    # mapas (ramal -> agente fica em ops.agent_phone_mappings)
    Field("queue_team_map", "maps", "map", "bridge.queue_team_map", "QUEUE_TEAM_MAP"),
    Field("branch_team_map", "maps", "map", "bridge.branch_team_map", "BRANCH_TEAM_MAP"),
    Field("team_area_map", "maps", "map", "bridge.team_area_map", "TEAM_AREA_MAP"),
    Field("default_team", "maps", "str", "bridge.default_team", "DEFAULT_TEAM"),
    Field("agent_match_by_name", "maps", "bool", "bridge.agent_match_by_name", "AGENT_MATCH_BY_NAME"),
    # n8n (ponte de eventos, WEBHOOK_CONTRACTS.md §8.3)
    Field("n8n_base_url", "n8n", "url", "panel.n8n_base_url", ""),
    Field("n8n_hmac_secret", "n8n", "secret", "panel.n8n_hmac_secret", "automation_routes.secret_ref"),
    Field("n8n_webhook_token", "n8n", "secret", "panel.n8n_webhook_token", "automation_routes.token_ref"),
]
BY_KEY: Dict[str, Field] = {f.key: f for f in FIELDS}
SECTIONS = ("status", "api", "webhook", "recordings", "dial", "ura", "maps", "n8n")

_HOST = re.compile(r"^(\*\.)?[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*$")
_HEADER = re.compile(r"^[A-Za-z0-9!#$%&'*+.^_`|~-]{1,64}$")


# ---------------------------------------------------------------------- cofre
class Vault:
    """Fernet (AES-128-CBC + HMAC-SHA256). Sem chave: `enabled` False e nenhum segredo pode ser gravado."""

    def __init__(self, keys: str):
        self.error: Optional[str] = None
        self.f = None
        ks = [k.strip() for k in (keys or "").split(",") if k.strip()]
        if not ks:
            return
        try:
            from cryptography.fernet import Fernet, MultiFernet
            self.f = MultiFernet([Fernet(k.encode()) for k in ks])
        except Exception as e:  # noqa: BLE001 - chave malformada: o serviço sobe, mas sem cofre
            self.error = "SDOPS_SETTINGS_KEY inválida (%s): use `python -m sd_ops new-settings-key`" % type(e).__name__
            log.error(self.error)

    @property
    def enabled(self) -> bool:
        return self.f is not None

    def encrypt(self, plain: str) -> str:
        if self.f is None:
            raise SettingsError("settings_key_missing", self.missing_message(), 422)
        return self.f.encrypt(plain.encode("utf-8")).decode("ascii")

    def decrypt(self, token: str) -> str:
        if self.f is None:
            raise SettingsError("settings_key_missing", self.missing_message(), 500)
        from cryptography.fernet import InvalidToken
        try:
            return self.f.decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError):
            raise SettingsError("settings_key_mismatch", "segredo gravado com outra SDOPS_SETTINGS_KEY", 500)

    def missing_message(self) -> str:
        return self.error or ("SDOPS_SETTINGS_KEY não configurada no sd-ops: os segredos não podem ser salvos pela "
                              "tela. Gere com `python -m sd_ops new-settings-key`, ponha no sd-ops.env e reinicie o "
                              "serviço uma vez.")


def new_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode("ascii")


# ---------------------------------------------------------------------- validação
def clean(f: Field, v: Any, env: str = "prod") -> Any:
    """Converte e valida um valor vindo da tela. ValueError com mensagem em pt-BR."""
    if f.kind == "bool":
        if isinstance(v, bool):
            return v
        if isinstance(v, str) and v.lower() in ("true", "false"):
            return v.lower() == "true"
        raise ValueError("deve ser verdadeiro/falso")
    if f.kind in ("int", "float"):
        try:
            n = int(v) if f.kind == "int" and not isinstance(v, bool) else float(v)
        except (TypeError, ValueError):
            raise ValueError("deve ser um número")
        if isinstance(v, bool) or (f.kind == "int" and float(v) != int(float(v))):
            raise ValueError("deve ser um número inteiro")
        if (f.lo is not None and n < f.lo) or (f.hi is not None and n > f.hi):
            raise ValueError("deve estar entre %g e %g" % (f.lo, f.hi))
        return n
    if f.kind == "enum":
        v = str(v)
        if v not in f.choices:
            raise ValueError("valor inválido (válidos: %s)" % ", ".join(f.choices))
        if f.key == "dial_mode" and v == "mock" and env != "dev":
            raise ValueError("o modo mock só existe no DEV (SDOPS_ENV=dev)")
        return v
    if f.kind == "list":
        items = v if isinstance(v, list) else [x for x in re.split(r"[,;\n]", str(v or ""))]
        out = [str(x).strip() for x in items if str(x).strip()]
        if f.key == "allowed_ips":
            for x in out:
                try:
                    ipaddress.ip_network(x, strict=False)
                except ValueError:
                    raise ValueError("IP/CIDR inválido: %s" % x)
        if f.key == "audio_allowed_hosts":
            for x in out:
                if not _HOST.match(x.lower()):
                    raise ValueError("host inválido: %s (ex. *.55pbx.com)" % x)
        return out
    if f.kind == "map":
        if not isinstance(v, dict):
            raise ValueError("deve ser um objeto {chave: valor}")
        out = {}
        for k, val in v.items():
            k, val = str(k).strip(), str(val if val is not None else "").strip()
            if not k or not val:
                raise ValueError("linhas do mapa precisam de chave e valor")
            out[k] = val
        return out
    v = "" if v is None else str(v).strip()
    if f.kind == "url":
        if v and not re.match(r"^https?://[^\s/]+", v):
            raise ValueError("URL inválida (use http:// ou https://)")
        return v.rstrip("/")
    if f.key in ("pbx_api_key_header", "ura_header") and v and not _HEADER.match(v):
        raise ValueError("nome de header inválido")
    if f.key == "recordings_host" and v and not _HOST.match(v.lower()):
        raise ValueError("host inválido (ex. vsa19.55pbx.com)")
    if len(v) > 2000:
        raise ValueError("valor longo demais")
    return v


def clean_secret(f: Field, v: str) -> str:
    v = (v or "").strip()
    if len(v) > 4000:
        raise ValueError("valor longo demais")
    if f.key == "webhook_secret" and len(v) < 32:
        raise ValueError("mínimo de 32 caracteres (use o botão Gerar novo)")
    if f.key in ("ura_token",) and len(v) < 16:
        raise ValueError("mínimo de 16 caracteres")
    return v


def mask(value: Optional[str], source: str) -> Dict[str, Any]:
    value = value or ""
    return {"defined": bool(value), "last4": value[-4:] if len(value) >= 12 else None,
            "source": source if value else "none"}


# ---------------------------------------------------------------------- mesclagem
def _panel_default(f: Field) -> Any:
    return f.default


def apply(s: OpsSettings, values: Dict[str, Any], secrets: Dict[str, str], version: int) -> OpsSettings:
    """OpsSettings efetivo = ambiente (s) + valores da tela. Não altera `s`."""
    b_over: Dict[str, Any] = {}
    o_over: Dict[str, Any] = {}
    panel: Dict[str, Any] = {}
    for src in (values, secrets):
        for k, v in (src or {}).items():
            f = BY_KEY.get(k)
            if f is None or (f.secret and src is values):
                continue
            tgt, attr = f.target.split(".", 1)
            if tgt == "bridge":
                b_over[attr] = v
            elif tgt == "ops":
                o_over[attr] = v
            else:
                panel[attr] = v
    if "pbx_api_url" in b_over:
        b_over["pbx_api_url"] = (b_over["pbx_api_url"] or s.bridge.pbx_api_url).rstrip("/")
    b = dataclasses.replace(s.bridge, **b_over) if b_over else s.bridge
    return dataclasses.replace(s, bridge=b, panel=dict(s.panel or {}, **panel), settings_version=version, **o_over)


def current_value(eff: OpsSettings, f: Field) -> Any:
    tgt, attr = f.target.split(".", 1)
    if tgt == "bridge":
        return getattr(eff.bridge, attr)
    if tgt == "ops":
        return getattr(eff, attr)
    return (eff.panel or {}).get(attr, _panel_default(f))


# ---------------------------------------------------------------------- provider
class SettingsProvider:
    def __init__(self, s: OpsSettings, engine):
        self.s, self.engine = s, engine
        self.vault = Vault(s.settings_key)
        self._rows: Dict[str, Tuple[float, Optional[Dict[str, Any]]]] = {}
        self._tenants: Tuple[float, List[Dict[str, Any]]] = (0.0, [])
        self.lock = threading.Lock()
        self.listeners: List[Any] = []          # chamados com o tenant_id na invalidação (ex. ChatwootSync)

    # ------------------------------------------------------------------ leitura
    def load(self, tenant_id: str, conn=None) -> Optional[Dict[str, Any]]:
        """Linha do ops.tenant_settings com os segredos já decifrados (só em memória)."""
        def _q(c):
            return c.execute(sa.select(m.tenant_settings).where(m.tenant_settings.c.tenant_id == tenant_id)).first()
        if conn is not None:
            r = _q(conn)
        else:
            with self.engine.begin() as c:
                r = _q(c)
        if r is None:
            return None
        secrets: Dict[str, str] = {}
        bad: List[str] = []
        for k, tok in (r.secrets or {}).items():
            try:
                secrets[k] = self.vault.decrypt(tok)
            except SettingsError:
                bad.append(k)
        if bad:
            log.error("tenant %s: %d segredo(s) do painel não puderam ser decifrados (SDOPS_SETTINGS_KEY); "
                      "valendo o ambiente para eles", tenant_id, len(bad))
        return {"values": dict(r.values or {}), "secrets": secrets, "version": r.version, "undecryptable": bad,
                "encrypted_keys": sorted((r.secrets or {}).keys()), "updated_at": r.updated_at,
                "updated_by": r.updated_by, "updated_by_email": r.updated_by_email}

    def row(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        now = time.monotonic()
        hit = self._rows.get(tenant_id)
        if hit is not None and now - hit[0] < max(0, self.s.settings_ttl_s):
            return hit[1]
        try:
            r = self.load(tenant_id)
        except sa.exc.SQLAlchemyError:
            if hit is not None:
                return hit[1]          # banco fora: mantém o último valor conhecido
            raise
        with self.lock:
            self._rows[tenant_id] = (now, r)
        return r

    def invalidate(self, tenant_id: Optional[str] = None) -> None:
        with self.lock:
            if tenant_id is None:
                self._rows.clear()
            else:
                self._rows.pop(tenant_id, None)
            self._tenants = (0.0, [])
        for fn in list(self.listeners):
            try:
                fn(tenant_id)
            except Exception:  # noqa: BLE001
                log.exception("listener de invalidação falhou")

    def effective(self, tenant_id: Optional[str] = None) -> OpsSettings:
        """Configuração em vigor para o tenant (tela > ambiente). Sem linha no painel = o próprio `s`."""
        tid = tenant_id or self.s.default_tenant
        try:
            r = self.row(tid)
        except sa.exc.SQLAlchemyError:
            return self.s
        if not r:
            return self.s
        return apply(self.s, r["values"], r["secrets"], r["version"])

    def panel_has(self, tenant_id: str, key: str) -> bool:
        try:
            r = self.row(tenant_id)
        except sa.exc.SQLAlchemyError:
            return False
        return bool(r) and (key in r["values"] or key in r["secrets"])

    def active_tenants(self) -> List[Dict[str, Any]]:
        now = time.monotonic()
        at, rows = self._tenants
        if rows and now - at < max(1, self.s.settings_ttl_s):
            return rows
        with self.engine.begin() as conn:
            rows = [dict(x._mapping) for x in conn.execute(sa.select(m.tenants.c.id, m.tenants.c.chatwoot_account_id)
                                                           .where(m.tenants.c.active.is_(True)))]
        self._tenants = (now, rows)
        return rows

    def enabled_tenants(self) -> List[str]:
        try:
            return [t["id"] for t in self.active_tenants() if self.effective(t["id"]).enabled]
        except sa.exc.SQLAlchemyError:
            return [self.s.default_tenant] if self.s.enabled else []

    def any_enabled(self) -> bool:
        return bool(self.s.enabled or self.enabled_tenants())

    # ------------------------------------------------------------------ credenciais com referência no banco
    def webhook_token(self, tenant_id: str, acc_ref: Optional[str]) -> str:
        """Header `token` da 55PBX (D11): tela > variável referenciada em integration_accounts.webhook_token_ref."""
        v = (self.effective(tenant_id).panel or {}).get("webhook_token")
        if v:
            return v
        return self.s.cred(acc_ref) if acc_ref else ""

    def ura_config(self, tenant_id: str, acc_ura: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Autenticação do Menu Dinâmico: campos da tela > integration_accounts.ura_auth (refs de ambiente)."""
        acc_ura = acc_ura or {}
        p = self.effective(tenant_id).panel or {}
        typ = p.get("ura_auth_type") or acc_ura.get("type")
        out = {"type": typ,
               "header": p.get("ura_header") or acc_ura.get("header") or URA_DEFAULT_HEADER,
               "token": p.get("ura_token") or (self.s.cred(acc_ura.get("ref")) if acc_ura.get("ref") else ""),
               "user": p.get("ura_user") or (self.s.cred(acc_ura.get("user_ref")) if acc_ura.get("user_ref") else ""),
               "password": p.get("ura_password") or (self.s.cred(acc_ura.get("pass_ref"))
                                                     if acc_ura.get("pass_ref") else "")}
        out["ready"] = bool(typ) and (bool(out["token"]) if typ in ("token", "bearer")
                                      else bool(out["user"] and out["password"]))
        return out

    def chatwoot_token(self, tenant_id: str, ref: Optional[str]) -> str:
        """Token do usuário de integração: tela > credencial referenciada (seed-tenant) > CHATWOOT_API_TOKEN."""
        if self.panel_has(tenant_id, "chatwoot_api_token"):
            return self.effective(tenant_id).bridge.chatwoot_api_token
        return (self.s.cred(ref) if ref else "") or self.s.bridge.chatwoot_api_token

    def env_source(self, f: Field) -> bool:
        return bool(f.env) and "." not in f.env and bool(os.environ.get(f.env))
