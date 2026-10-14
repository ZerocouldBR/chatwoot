"""Workers: inbox (webhooks persistidos -> máquina de estados), outbox (Chatwoot, gravação, stream, n8n) com
retentativa exponencial, DLQ e circuit breaker; poller/reconciliação pelo Report02; SLA; manutenção.

Itens são reservados com FOR UPDATE SKIP LOCKED + lease (locked_until): se o processo cair no meio, o item
volta para a fila quando o lease vence (recuperação após reinício).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional

import httpx
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from pbx_bridge.normalize import mask, parse_body
from pbx_bridge.pbx_api import PbxApi, PbxError

from . import db, obs, sla
from . import models as m
from .calls import CallEngine
from .config import OpsSettings
from .events import deliver, route_matches
from .normalize55 import canonicalize, fix_isodate
from .recordings import Retry

log = logging.getLogger("sd_ops.worker")
METRICS = obs.METRICS


class Breaker:
    """Circuit breaker simples por destino (Chatwoot, n8n...)."""

    def __init__(self, threshold: int, cooldown_s: int):
        self.threshold, self.cooldown = threshold, cooldown_s
        self.fails: Dict[str, int] = {}
        self.open_until: Dict[str, float] = {}

    def allow(self, target: str) -> bool:
        return time.time() >= self.open_until.get(target, 0)

    def ok(self, target: str) -> None:
        self.fails[target] = 0

    def fail(self, target: str) -> None:
        n = self.fails.get(target, 0) + 1
        self.fails[target] = n
        if n >= self.threshold:
            self.open_until[target] = time.time() + self.cooldown
            log.warning("circuit breaker ABERTO para %s por %d s", target, self.cooldown)


def accept(conn, tenant_id: Optional[str], source: str, body: bytes, content_type: str,
           headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Persiste o corpo recebido (idempotente pelo conteúdo). Usado pelo webhook e pelo poller."""
    raw = body.decode("utf-8", errors="replace")
    h = db.sha256(body)
    dedup = db.sha256("%s|%s|%s" % (source, tenant_id or "-", h))
    r = conn.execute(pg_insert(m.webhook_inbox).values(
        tenant_id=tenant_id, source=source, content_type=content_type, headers=headers or {}, raw=raw,
        body_sha256=h, dedup_key=dedup, correlation_id=obs.correlation_id()).on_conflict_do_nothing(
        index_elements=["dedup_key"]).returning(m.webhook_inbox.c.id)).first()
    if r is None:
        eid = conn.execute(sa.select(m.webhook_inbox.c.id).where(m.webhook_inbox.c.dedup_key == dedup)).scalar()
        return {"id": eid, "duplicate": True}
    return {"id": r[0], "duplicate": False}


def backoff(attempt: int, base: int, cap: int) -> int:
    return int(min(base * 2 ** max(0, attempt - 1), cap))


