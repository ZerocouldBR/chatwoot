"""Configuração do sd-ops (variáveis de ambiente). Herda a configuração da pbx-bridge (pbx_bridge.config.Settings),
que continua valendo para a projeção no Chatwoot (notas no formato do Zendesk, mapas de fila/ramal/time)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from pbx_bridge.config import Settings as BridgeSettings
from pbx_bridge.config import _bool, _env, _int, _list

# call_status (55PBX) -> outcome. Só "call_attended" aparece na documentação; os demais são palpites
# configuráveis (CALL_STATUS_MAP) e precisam ser validados com tráfego real.
DEFAULT_CALL_STATUS_MAP = {
    "call_attended": "answered",
    "attended": "answered",
    "atendida": "answered",
    "answered": "answered",
    "call_not_attended": "missed",
    "not_attended": "missed",
    "no_answer": "missed",
    "noanswer": "missed",
    "nao_atendida": "missed",
    "missed": "missed",
    "abandoned": "abandoned_queue",
    "call_abandoned": "abandoned_queue",
    "abandonada": "abandoned_queue",
    "abandoned_ura": "abandoned_ura",
    "abandoned_queue": "abandoned_queue",
    "busy": "failed",
    "ocupado": "failed",
    "failed": "failed",
    "rejected": "rejected",
    "recusada": "rejected",
    "out_of_hours": "after_hours",
    "fora_expediente": "after_hours",
}

MISSED_OUTCOMES = ("missed", "abandoned_ura", "abandoned_queue", "after_hours", "dropped")


def _json(name: str, default):
    v = _env(name)
    if v is None:
        return default
    return json.loads(v)


@dataclass
class OpsSettings:
    bridge: BridgeSettings = field(default_factory=BridgeSettings)
    env: str = "prod"                       # dev | test | prod
    database_url: str = ""
    redis_url: str = ""
    stream_key: str = "sd:events"
    stream_maxlen: int = 200000
    default_tenant: str = "b2b"
    workers: bool = True
    worker_batch: int = 20
    lease_s: int = 120                      # item "processing" sem dono há mais que isso volta para a fila
    inbox_max_attempts: int = 8
    outbox_max_attempts: int = 10
    outbox_base_delay_s: int = 15
    outbox_max_delay_s: int = 3600
    breaker_threshold: int = 5
    breaker_cooldown_s: int = 60
    # telefonia
    rt_time_fields: str = "examples"         # examples: call_time=total, call_duration=falado | descriptions
    call_status_map: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_CALL_STATUS_MAP))
    callback_outcomes: List[str] = field(default_factory=lambda: list(MISSED_OUTCOMES))
    callback_due_min: int = 60
    short_abandon_s: int = 5
    sl_threshold_s: int = 20
    # gravações
    storage_backend: str = "local"
    storage_dir: str = "/data/recordings"
    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_region: str = "us-east-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    recording_initial_delay_s: int = 120
    recording_max_attempts: int = 12
    recording_min_bytes: int = 1024
    recording_max_duration_s: int = 4 * 3600
    recording_short_ratio: float = 0.5
    recording_short_retries: int = 2
    recording_url_secret: str = ""
    recording_url_ttl_s: int = 300
    chatwoot_attach_recording: bool = True
    # discagem (API "Discagem automática para ramal")
    dial_mode: str = "disabled"              # live | mock | disabled
    dial_url: str = "https://ws.55pbx.com:20500/api/webphone/dial"
    dial_client_code: str = ""
    dial_api_key: str = ""
    dial_jwt: str = ""
    dial_timeout_s: float = 20.0
    dial_pending_s: int = 45
    webphone_url: str = ""                   # webphone oficial da 55PBX (ex. https://fone.55pbx.com); vazio = desabilitado
    # CTI / sessão
    allowed_origins: List[str] = field(default_factory=list)
    session_idle_min: int = 30
    session_max_hours: int = 8
    cookie_secure: bool = True
    auth_rate_limit_per_min: int = 10
    service_tokens: Dict[str, dict] = field(default_factory=dict)
    metrics_token: str = ""
    # URA
    ura_rate_limit_per_min: int = 10
    ura_require_caller_match: bool = True
    # retenção
    raw_retention_days: int = 30
    log_json: bool = True

    @property
    def enabled(self) -> bool:
        return self.bridge.enabled

    @classmethod
    def from_env(cls) -> "OpsSettings":
        b = BridgeSettings.from_env()
        status_map = dict(DEFAULT_CALL_STATUS_MAP)
        status_map.update(_json("CALL_STATUS_MAP", {}))
        return cls(
            bridge=b,
            env=_env("SDOPS_ENV", "prod"),
            database_url=_env("SDOPS_DATABASE_URL", "") or "",
            redis_url=_env("SDOPS_REDIS_URL", "") or "",
            stream_key=_env("SDOPS_STREAM_KEY", "sd:events"),
            stream_maxlen=_int("SDOPS_STREAM_MAXLEN", 200000),
            default_tenant=_env("SDOPS_DEFAULT_TENANT", "b2b"),
            workers=_bool("SDOPS_WORKERS", True),
            worker_batch=_int("SDOPS_WORKER_BATCH", 20),
            lease_s=_int("SDOPS_LEASE_S", 120),
            inbox_max_attempts=_int("INBOX_MAX_ATTEMPTS", 8),
            outbox_max_attempts=_int("OUTBOX_MAX_ATTEMPTS", 10),
            outbox_base_delay_s=_int("OUTBOX_BASE_DELAY_S", 15),
            outbox_max_delay_s=_int("OUTBOX_MAX_DELAY_S", 3600),
            breaker_threshold=_int("BREAKER_THRESHOLD", 5),
            breaker_cooldown_s=_int("BREAKER_COOLDOWN_S", 60),
            rt_time_fields=_env("PBX_RT_TIME_FIELDS", "examples"),
            call_status_map=status_map,
            callback_outcomes=_list("CALLBACK_OUTCOMES", ",".join(MISSED_OUTCOMES)),
            callback_due_min=_int("CALLBACK_DUE_MIN", 60),
            short_abandon_s=_int("SL_SHORT_ABANDON_S", 5),
            sl_threshold_s=_int("SL_THRESHOLD_S", 20),
            storage_backend=_env("SDOPS_STORAGE_BACKEND", "local"),
            storage_dir=_env("SDOPS_STORAGE_DIR", "/data/recordings"),
            s3_endpoint_url=_env("S3_ENDPOINT_URL", "") or "",
            s3_bucket=_env("S3_BUCKET", "") or "",
            s3_region=_env("S3_REGION", "us-east-1"),
            s3_access_key_id=_env("S3_ACCESS_KEY_ID", "") or "",
            s3_secret_access_key=_env("S3_SECRET_ACCESS_KEY", "") or "",
            recording_initial_delay_s=_int("RECORDING_INITIAL_DELAY_S", 120),
            recording_max_attempts=_int("RECORDING_MAX_ATTEMPTS", 12),
            recording_min_bytes=_int("RECORDING_MIN_BYTES", 1024),
            recording_max_duration_s=_int("RECORDING_MAX_DURATION_S", 4 * 3600),
            recording_short_ratio=float(_env("RECORDING_SHORT_RATIO", "0.5")),
            recording_short_retries=_int("RECORDING_SHORT_RETRIES", 2),
            recording_url_secret=_env("RECORDING_URL_SECRET", "") or "",
            recording_url_ttl_s=_int("RECORDING_URL_TTL_S", 300),
            chatwoot_attach_recording=_bool("CHATWOOT_ATTACH_RECORDING", True),
            dial_mode=_env("PBX_DIAL_MODE", "disabled"),
            dial_url=_env("PBX_DIAL_URL", "https://ws.55pbx.com:20500/api/webphone/dial"),
            dial_client_code=_env("PBX_DIAL_CLIENT_CODE", "") or "",
            dial_api_key=_env("PBX_DIAL_API_KEY", "") or "",
            dial_jwt=_env("PBX_DIAL_JWT", "") or "",
            dial_timeout_s=float(_env("PBX_DIAL_TIMEOUT_S", "20")),
            dial_pending_s=_int("PBX_DIAL_PENDING_S", 45),
            webphone_url=_env("PBX_WEBPHONE_URL", "") or "",
            allowed_origins=_list("SDOPS_ALLOWED_ORIGINS", ""),
            session_idle_min=_int("SESSION_IDLE_MIN", 30),
            session_max_hours=_int("SESSION_MAX_HOURS", 8),
            cookie_secure=_bool("SESSION_COOKIE_SECURE", True),
            auth_rate_limit_per_min=_int("AUTH_RATE_LIMIT_PER_MIN", 10),
            service_tokens=_json("SDOPS_SERVICE_TOKENS", {}),
            metrics_token=_env("SDOPS_METRICS_TOKEN", "") or "",
            ura_rate_limit_per_min=_int("URA_RATE_LIMIT_PER_MIN", 10),
            ura_require_caller_match=_bool("URA_REQUIRE_CALLER_MATCH", True),
            raw_retention_days=_int("RETENTION_DAYS", 30),
            log_json=_bool("LOG_JSON", True),
        )

    def problems(self) -> List[str]:
        p = []
        if not self.database_url:
            p.append("SDOPS_DATABASE_URL")
        if not self.recording_url_secret or len(self.recording_url_secret) < 32:
            p.append("RECORDING_URL_SECRET (mínimo 32 caracteres)")
        if self.dial_mode == "mock" and self.env != "dev":
            p.append("PBX_DIAL_MODE=mock só é aceito com SDOPS_ENV=dev")
        return p

    def cred(self, env_var: Optional[str]) -> str:
        """Lê o valor de uma credencial pela referência (nome da variável de ambiente)."""
        if not env_var:
            return ""
        return os.environ.get(env_var, "")
