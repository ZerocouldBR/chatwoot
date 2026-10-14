"""Pipeline de gravação até recording.stored: aguarda, baixa (só hosts permitidos, sem redirecionamento),
valida (tipo, tamanho, integridade, duração), guarda no storage privado e publica o evento.
Transcrição e QA são do A3 (consomem recording.stored)."""
from __future__ import annotations

import datetime as dt
import hashlib
import logging
import re
import struct
import subprocess
import tempfile
from typing import Any, Callable, Dict, Optional, Tuple

import sqlalchemy as sa

from pbx_bridge.audio import AudioError, download, host_allowed

from . import db
from . import models as m
from .config import OpsSettings

log = logging.getLogger("sd_ops.recordings")


class Retry(Exception):
    """O item volta para a fila depois de `delay_s` sem contar como falha da outbox."""

    def __init__(self, delay_s: float, reason: str = ""):
        super().__init__(reason)
        self.delay_s = delay_s


def detect(data: bytes) -> Optional[Tuple[str, str]]:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return "audio/wav", "wav"
    if data[:3] == b"ID3" or (len(data) > 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
        return "audio/mpeg", "mp3"
    if data[:4] == b"OggS":
        return "audio/ogg", "ogg"
    if data[:5] == b"#!AMR":
        return "audio/amr", "amr"
    return None


def wav_duration(data: bytes) -> Optional[float]:
    """Duração pelo cabeçalho RIFF (PCM, GSM/WAV49 e demais: tamanho do bloco data / byte rate)."""
    pos, byte_rate, data_size = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], struct.unpack("<I", data[pos + 4:pos + 8])[0]
        if cid == b"fmt " and size >= 12:
            byte_rate = struct.unpack("<I", data[pos + 16:pos + 20])[0]
        elif cid == b"data":
            data_size = min(size, len(data) - pos - 8)
            break
        pos += 8 + size + (size & 1)
    if byte_rate and data_size is not None:
        return round(data_size / float(byte_rate), 3)
    return None


def ffmpeg_duration(data: bytes, ffmpeg: str) -> Optional[float]:
    with tempfile.NamedTemporaryFile(prefix="sdrec-") as f:
        f.write(data)
        f.flush()
        try:
            p = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", "-i", f.name, "-f", "null", "-"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
        except (OSError, subprocess.TimeoutExpired):
            return None
    txt = p.stderr.decode(errors="replace")
    times = re.findall(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)", txt)
    if not times:
        mm = re.search(r"Duration: (\d+):(\d+):(\d+(?:\.\d+)?)", txt)
        times = [mm.groups()] if mm else []
    if not times:
        return None
    h, mi, se = times[-1]
    return round(int(h) * 3600 + int(mi) * 60 + float(se), 3)


def duration_of(data: bytes, mime: str, ffmpeg: str) -> Optional[float]:
    if mime == "audio/wav":
        d = wav_duration(data)
        if d is not None:
            return d
    return ffmpeg_duration(data, ffmpeg)


def backoff(attempt: int) -> int:
    """5, 10, 20, 40 min … até 6 h."""
    return int(min(300 * 2 ** max(0, attempt - 1), 6 * 3600))


