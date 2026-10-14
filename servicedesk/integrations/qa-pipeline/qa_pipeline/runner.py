"""Laço do worker: consome sd:events, processa jobs vencidos, publica a outbox e entrega ao sd-ops.

Um processo = um job por vez (STT usa CPU). Para escalar, suba mais réplicas: a fila de jobs usa
SELECT ... FOR UPDATE SKIP LOCKED e o consumer group do Redis divide os eventos.
"""
from __future__ import annotations

import logging
import signal
import time

import redis

from . import db
from .clients import ChatwootClient, ClientError, SdOpsClient
from .config import Settings
from .events import CONSUMED, EventBus, parse_message
from .pipeline import Pipeline
from .storage import build_storage

log = logging.getLogger("qa_pipeline.runner")


def build_pipeline(s: Settings) -> Pipeline:
    db.init_engine(s.database_url)
    r = redis.Redis.from_url(s.redis_url) if s.redis_url else None
    bus = EventBus(r, s.events_stream, s.consumer_group, s.consumer_name, s.stream_start_id, s.dlq_stream) if r else None
    cw = None
    if s.post_notes:
        try:
            cw = ChatwootClient(s.chatwoot_url, s.chatwoot_api_token, s.chatwoot_account_id)
        except ClientError as exc:
            log.warning("notas no Chatwoot desligadas: %s", exc)
    sd = SdOpsClient(s.sd_ops_url, s.sd_ops_token) if s.sd_ops_url else None
    return Pipeline(s, storage=build_storage(s), bus=bus, chatwoot=cw, sdops=sd)


def consume_once(pipe: Pipeline, block_ms: int = 2000) -> int:
    bus = pipe.bus
    n = 0
    for msg_id, fields in bus.read(count=20, block_ms=block_ms):
        ev = parse_message(fields)
        if ev is None:
            bus.dead_letter(msg_id, fields, "envelope inválido")
            continue
        if ev["type"] not in CONSUMED:
            bus.ack(msg_id)  # eventos de outros domínios (inclusive os nossos)
            continue
        sid = msg_id.decode() if isinstance(msg_id, bytes) else str(msg_id)
        try:
            res = pipe.handle_event(ev, sid)
            log.info("evento %s -> %s", ev["type"], res, extra={"event_type": ev["type"],
                                                                 "correlation_id": ev.get("correlation_id")})
            bus.ack(msg_id)
            n += 1
        except Exception as exc:  # erro de banco etc.: fica pendente e é reentregue; após 5 vezes, DLQ
            info = bus.r.xpending_range(bus.stream, bus.group, min=msg_id, max=msg_id, count=1)
            deliveries = info[0]["times_delivered"] if info else 1
            log.exception("falha ao aplicar evento (entrega %s)", deliveries)
            if deliveries >= 5:
                bus.dead_letter(msg_id, fields, f"{type(exc).__name__}: {exc}")
            break
    return n


def run_worker(s: Settings) -> None:
    if not s.enabled:
        log.warning("QA_ENABLED=false: worker dormente (não consome eventos nem processa jobs)")
        while True:
            time.sleep(60)
    s.check_ai_policy()
    pipe = build_pipeline(s)
    pipe.bus.ensure_group()
    stop = {"flag": False}
    signal.signal(signal.SIGTERM, lambda *_: stop.update(flag=True))
    signal.signal(signal.SIGINT, lambda *_: stop.update(flag=True))
    last_maint = 0.0
    log.info("worker iniciado", extra={"stage": "start"})
    while not stop["flag"]:
        try:
            consume_once(pipe, block_ms=int(s.worker_poll_s * 1000))
            if time.time() - last_maint > 60:
                pipe.recover_stale()
                pipe.post_notes()
                last_maint = time.time()
            pipe.run_due(max_jobs=1)
            pipe.deliver_sdops()
        except redis.RedisError:
            log.exception("Redis indisponível; nova tentativa em 5 s")
            time.sleep(5)
        except Exception:
            log.exception("erro no laço do worker; nova tentativa em 5 s")
            time.sleep(5)
    log.info("worker encerrado", extra={"stage": "stop"})
