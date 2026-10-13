"""Configuração 100% por variáveis de ambiente. Nenhum segredo tem valor padrão."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

TRUE = {"1", "true", "yes", "sim", "on"}

# Padrões levantados nos 17.609 tickets 55PBX de 2026 (ver docs/INTEGRACAO-55PBX.md §2).
# Fila (normalizada) -> time. Usado para ligações RECEPTIVAS que chegam por uma fila conhecida.
DEFAULT_QUEUE_TEAM_MAP = {
    "fila_suporte_1": "Suporte",
    "checkout_n2": "Suporte",
    "tarifas_e_disponibilidade": "Treinamento",
    "fila_integracoes": "Treinamento",
    "fila_financeiro_1": "Financeiro",
    "fila_novos_negocios": "Novos Negócios",
}
# Time -> valor do campo "Área interna" (zd_area_interna, Zendesk 21587135564955), opção mais frequente por grupo.
DEFAULT_TEAM_AREA_MAP = {
    "suporte": "Suporte",
    "novos negocios": "Novos negócios",
    "treinamento": "Hospitality",
    "relacionamento hospitalidade": "Novos negócios",
    "pms": "Novos negócios",
    "diretorio de hoteis": "Novos negócios",
    "financeiro": "Financeiro",
    "cadastro": "Hospitality",
    "integracoes - n3": "Integrações",
    "integracoes": "Integrações",
    "prospeccao": "Novos negócios",
    "onboarding checkout": "Checkout",
    "analytics": "Novos negócios",
    "alteracoes cadastrais": "Novos negócios",
    "retencao": "Novos negócios",
}
# Gatilho Zendesk 22279703933339 "Encerra os tickets da 55PABX ATIVOS do grupo Novos Negócios".
DEFAULT_CLOSE_ATTRS = {
    "zd_area_interna": "Novos negócios",
    "zd_novos_negocios": "Prospecção",
    "zd_status": "Resolvido",
}


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    v = os.environ.get(name)
    return default if v is None or v == "" else v


def _bool(name: str, default: bool) -> bool:
    v = _env(name)
    return default if v is None else v.strip().lower() in TRUE


def _int(name: str, default: int) -> int:
    v = _env(name)
    return default if v is None else int(v)


def _json_map(name: str, default: Optional[dict] = None) -> Dict[str, str]:
    """Aceita JSON ({"a":"b"}) ou lista 'a=b;c=d' (separador ; ou quebra de linha)."""
    v = _env(name)
    if v is None:
        return dict(default or {})
    v = v.strip()
    if v.startswith("{"):
        return {str(k): str(val) for k, val in json.loads(v).items()}
    out = {}
    for part in v.replace("\n", ";").split(";"):
        if "=" in part:
            k, val = part.split("=", 1)
            out[k.strip()] = val.strip()
    return out


def _list(name: str, default: str = "") -> List[str]:
    v = _env(name, default) or ""
    return [x.strip() for x in v.replace(";", ",").split(",") if x.strip()]


@dataclass
class Settings:
    enabled: bool = False
    chatwoot_url: str = ""
    chatwoot_api_token: str = ""
    chatwoot_account_id: int = 0
    pbx_inbox_id: int = 0
    integration_user_id: int = 0
    pbx_api_url: str = "https://reportapi02.55pbx.com:50500/api/pbx/reports/metrics"
    pbx_api_key: str = ""
    pbx_api_key_header: str = "key"
    pbx_queue: str = "all_queues"
    pbx_number: str = "all_numbers"
    pbx_agent: str = "all_agent"
    tz_offset_hours: int = -3
    webhook_secret: str = ""
    chatwoot_webhook_hmac_secret: str = ""
    allowed_ips: List[str] = field(default_factory=list)
    trust_proxy: bool = True
    max_body_bytes: int = 262144
    poll_interval_min: int = 10
    poll_lookback_min: int = 180
    queue_team_map: Dict[str, str] = field(default_factory=dict)
    branch_agent_map: Dict[str, str] = field(default_factory=dict)
    branch_team_map: Dict[str, str] = field(default_factory=dict)
    team_area_map: Dict[str, str] = field(default_factory=dict)
    default_team: str = "Suporte"
    agent_match_by_name: bool = True
    download_recordings: bool = True
    audio_allowed_hosts: List[str] = field(default_factory=list)
    audio_send_api_key: bool = False
    audio_max_mb: int = 80
    audio_bitrate: str = "32k"
    audio_max_attempts: int = 12
    ffmpeg_bin: str = "ffmpeg"
    db_path: str = "/data/pbx-bridge.sqlite3"
    trigger_assign_on_agent_update: bool = True
    trigger_close_enabled: bool = True
    trigger_close_teams: List[str] = field(default_factory=list)
    trigger_close_types: List[str] = field(default_factory=list)
    trigger_close_attrs: Dict[str, str] = field(default_factory=dict)
    trigger_close_status: str = "resolved"
    open_status_label: str = "Aberto"
    onboarding_value: str = "Ligação"
    max_event_attempts: int = 10
    http_timeout: float = 60.0
    pbx_http_timeout: float = 180.0
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls(
            enabled=_bool("ENABLED", False),
            chatwoot_url=(_env("CHATWOOT_URL", "") or "").rstrip("/"),
            chatwoot_api_token=_env("CHATWOOT_API_TOKEN", "") or "",
            chatwoot_account_id=_int("CHATWOOT_ACCOUNT_ID", 0),
            pbx_inbox_id=_int("PBX_INBOX_ID", 0),
            integration_user_id=_int("INTEGRATION_USER_ID", 0),
            pbx_api_url=(_env("PBX_API_URL", cls.pbx_api_url) or "").rstrip("/"),
            pbx_api_key=_env("PBX_API_KEY", "") or "",
            pbx_api_key_header=_env("PBX_API_KEY_HEADER", "key") or "key",
            pbx_queue=_env("PBX_QUEUE", "all_queues"),
            pbx_number=_env("PBX_NUMBER", "all_numbers"),
            pbx_agent=_env("PBX_AGENT", "all_agent"),
            tz_offset_hours=_int("PBX_TZ_OFFSET", -3),
            webhook_secret=_env("WEBHOOK_SECRET", "") or "",
            chatwoot_webhook_hmac_secret=_env("CHATWOOT_WEBHOOK_HMAC_SECRET", "") or "",
            allowed_ips=_list("ALLOWED_IPS"),
            trust_proxy=_bool("TRUST_PROXY", True),
            max_body_bytes=_int("MAX_BODY_BYTES", 262144),
            poll_interval_min=_int("POLL_INTERVAL_MIN", 10),
            poll_lookback_min=_int("POLL_LOOKBACK_MIN", 180),
            queue_team_map=_json_map("QUEUE_TEAM_MAP", DEFAULT_QUEUE_TEAM_MAP),
            branch_agent_map=_json_map("BRANCH_AGENT_MAP", {}),
            branch_team_map=_json_map("BRANCH_TEAM_MAP", {}),
            team_area_map=_json_map("TEAM_AREA_MAP", DEFAULT_TEAM_AREA_MAP),
            default_team=_env("DEFAULT_TEAM", "Suporte"),
            agent_match_by_name=_bool("AGENT_MATCH_BY_NAME", True),
            download_recordings=_bool("DOWNLOAD_RECORDINGS", True),
            audio_allowed_hosts=_list("AUDIO_ALLOWED_HOSTS", "*.55pbx.com,*.55pbx.com.br"),
            audio_send_api_key=_bool("AUDIO_SEND_API_KEY", False),
            audio_max_mb=_int("AUDIO_MAX_MB", 80),
            audio_bitrate=_env("AUDIO_BITRATE", "32k"),
            audio_max_attempts=_int("AUDIO_MAX_ATTEMPTS", 12),
            ffmpeg_bin=_env("FFMPEG_BIN", "ffmpeg"),
            db_path=_env("DB_PATH", "/data/pbx-bridge.sqlite3"),
            trigger_assign_on_agent_update=_bool("TRIGGER_ASSIGN_ON_AGENT_UPDATE", True),
            trigger_close_enabled=_bool("TRIGGER_CLOSE_ENABLED", True),
            trigger_close_teams=_list("TRIGGER_CLOSE_TEAMS", "Novos Negócios"),
            trigger_close_types=_list("TRIGGER_CLOSE_TYPES", "ativo"),
            trigger_close_attrs=_json_map("TRIGGER_CLOSE_ATTRS", DEFAULT_CLOSE_ATTRS),
            trigger_close_status=_env("TRIGGER_CLOSE_STATUS", "resolved"),
            open_status_label=_env("OPEN_STATUS_LABEL", "Aberto"),
            onboarding_value=_env("ONBOARDING_VALUE", "Ligação"),
            max_event_attempts=_int("MAX_EVENT_ATTEMPTS", 10),
            http_timeout=float(_env("HTTP_TIMEOUT", "60")),
            pbx_http_timeout=float(_env("PBX_HTTP_TIMEOUT", "180")),
            log_level=_env("LOG_LEVEL", "INFO"),
        )
        return s

    def problems(self) -> List[str]:
        """Itens obrigatórios ausentes (sem revelar valores)."""
        p = []
        if not self.chatwoot_url:
            p.append("CHATWOOT_URL")
        if not self.chatwoot_api_token:
            p.append("CHATWOOT_API_TOKEN")
        if not self.chatwoot_account_id:
            p.append("CHATWOOT_ACCOUNT_ID")
        if not self.pbx_inbox_id:
            p.append("PBX_INBOX_ID")
        if len(self.webhook_secret) < 32:
            p.append("WEBHOOK_SECRET (mínimo 32 caracteres)")
        return p