class RecordingPipeline:
    def __init__(self, s: OpsSettings, engine, storage, downloader: Callable = download, settings=None):
        self.s, self.engine, self.storage, self.downloader = s, engine, storage, downloader
        self.settings = settings     # configuração por tenant (tela > ambiente)

    def cfg(self, tenant_id: str) -> OpsSettings:
        return self.settings.effective(tenant_id) if self.settings is not None else self.s

    def run(self, recording_id: str) -> str:
        with self.engine.begin() as conn:
            r = conn.execute(sa.select(m.call_recordings).where(m.call_recordings.c.id == recording_id)).first()
            if r is None or r.status != "pending":
                return "skip"
            rec = dict(r._mapping)
        url = rec["source_url"]
        cfg = self.cfg(rec["tenant_id"])
        if not url or not host_allowed(url, cfg.bridge.audio_allowed_hosts):
            return self._fail(rec, "host da gravação fora de AUDIO_ALLOWED_HOSTS ou URL ausente")
        b = cfg.bridge
        headers = {b.pbx_api_key_header: b.pbx_api_key} if (b.audio_send_api_key and b.pbx_api_key) else None
        try:
            data = self.downloader(url, b.audio_max_mb * 1024 * 1024, headers=headers)
        except AudioError as e:
            if e.permanent:
                return self._fail(rec, str(e))
            return self._retry(rec, str(e))
        if len(data) < cfg.recording_min_bytes:
            return self._retry(rec, "arquivo incompleto (%d bytes)" % len(data))
        kind = detect(data)
        if kind is None:
            return self._fail(rec, "tipo de arquivo não reconhecido como áudio")
        mime, ext = kind
        dur = duration_of(data, mime, b.ffmpeg_bin)
        if dur is not None and dur > cfg.recording_max_duration_s:
            return self._fail(rec, "duração acima do limite (%.0f s)" % dur)
        exp = rec.get("expected_talk_s")
        integrity = "ok"
        if dur is None:
            integrity = "unknown_duration"
        elif exp:
            if dur < exp * cfg.recording_short_ratio:
                if rec["attempts"] < cfg.recording_short_retries:
                    return self._retry(rec, "áudio mais curto que o tempo falado (%.0f s de %d s)" % (dur, exp))
                integrity = "short"
            elif abs(dur - exp) > max(10.0, 0.1 * exp):
                integrity = "duration_mismatch"
        digest = hashlib.sha256(data).hexdigest()
        when = db.utcnow()
        key = "recordings/%s/%04d/%02d/%s.%s" % (rec["tenant_id"], when.year, when.month, rec["id"], ext)
        try:
            self.storage.put(key, data, mime)
        except Exception as e:  # noqa: BLE001 - storage fora: tenta de novo
            return self._retry(rec, "storage indisponível: %s" % type(e).__name__)
        with self.engine.begin() as conn:
            r = conn.execute(m.call_recordings.update().where(m.call_recordings.c.id == rec["id"],
                                                              m.call_recordings.c.status == "pending").values(
                status="stored", storage_backend=getattr(self.storage, "backend_for", lambda _k: self.storage.backend)(key),
                storage_key=key, mime=mime,
                size_bytes=len(data), duration_s=dur, sha256=digest, integrity=integrity, stored_at=when,
                attempts=rec["attempts"] + 1, last_error=None, updated_at=when))
            if r.rowcount == 0:
                return "skip"
            call = conn.execute(sa.select(m.calls).where(m.calls.c.id == rec["call_id"])).first()
            if call is not None and call.state == "merged" and call.merged_into:
                call = conn.execute(sa.select(m.calls).where(m.calls.c.id == call.merged_into)).first()
            leg = conn.execute(sa.select(m.call_legs.c.provider_call_id).where(m.call_legs.c.id == rec["leg_id"])).scalar()
            from . import tickets
            tks = tickets.tickets_of_call(conn, call.id) if call is not None else []
            payload = {"recording_id": rec["id"], "call_id": call.id if call is not None else rec["call_id"],
                       "leg_id": rec["leg_id"], "provider_call_id": leg,
                       "ticket_id": tks[0]["id"] if tks else None,
                       "conversation_id": call.conversation_id if call is not None else None, "storage_key": key,
                       "mime": mime, "duration_s": dur, "size_bytes": len(data), "sha256": digest,
                       "expected_talk_s": exp, "integrity": integrity}
            db.publish(conn, rec["tenant_id"], "recording.stored", rec["id"], payload,
                       subject={"call_id": payload["call_id"], "provider_call_id": leg,
                                "ticket_id": payload["ticket_id"], "conversation_id": payload["conversation_id"]})
            db.audit(conn, rec["tenant_id"], "recording.stored", "recording", rec["id"],
                     {"size": len(data), "duration_s": dur, "integrity": integrity})
            db.sync_log(conn, rec["tenant_id"], "55pbx", "recording.download", "ok", "recording", rec["id"])
            if cfg.chatwoot_attach_recording and call is not None:
                db.enqueue(conn, rec["tenant_id"], "chatwoot.sync_call", "sync_call:rec:%s" % rec["id"],
                           {"call_id": call.id, "leg_id": rec["leg_id"], "recording_id": rec["id"]},
                           ordering_key="call:" + call.id)
        log.info("gravação %s armazenada (%d bytes, %s s, %s)", rec["id"], len(data), dur, integrity)
        return "stored"

    def _retry(self, rec: Dict[str, Any], reason: str) -> str:
        n = rec["attempts"] + 1
        if n >= self.s.recording_max_attempts:
            return self._fail(rec, "esgotou %d tentativas: %s" % (n, reason))
        delay = backoff(n)
        with self.engine.begin() as conn:
            conn.execute(m.call_recordings.update().where(m.call_recordings.c.id == rec["id"]).values(
                attempts=n, last_error=reason[:500], next_attempt_at=db.utcnow() + dt.timedelta(seconds=delay),
                updated_at=db.utcnow()))
            db.sync_log(conn, rec["tenant_id"], "55pbx", "recording.download", "retry", "recording", rec["id"],
                        error=reason)
        log.warning("gravação %s: %s; nova tentativa em %d s (tentativa %d)", rec["id"], reason, delay, n)
        raise Retry(delay, reason)

    def _fail(self, rec: Dict[str, Any], reason: str) -> str:
        with self.engine.begin() as conn:
            r = conn.execute(m.call_recordings.update().where(m.call_recordings.c.id == rec["id"],
                                                              m.call_recordings.c.status == "pending").values(
                status="failed", attempts=rec["attempts"] + 1, last_error=reason[:500], updated_at=db.utcnow()))
            if r.rowcount:
                db.publish(conn, rec["tenant_id"], "recording.failed", rec["id"],
                           {"recording_id": rec["id"], "call_id": rec["call_id"], "reason": reason},
                           subject={"call_id": rec["call_id"]})
                db.audit(conn, rec["tenant_id"], "recording.failed", "recording", rec["id"], {"reason": reason})
                db.sync_log(conn, rec["tenant_id"], "55pbx", "recording.download", "dead", "recording", rec["id"],
                            error=reason)
        log.warning("gravação %s falhou de vez: %s", rec["id"], reason)
        return "failed"
