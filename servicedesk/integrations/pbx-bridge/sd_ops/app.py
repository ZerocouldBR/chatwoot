"""Aplicação sd-ops (evolução da pbx-bridge): HTTP + workers. Mantém as rotas /integracoes/55pbx/*."""
from __future__ import annotations

import contextlib
import logging
from typing import Any, Dict, Optional

import sqlalchemy as sa
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from pbx_bridge.pbx_api import PbxApi

from . import __version__, api, db, obs
from . import models as m
from .auth import Auth
from .calls import CallEngine
from .chatwoot_sync import ChatwootSync
from .config import OpsSettings
from .dial import DialAdapter
from .events import MemoryPublisher, RedisPublisher
from .recordings import RecordingPipeline
from .storage import make_storage
from .tickets import TicketError
from .worker import Worker

log = logging.getLogger("sd_ops")


class Services:
    """Monta as dependências (injetáveis nos testes)."""

    def __init__(self, s: OpsSettings, engine=None, publisher=None, storage=None, cw_factory=None, profile_fn=None,
                 dial=None, downloader=None, pbx=None):
        self.s = s
        self.engine = engine or db.make_engine(s.database_url)
        self.storage = storage or make_storage(s)
        if publisher is None:
            publisher = RedisPublisher(s.redis_url, s.stream_key, s.stream_maxlen) if s.redis_url else MemoryPublisher()
        self.publisher = publisher
        self.calls = CallEngine(s)
        self.sync = ChatwootSync(s, self.engine, self.storage, cw_factory)
        kw = {"downloader": downloader} if downloader else {}
        self.recordings = RecordingPipeline(s, self.engine, self.storage, **kw)
        b = s.bridge
        if pbx is None and b.pbx_api_key:
            pbx = PbxApi(b.pbx_api_url, b.pbx_api_key, b.pbx_api_key_header, b.pbx_queue, b.pbx_number, b.pbx_agent,
                         b.tz_offset_hours, b.pbx_http_timeout)
        self.worker = Worker(s, self.engine, self.calls, self.sync, self.recordings, self.publisher, pbx)
        self.auth = Auth(s, self.engine, profile_fn)
        self.dial = dial or DialAdapter(s)

    def health(self, full: bool = False) -> Dict[str, Any]:
        out: Dict[str, Any] = {"status": "ok", "service": "sd-ops", "version": __version__, "enabled": self.s.enabled}
        try:
            with self.engine.begin() as conn:
                def cnt(tbl, *w):
                    return conn.execute(sa.select(sa.func.count()).select_from(tbl).where(*w)).scalar()
                out["inbox_pending"] = cnt(m.webhook_inbox, m.webhook_inbox.c.status.in_(("pending", "processing")))
                out["inbox_dead"] = cnt(m.webhook_inbox, m.webhook_inbox.c.status == "dead")
                out["inbox_unparsed"] = cnt(m.webhook_inbox, m.webhook_inbox.c.status == "unparsed")
                out["outbox_pending"] = cnt(m.outbox, m.outbox.c.status.in_(("pending", "processing")))
                out["outbox_dead"] = cnt(m.outbox, m.outbox.c.status == "dead")
                out["recordings_pending"] = cnt(m.call_recordings, m.call_recordings.c.status == "pending")
                out["recordings_failed"] = cnt(m.call_recordings, m.call_recordings.c.status == "failed")
                out["calls_active"] = cnt(m.calls, m.calls.c.state == "active")
                out["last_poll_ok_at"] = db.kv_get(conn, "last_poll_ok_at:%s" % self.s.default_tenant)
                out["last_poll_error"] = db.kv_get(conn, "last_poll_error:%s" % self.s.default_tenant)
                if full:
                    out["migration"] = conn.execute(sa.text("SELECT version_num FROM ops.alembic_version")).scalar()
        except Exception as e:  # noqa: BLE001
            out["status"] = "degraded"
            out["database"] = "erro: %s" % type(e).__name__
        if full:
            try:
                self.publisher.ping()
                out["redis"] = "ok"
            except Exception as e:  # noqa: BLE001
                out["status"] = "degraded"
                out["redis"] = "erro: %s" % type(e).__name__
            try:
                out["storage"] = "ok" if self.storage.ping() else "sem escrita"
            except Exception as e:  # noqa: BLE001
                out["status"] = "degraded"
                out["storage"] = "erro: %s" % type(e).__name__
            out["breakers_open"] = [k for k, v in self.worker.breaker.open_until.items() if v > __import__("time").time()]
            out["dial"] = self.dial.available() or "disponível"
        return out


