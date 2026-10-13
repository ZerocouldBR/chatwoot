"""Serviço HTTP (webhook 55PBX, eventos do ServiceDesk, health) + worker da fila + poller do Report02."""
from __future__ import annotations

import contextlib
import datetime as dt
import hashlib
import hmac
import ipaddress
import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.responses import JSONResponse

from . import __version__
from .chatwoot import Chatwoot
from .config import Settings
from .normalize import mask, mask_payload, normalize, parse_body
from .pbx_api import PbxApi, PbxError
from .processor import Processor
from .store import Store

log = logging.getLogger("pbx_bridge")
PREFIX = "/integracoes/55pbx"


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(level=getattr(logging, level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # httpx registra a URL completa no nível INFO (inclui busca por telefone): nunca em log.
    for noisy in ("httpx", "httpcore", "uvicorn.access"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


class Bridge:
    def __init__(self, s: Settings, store: Optional[Store] = None, cw: Optional[Chatwoot] = None,
                 pbx: Optional[PbxApi] = None, processor: Optional[Processor] = None):
        self.s = s
        self.store = store or Store(s.db_path)
        self.cw = cw or Chatwoot(s.chatwoot_url, s.chatwoot_api_token, s.chatwoot_account_id, s.http_timeout)
        self.pbx = pbx or PbxApi(s.pbx_api_url, s.pbx_api_key, s.pbx_api_key_header, s.pbx_queue, s.pbx_number,
                                 s.pbx_agent, s.tz_offset_hours, s.pbx_http_timeout)
        self.proc = processor or Processor(s, self.store, self.cw)
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.threads: List[threading.Thread] = []

    # ------------------------------------------------------------ entrada
    def ingest(self, body: bytes, content_type: str, source: str = "webhook") -> Dict[str, int]:
        records, raw_obj = parse_body(body, content_type)
        raw_txt = body.decode("utf-8", errors="replace")
        queued = unparsed = 0
        if not records:
            self.store.add_event(source, raw_txt, content_type, None, None, status="unparsed")
            log.warning("payload %s não reconhecido (guardado para conferência): %s", source, mask(raw_txt[:500]))
            return {"queued": 0, "unparsed": 1}
        for rec in records:
            data = normalize(rec)
            if data.get("call_id"):
                self.store.add_event(source, json.dumps(rec, ensure_ascii=False, default=str), content_type,
                                     data["call_id"], data)
                queued += 1
            else:
                self.store.add_event(source, json.dumps(rec, ensure_ascii=False, default=str), content_type, None,
                                     data, status="unparsed")
                unparsed += 1
                log.warning("registro %s sem call_id (o poller reconcilia): %s", source, mask_payload(rec, 500))
        if queued:
            log.info("%s: %d registro(s) na fila", source, queued)
            self.wake.set()
        return {"queued": queued, "unparsed": unparsed}

    # ------------------------------------------------------------ worker
    def work_once(self) -> int:
        n = 0
        for ev in self.store.next_events():
            data = json.loads(ev["data"]) if ev["data"] else {}
            try:
                self.proc.handle(data)
                self.store.event_done(ev["id"])
            except Exception as e:  # noqa: BLE001 - qualquer falha volta para a fila com backoff
                self.store.event_failed(ev["id"], "%s: %s" % (type(e).__name__, mask(str(e))), self.s.max_event_attempts)
                log.warning("evento %s (ligação %s) falhou: %s: %s", ev["id"], ev["call_id"], type(e).__name__, mask(str(e))[:300])
            n += 1
        for call_id in self.store.audio_due():
            try:
                self.proc.retry_audio(call_id)
            except Exception as e:  # noqa: BLE001
                log.warning("nova tentativa de gravação da ligação %s falhou: %s", call_id, type(e).__name__)
        return n

    def poll_once(self, now: Optional[dt.datetime] = None) -> Dict[str, int]:
        if not self.s.pbx_api_key:
            return {"skipped": 1}
        now = now or dt.datetime.now(dt.timezone.utc)
        start = now - dt.timedelta(minutes=self.s.poll_lookback_min)
        try:
            rows = self.pbx.report02(start, now)
        except PbxError as e:
            self.store.kv_set("last_poll_error", "%s %s" % (now.isoformat(timespec="seconds"), mask(str(e))[:200]))
            log.warning("poller: Report02 falhou: %s", mask(str(e)))
            return {"error": 1}
        new = 0
        for row in rows:
            data = normalize(row)
            cid = data.get("call_id")
            if not cid or self.store.is_complete(cid):
                continue
            c = self.store.get_call(cid)
            if c and c["data"].get("_poller_sig") == json.dumps(data, sort_keys=True):
                continue  # nada novo desde a última passada
            data["_poller_sig"] = json.dumps({k: v for k, v in data.items()}, sort_keys=True)
            self.store.add_event("poller", json.dumps(row, ensure_ascii=False, default=str), "application/json", cid, data)
            new += 1
        self.store.kv_set("last_poll_ok_at", now.isoformat(timespec="seconds"))
        self.store.kv_set("last_poll_rows", str(len(rows)))
        if new:
            log.info("poller: %d de %d ligação(ões) do Report02 para processar", new, len(rows))
            self.wake.set()
        return {"rows": len(rows), "queued": new}

    # ------------------------------------------------------------ threads
    def _worker_loop(self) -> None:
        while not self.stop.is_set():
            try:
                self.work_once()
            except Exception:  # noqa: BLE001
                log.exception("worker: erro inesperado")
            self.wake.wait(5)
            self.wake.clear()

    def _poller_loop(self) -> None:
        if not self.s.pbx_api_key:
            log.warning("poller desligado: PBX_API_KEY não configurada")
            return
        while not self.stop.is_set():
            try:
                self.poll_once()
            except Exception:  # noqa: BLE001
                log.exception("poller: erro inesperado")
            self.stop.wait(max(1, self.s.poll_interval_min) * 60)

    def start(self) -> None:
        for fn in (self._worker_loop, self._poller_loop):
            t = threading.Thread(target=fn, daemon=True, name=fn.__name__)
            t.start()
            self.threads.append(t)

    def shutdown(self) -> None:
        self.stop.set()
        self.wake.set()


# ================================================================ HTTP
def client_ip(request: Request, trust_proxy: bool) -> str:
    if trust_proxy:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            return xff.split(",")[-1].strip()  # último salto = adicionado pelo Traefik
    return request.client.host if request.client else ""


def ip_allowed(ip: str, allowed: List[str]) -> bool:
    if not allowed:
        return True
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for a in allowed:
        try:
            if addr in ipaddress.ip_network(a, strict=False):
                return True
        except ValueError:
            continue
    return False


async def read_limited(request: Request, limit: int) -> Optional[bytes]:
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > limit:
        return None
    buf = bytearray()
    async for chunk in request.stream():
        buf.extend(chunk)
        if len(buf) > limit:
            return None
    return bytes(buf)


def verify_chatwoot_signature(secret: str, body: bytes, ts: str, sig: str, now: Optional[float] = None) -> bool:
    if not ts or not sig or not ts.isdigit():
        return False
    if abs((now or time.time()) - int(ts)) > 300:
        return False
    exp = "sha256=" + hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(exp, sig)


def create_app(s: Optional[Settings] = None, bridge: Optional[Bridge] = None, start_threads: bool = True) -> FastAPI:
    s = s or Settings.from_env()
    setup_logging(s.log_level)
    problems = s.problems()
    if s.enabled and problems:
        raise SystemExit("Configuração incompleta: " + ", ".join(problems))
    br = bridge if bridge is not None else (Bridge(s) if s.enabled else None)
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        log.info("pbx-bridge %s iniciado; ENABLED=%s", __version__, s.enabled)
        if br is not None and start_threads:
            br.start()
        yield
        if br is not None:
            br.shutdown()

    app = FastAPI(title="pbx-bridge", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.state.bridge = br
    app.state.settings = s

    def _secret_ok(secret: str) -> bool:
        return bool(s.webhook_secret) and hmac.compare_digest(secret.encode(), s.webhook_secret.encode())

    @app.get(PREFIX + "/health")
    def health() -> Dict[str, Any]:
        out: Dict[str, Any] = {"status": "ok", "enabled": s.enabled, "version": __version__}
        if br is not None:
            out.update(br.store.counts())
            out["last_poll_ok_at"] = br.store.kv_get("last_poll_ok_at")
            out["last_poll_error"] = br.store.kv_get("last_poll_error")
            out["poller"] = bool(s.pbx_api_key)
        return out

    async def _webhook(secret: str, request: Request) -> JSONResponse:
        if not _secret_ok(secret):
            return JSONResponse({"error": "not found"}, status_code=404)
        ip = client_ip(request, s.trust_proxy)
        if not ip_allowed(ip, s.allowed_ips):
            log.warning("webhook recusado: IP fora de ALLOWED_IPS (%s)", mask(ip))
            return JSONResponse({"error": "forbidden"}, status_code=403)
        if br is None:
            return JSONResponse({"error": "integração desativada (ENABLED=false)"}, status_code=503)
        body = await read_limited(request, s.max_body_bytes)
        if body is None:
            return JSONResponse({"error": "payload grande demais"}, status_code=413)
        res = br.ingest(body, request.headers.get("content-type", ""), "webhook")
        return JSONResponse({"ok": True, **res})

    @app.post(PREFIX + "/webhook/{secret}")
    async def webhook_post(secret: str, request: Request) -> JSONResponse:
        return await _webhook(secret, request)

    @app.put(PREFIX + "/webhook/{secret}")
    async def webhook_put(secret: str, request: Request) -> JSONResponse:
        return await _webhook(secret, request)

    @app.post(PREFIX + "/servicedesk-events/{secret}")
    async def servicedesk_events(secret: str, request: Request, tasks: BackgroundTasks) -> JSONResponse:
        """Webhook da inbox API 'Telefone (55PBX)' no ServiceDesk (gatilho de atribuição)."""
        if not _secret_ok(secret):
            return JSONResponse({"error": "not found"}, status_code=404)
        if br is None:
            return JSONResponse({"error": "integração desativada (ENABLED=false)"}, status_code=503)
        body = await read_limited(request, 1024 * 1024)
        if body is None:
            return JSONResponse({"error": "payload grande demais"}, status_code=413)
        if s.chatwoot_webhook_hmac_secret and not verify_chatwoot_signature(
                s.chatwoot_webhook_hmac_secret, body, request.headers.get("x-chatwoot-timestamp", ""),
                request.headers.get("x-chatwoot-signature", "")):
            return JSONResponse({"error": "assinatura inválida"}, status_code=401)
        try:
            payload = json.loads(body.decode("utf-8"))
        except ValueError:
            return JSONResponse({"error": "json inválido"}, status_code=400)

        def run() -> None:
            try:
                br.proc.handle_chatwoot_event(payload)
            except Exception as e:  # noqa: BLE001
                log.warning("evento do ServiceDesk falhou: %s", type(e).__name__)

        tasks.add_task(run)
        return JSONResponse({"ok": True})

    return app