class Worker:
    def __init__(self, s: OpsSettings, engine, call_engine: CallEngine, sync, recordings, publisher,
                 pbx: Optional[PbxApi] = None, http: Optional[httpx.Client] = None, settings=None):
        self.s, self.engine, self.calls, self.sync, self.recs, self.pub = s, engine, call_engine, sync, recordings, publisher
        self.pbx = pbx                   # cliente injetado (testes/CLI); sem ele, um por tenant conforme a configuração
        self.settings = settings         # SettingsProvider (tela > ambiente); None = só o ambiente
        self._pbx_cache: Dict[tuple, PbxApi] = {}
        self._last_poll: Dict[str, float] = {}
        self.http = http or httpx.Client(timeout=10.0, follow_redirects=False)
        self.breaker = Breaker(s.breaker_threshold, s.breaker_cooldown_s)
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.threads: List[threading.Thread] = []

    # ================================================================== configuração por tenant
    def cfg(self, tenant_id: Optional[str]) -> OpsSettings:
        if self.settings is None or not tenant_id:
            return self.s
        return self.settings.effective(tenant_id)

    def active(self) -> bool:
        """Há algum tenant ativo (tela ou ENABLED)? Os workers sobem sempre, mas só trabalham com algum ativo:
        assim a ativação pela tela vale sem reiniciar e o serviço dormente continua parado."""
        if self.settings is None:
            return self.s.enabled
        return self.settings.any_enabled() and not self.s.force_disabled

    def pbx_for(self, tenant_id: str) -> Optional[PbxApi]:
        if self.pbx is not None:
            return self.pbx
        b = self.cfg(tenant_id).bridge
        if not b.pbx_api_key:
            return None
        k = (b.pbx_api_url, b.pbx_api_key, b.pbx_api_key_header, b.pbx_queue, b.pbx_number, b.pbx_agent,
             b.tz_offset_hours, b.pbx_http_timeout)
        api = self._pbx_cache.get(k)
        if api is None:
            if len(self._pbx_cache) > 32:
                self._pbx_cache.clear()
            api = self._pbx_cache[k] = PbxApi(*k)
        return api

    # ================================================================== inbox
    def _claim(self, table, extra_where: Optional[Callable] = None, limit: int = 20) -> List[Dict[str, Any]]:
        now = db.utcnow()
        t = table
        c = table.alias("cand")
        due = sa.or_(sa.and_(c.c.status == "pending", c.c.next_attempt_at <= now),
                     sa.and_(c.c.status == "processing", c.c.locked_until < now))
        sub = sa.select(c.c.id).where(due)
        if extra_where is not None:
            sub = sub.where(extra_where(c))
        sub = sub.order_by(c.c.id).limit(limit).with_for_update(of=c, skip_locked=True)
        with self.engine.begin() as conn:
            rows = conn.execute(t.update().where(t.c.id.in_(sub.scalar_subquery())).values(
                status="processing", locked_until=now + dt.timedelta(seconds=self.s.lease_s),
                attempts=t.c.attempts + 1).returning(t)).fetchall()
        return sorted([dict(r._mapping) for r in rows], key=lambda r: r["id"])

    def inbox_once(self, limit: Optional[int] = None) -> int:
        rows = self._claim(m.webhook_inbox, limit=limit or self.s.worker_batch)
        for row in rows:
            with obs.context(correlation_id=row.get("correlation_id") or obs.new_correlation_id(),
                             tenant=row.get("tenant_id"), inbox_id=str(row["id"])):
                t0 = time.monotonic()
                try:
                    res = self._process_inbox(row)
                    METRICS.inc("sdops_inbox_processed_total", source=row["source"], result=res.get("status", "done"))
                except Exception as e:  # noqa: BLE001 - volta para a fila com backoff; DLQ ao esgotar
                    self._inbox_failed(row, e)
                finally:
                    METRICS.observe("sdops_inbox_processing_seconds", time.monotonic() - t0, source=row["source"])
        return len(rows)

    def _process_inbox(self, row: Dict[str, Any]) -> Dict[str, Any]:
        tenant_id = row["tenant_id"] or self.s.default_tenant
        if row["source"] == "chatwoot":
            payload = json.loads(row["raw"] or "{}")
            with self.engine.begin() as conn:
                db.enqueue(conn, tenant_id, "chatwoot.event", "cwevent:%s" % row["id"], {"payload": payload},
                           ordering_key="cwconv:%s" % ((payload.get("conversation") or {}).get("id") or payload.get("id")))
                self._inbox_done(conn, row, "done", {"enqueued": 1})
            return {"status": "done"}
        records, _ = parse_body(fix_isodate(row["raw"] or "").encode("utf-8"), row.get("content_type") or "")
        results = []
        unparsed = 0
        with self.engine.begin() as conn:
            for rec in records:
                d, anomalies = canonicalize(rec, self.s.rt_time_fields)
                if not d.get("call_id"):
                    unparsed += 1
                    continue
                res = self.calls.ingest(conn, tenant_id, d, anomalies, row["source"], row["id"])
                results.append(res)
                if res.get("result") == "ok":
                    log.info("evento %s da ligação %s -> chamada %s (%s, %s)", res["kind"], d["call_id"],
                             res["call_id"], res["state"], res.get("outcome") or "-")
            status = "done" if results else "unparsed"
            self._inbox_done(conn, row, status, {"records": len(records), "unparsed": unparsed,
                                                 "results": [{k: r.get(k) for k in ("result", "kind", "call_id")}
                                                             for r in results]})
        if status == "unparsed":
            log.warning("payload %s não reconhecido (guardado em webhook_inbox #%s): %s", row["source"], row["id"],
                        mask((row["raw"] or "")[:300]))
        if results:
            self.wake.set()
        return {"status": status}

    def _inbox_done(self, conn, row, status: str, result: Dict[str, Any]) -> None:
        conn.execute(m.webhook_inbox.update().where(m.webhook_inbox.c.id == row["id"]).values(
            status=status, processed_at=db.utcnow(), locked_until=None, last_error=None, result=result))

    def _inbox_failed(self, row, e: Exception) -> None:
        n = row["attempts"]
        dead = n >= self.s.inbox_max_attempts
        delay = backoff(n, self.s.outbox_base_delay_s, self.s.outbox_max_delay_s)
        err = "%s: %s" % (type(e).__name__, mask(str(e))[:400])
        with self.engine.begin() as conn:
            conn.execute(m.webhook_inbox.update().where(m.webhook_inbox.c.id == row["id"]).values(
                status="dead" if dead else "pending", locked_until=None, last_error=err,
                next_attempt_at=db.utcnow() + dt.timedelta(seconds=delay)))
        METRICS.inc("sdops_inbox_failures_total", dead=str(dead).lower())
        (log.error if dead else log.warning)("webhook_inbox #%s falhou (%d): %s%s", row["id"], n, err,
                                             " -> DLQ" if dead else "", exc_info=dead)

    # ================================================================== outbox
    def outbox_once(self, limit: Optional[int] = None, kinds: Optional[List[str]] = None) -> int:
        def where(o):
            p = m.outbox.alias("prev")
            blocked = sa.exists().where(p.c.ordering_key == o.c.ordering_key, p.c.id < o.c.id,
                                        p.c.status.in_(("pending", "processing")))
            return sa.and_(sa.or_(o.c.ordering_key.is_(None), ~blocked),
                           o.c.kind.in_(kinds) if kinds else sa.true())
        rows = self._claim(m.outbox, where, limit or self.s.worker_batch)
        for row in rows:
            with obs.context(correlation_id=row.get("correlation_id") or obs.new_correlation_id(),
                             tenant=row["tenant_id"], outbox_id=str(row["id"]), kind=row["kind"]):
                t0 = time.monotonic()
                self._run_outbox(row)
                METRICS.observe("sdops_outbox_processing_seconds", time.monotonic() - t0, kind=row["kind"])
        return len(rows)

    def _target(self, kind: str) -> str:
        if kind.startswith("chatwoot."):
            return "chatwoot"
        if kind in ("webhook.deliver", "fanout"):
            return "automation"
        if kind == "stream":
            return "redis"
        return "55pbx"

    def _run_outbox(self, row: Dict[str, Any]) -> None:
        target = self._target(row["kind"])
        if not self.breaker.allow(target):
            self._outbox_reschedule(row, self.s.breaker_cooldown_s, "circuit breaker aberto (%s)" % target)
            return
        try:
            res = self._dispatch(row)
        except Retry as r:
            self._outbox_reschedule(row, r.delay_s, str(r))
            return
        except Exception as e:  # noqa: BLE001
            self.breaker.fail(target)
            self._outbox_failed(row, e, target)
            return
        self.breaker.ok(target)
        with self.engine.begin() as conn:
            conn.execute(m.outbox.update().where(m.outbox.c.id == row["id"]).values(
                status="done", processed_at=db.utcnow(), locked_until=None, last_error=None))
        METRICS.inc("sdops_outbox_processed_total", kind=row["kind"], result=str(res or "ok").split(":")[0])

    def _dispatch(self, row: Dict[str, Any]) -> Any:
        k, p = row["kind"], row["payload"]
        if k == "stream":
            rid = self.pub.publish(p)
            self._fanout(row, p)
            return rid
        if k == "fanout":
            # evento de outro serviço (ex. qa.completed do qa-pipeline): só para as rotas de automação
            self._fanout(row, p)
            return "fanout"
        if k == "webhook.deliver":
            return self._deliver(row)
        if k == "chatwoot.sync_call":
            return self.sync.sync_call(p)
        if k == "chatwoot.sync_ticket":
            return self.sync.sync_ticket(p)
        if k == "chatwoot.note":
            return self.sync.post_note(p)
        if k == "chatwoot.event":
            return self.sync.handle_event(row["tenant_id"], p["payload"])
        if k == "recording.fetch":
            return self.recs.run(p["recording_id"])
        raise ValueError("tipo de outbox desconhecido: %s" % k)

    def _fanout(self, row: Dict[str, Any], env: Dict[str, Any]) -> None:
        """Evento publicado no stream -> entrega às rotas de automação (n8n) que assinam o tipo."""
        with self.engine.begin() as conn:
            routes = conn.execute(sa.select(m.automation_routes).where(
                m.automation_routes.c.active.is_(True),
                sa.or_(m.automation_routes.c.tenant_id.is_(None), m.automation_routes.c.tenant_id == row["tenant_id"])
            )).fetchall()
            for r in routes:
                if not route_matches(r.event_types, env["type"]):
                    continue
                caused = env.get("caused_by") or ""
                if caused and caused == "n8n:%s" % r.name:
                    conn.execute(pg_insert(m.automation_executions).values(
                        tenant_id=row["tenant_id"], route_id=r.id, event_id=env["id"], event_type=env["type"],
                        status="skipped_loop").on_conflict_do_nothing())
                    continue
                db.enqueue(conn, row["tenant_id"], "webhook.deliver", "deliver:%s:%s" % (r.id, env["id"]),
                           {"route_id": r.id, "envelope": env}, ordering_key="route:%s" % r.id)

    def _deliver(self, row: Dict[str, Any]) -> str:
        p = row["payload"]
        with self.engine.begin() as conn:
            r = conn.execute(sa.select(m.automation_routes).where(m.automation_routes.c.id == p["route_id"])).first()
        if r is None or not r.active:
            return "skip"
        env = p["envelope"]
        # n8n: segredo HMAC, token e URL base da tela > variáveis referenciadas na rota (token_ref/secret_ref)
        panel = self.cfg(row["tenant_id"]).panel or {}
        url = r.url
        if url.startswith("/"):
            if not panel.get("n8n_base_url"):
                raise RuntimeError("rota %s com URL relativa e sem URL do n8n configurada" % r.name)
            url = panel["n8n_base_url"].rstrip("/") + url
        code = deliver(self.http, url, env, panel.get("n8n_webhook_token") or self.s.cred(r.token_ref),
                       panel.get("n8n_hmac_secret") or self.s.cred(r.secret_ref))
        ok = 200 <= code < 300
        with self.engine.begin() as conn:
            conn.execute(pg_insert(m.automation_executions).values(
                tenant_id=row["tenant_id"], route_id=r.id, event_id=env["id"], event_type=env["type"],
                status="ok" if ok else "error", attempts=row["attempts"], http_status=code).on_conflict_do_update(
                index_elements=["route_id", "event_id"],
                set_={"status": "ok" if ok else "error", "attempts": row["attempts"], "http_status": code,
                      "updated_at": db.utcnow()}))
        if not ok:
            raise RuntimeError("rota %s respondeu HTTP %d" % (r.name, code))
        return "ok"

    def _outbox_reschedule(self, row, delay: float, reason: str) -> None:
        with self.engine.begin() as conn:
            conn.execute(m.outbox.update().where(m.outbox.c.id == row["id"]).values(
                status="pending", locked_until=None, attempts=sa.func.greatest(m.outbox.c.attempts - 1, 0),
                last_error=reason[:500], next_attempt_at=db.utcnow() + dt.timedelta(seconds=delay)))

    def _outbox_failed(self, row, e: Exception, target: str) -> None:
        n = row["attempts"]
        dead = n >= self.s.outbox_max_attempts
        delay = backoff(n, self.s.outbox_base_delay_s, self.s.outbox_max_delay_s)
        err = "%s: %s" % (type(e).__name__, mask(str(e))[:400])
        with self.engine.begin() as conn:
            conn.execute(m.outbox.update().where(m.outbox.c.id == row["id"]).values(
                status="dead" if dead else "pending", locked_until=None, last_error=err,
                next_attempt_at=db.utcnow() + dt.timedelta(seconds=delay)))
            db.sync_log(conn, row["tenant_id"], target, row["kind"], "dead" if dead else "retry", "outbox",
                        str(row["id"]), error=err)
        METRICS.inc("sdops_outbox_failures_total", kind=row["kind"], dead=str(dead).lower())
        (log.error if dead else log.warning)("outbox #%s (%s) falhou na tentativa %d: %s%s", row["id"], row["kind"], n,
                                             err, " -> DLQ" if dead else " (nova tentativa em %ds)" % delay)

    # ================================================================== reconciliação (Report02)
    def reconcile(self, tenant_id: str, start: dt.datetime, end: dt.datetime, mode: str = "poll",
                  chunk_h: int = 6) -> Dict[str, Any]:
        api = self.pbx_for(tenant_id)
        if api is None or (self.pbx is not None and not self.cfg(tenant_id).bridge.pbx_api_key):
            return {"skipped": "PBX_API_KEY não configurada"}
        total = new = 0
        cur = start
        while cur < end:
            nxt = min(end, cur + dt.timedelta(hours=chunk_h))
            with self.engine.begin() as conn:
                run_id = conn.execute(m.reconciliation_runs.insert().values(
                    tenant_id=tenant_id, mode=mode, window_start=cur, window_end=nxt, status="running")
                    .returning(m.reconciliation_runs.c.id)).scalar()
            try:
                rows = api.report02(cur, nxt)
            except PbxError as e:
                with self.engine.begin() as conn:
                    conn.execute(m.reconciliation_runs.update().where(m.reconciliation_runs.c.id == run_id).values(
                        status="error", error=mask(str(e))[:500], finished_at=db.utcnow()))
                    db.kv_set(conn, "last_poll_error:%s" % tenant_id, "%s %s" % (db.iso(db.utcnow()), mask(str(e))[:200]))
                    db.sync_log(conn, tenant_id, "55pbx", "report02", "error", error=str(e))
                log.warning("reconciliação %s..%s falhou: %s", db.iso(cur), db.iso(nxt), mask(str(e)))
                return {"error": mask(str(e))[:200], "rows": total, "new": new}
            n_new = 0
            with self.engine.begin() as conn:
                for r in rows:
                    body = json.dumps(r, ensure_ascii=False, sort_keys=True, default=str).encode()
                    if not accept(conn, tenant_id, "report02", body, "application/json")["duplicate"]:
                        n_new += 1
                conn.execute(m.reconciliation_runs.update().where(m.reconciliation_runs.c.id == run_id).values(
                    status="ok", rows=len(rows), new_rows=n_new, finished_at=db.utcnow()))
                db.kv_set(conn, "last_poll_ok_at:%s" % tenant_id, db.iso(db.utcnow()))
            total += len(rows)
            new += n_new
            cur = nxt
        if new:
            self.wake.set()
        return {"rows": total, "new": new}

    def poll_targets(self) -> List[str]:
        """Tenants a consultar no Report02: o padrão (chave da tela ou PBX_API_KEY do ambiente) e os demais que
        têm chave PRÓPRIA na tela (a do ambiente é do tenant padrão). Só os ativos."""
        if self.settings is None:
            return [self.s.default_tenant] if self.s.enabled else []
        out = []
        for tid in self.settings.enabled_tenants():
            if tid == self.s.default_tenant or self.settings.panel_has(tid, "pbx_api_key"):
                out.append(tid)
        return out

    def poll_once(self, now: Optional[dt.datetime] = None, force: bool = True) -> Dict[str, Any]:
        """Uma passada do Report02 por tenant ativo (cada um com POLL_INTERVAL_MIN/LOOKBACK da sua configuração).
        Devolve o resultado do tenant padrão (compatível com a v2) e, em `tenants`, o de cada um."""
        now = now or db.utcnow()
        targets = self.poll_targets() if self.settings is not None else [self.s.default_tenant]
        if self.settings is None or (force and self.s.default_tenant not in targets and self.pbx is not None):
            targets = list(dict.fromkeys([self.s.default_tenant] + targets))
        res: Dict[str, Any] = {}
        for tid in targets:
            b = self.cfg(tid).bridge
            if not force and time.time() - self._last_poll.get(tid, 0) < max(1, b.poll_interval_min) * 60:
                continue
            self._last_poll[tid] = time.time()
            start = now - dt.timedelta(minutes=b.poll_lookback_min)
            res[tid] = self.reconcile(tid, start, now, "poll", chunk_h=24)
        out = dict(res.get(self.s.default_tenant) or {"skipped": "nenhum tenant ativo com chave"})
        out["tenants"] = res
        return out

    # ================================================================== manutenção
    def maintenance_once(self) -> Dict[str, int]:
        out = {}
        with self.engine.begin() as conn:
            out["sla_breached"] = sla.check_breaches(conn)
        with self.engine.begin() as conn:
            out["stale_calls"] = self.calls.finalize_stale(conn)
        with self.engine.begin() as conn:
            # retenção do payload bruto por tenant (tela > RETENTION_DAYS); sem tenant = padrão do ambiente
            tids = [t[0] for t in conn.execute(sa.select(m.tenants.c.id))]
            wi = m.webhook_inbox
            out["raw_purged"] = 0
            for tid in tids + [None]:
                cutoff = db.utcnow() - dt.timedelta(days=self.cfg(tid).raw_retention_days)
                out["raw_purged"] += conn.execute(wi.update().where(
                    wi.c.tenant_id.is_(None) if tid is None else wi.c.tenant_id == tid,
                    wi.c.status.in_(("done", "unparsed", "dead")), wi.c.received_at < cutoff,
                    wi.c.raw.isnot(None)).values(raw=None, raw_purged_at=db.utcnow())).rowcount
            conn.execute(m.cti_sessions.delete().where(m.cti_sessions.c.expires_at < db.utcnow() - dt.timedelta(days=1)))
            conn.execute(m.idempotency_keys.delete().where(
                m.idempotency_keys.c.created_at < db.utcnow() - dt.timedelta(hours=24)))
        return out

    def run_until_idle(self, max_loops: int = 50) -> int:
        """Processa inbox e outbox até não sobrar nada pronto (testes, CLI)."""
        total = 0
        for _ in range(max_loops):
            n = self.inbox_once(100) + self.outbox_once(100)
            total += n
            if n == 0:
                break
        return total

    # ================================================================== threads
    def _loop(self, fn: Callable[[], Any], every: float, name: str) -> None:
        while not self.stop.is_set():
            try:
                n = fn() if self.active() else 0
            except Exception:  # noqa: BLE001
                log.exception("%s: erro inesperado", name)
                n = 0
            if not n:
                self.wake.wait(every)
                self.wake.clear()

    def _periodic(self, fn: Callable[[], Any], every: float, name: str) -> None:
        while not self.stop.is_set():
            try:
                if self.active():
                    fn()
            except Exception:  # noqa: BLE001
                log.exception("%s: erro inesperado", name)
            self.stop.wait(every)

    def start(self) -> None:
        jobs = [(self._loop, (self.inbox_once, 2, "inbox")),
                (self._loop, (self.outbox_once, 2, "outbox")),
                (self._periodic, (self.maintenance_once, 60, "manutenção"))]
        if self.settings is not None:
            # poller sempre registrado: cada tenant respeita o próprio intervalo (configurável pela tela)
            jobs.append((self._periodic, (lambda: self.poll_once(force=False), 60, "poller")))
        elif self.pbx is not None and self.s.bridge.pbx_api_key:
            jobs.append((self._periodic, (self.poll_once, max(1, self.s.bridge.poll_interval_min) * 60, "poller")))
        for fn, args in jobs:
            t = threading.Thread(target=fn, args=args, daemon=True, name="sdops-" + args[2])
            t.start()
            self.threads.append(t)

    def shutdown(self) -> None:
        self.stop.set()
        self.wake.set()