def create_app(s: Optional[OpsSettings] = None, services: Optional[Services] = None,
               start_workers: Optional[bool] = None) -> FastAPI:
    s = s or OpsSettings.from_env()
    obs.setup_logging(s.bridge.log_level, s.log_json)
    probs = s.problems()
    if probs and s.enabled:
        raise SystemExit("Configuração incompleta: " + ", ".join(probs))
    svc = services or Services(s)
    run_workers = s.enabled and s.workers if start_workers is None else start_workers

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        log.info("sd-ops %s iniciado; ENABLED=%s workers=%s dial=%s", __version__, s.enabled, run_workers,
                 svc.dial.available() or "ok")
        if run_workers:
            svc.worker.start()
        yield
        svc.worker.shutdown()

    app = FastAPI(title="sd-ops (ServiceDesk Ops)", version=__version__, lifespan=lifespan,
                  description="Telefonia 55PBX, tickets de negócio, SLA, gravações e CTI do ServiceDesk. "
                              "Contratos: docs/integrations/WEBHOOK_CONTRACTS.md §8 e CTI_AUTH.md.",
                  docs_url=None, redoc_url=None, openapi_url="/sd-ops/api/v1/openapi.json")
    app.state.services = svc
    if s.allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=s.allowed_origins, allow_credentials=True,
                           allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
                           allow_headers=["Authorization", "Content-Type", "X-SD-CSRF", "X-SD-Tenant", "Idempotency-Key",
                                          "Range", "X-Request-ID"], expose_headers=["X-Request-ID"])

    @app.middleware("http")
    async def correlation(request: Request, call_next):
        cid = request.headers.get("x-request-id") or request.headers.get("x-correlation-id") or obs.new_correlation_id()
        cid = "".join(ch for ch in cid if ch.isalnum() or ch in "-_")[:64] or obs.new_correlation_id()
        with obs.context(correlation_id=cid):
            with obs.METRICS.timer("sdops_http_request_seconds", method=request.method):
                resp = await call_next(request)
        resp.headers["X-Request-ID"] = cid
        return resp

    @app.exception_handler(api.ApiError)
    async def _api_err(_r, e: api.ApiError):
        return JSONResponse(dict({"error": e.code, "message": e.message}, **e.extra), status_code=e.http)

    @app.exception_handler(TicketError)
    async def _t_err(_r, e: TicketError):
        return JSONResponse({"error": e.code, "message": e.message}, status_code=e.http)

    @app.exception_handler(RequestValidationError)
    async def _v_err(_r, e: RequestValidationError):
        return JSONResponse({"error": "validation", "message": "requisição inválida",
                             "details": [{"loc": list(x.get("loc", [])), "msg": x.get("msg")} for x in e.errors()]},
                            status_code=422)

    @app.get("/integracoes/55pbx/health", tags=["operação"])
    def legacy_health():
        return svc.health(full=False)

    @app.get("/sd-ops/health", tags=["operação"])
    def health():
        return svc.health(full=False)

    @app.get("/sd-ops/metrics", tags=["operação"], response_class=PlainTextResponse)
    def metrics(request: Request):
        if s.metrics_token and request.headers.get("authorization", "") != "Bearer " + s.metrics_token:
            return PlainTextResponse("forbidden\n", status_code=403)
        h = svc.health(full=False)
        g = {"sdops_%s" % k: v for k, v in h.items() if isinstance(v, int) and not isinstance(v, bool)}
        return PlainTextResponse(obs.METRICS.render(g))

    app.include_router(api.build(svc))
    return app
