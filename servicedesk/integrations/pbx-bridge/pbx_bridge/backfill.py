"""Backfill das gravações históricas (tickets importados do Zendesk) e estimativa de volume.

A API do Chatwoot não permite anexar arquivo a uma mensagem que já existe. Por isso a gravação entra como
nota privada nova, em resposta (in_reply_to) à mensagem importada "Atualização de ligação da 55PBX" que tem a
"URL do Áudio". A chave de idempotência é o source_id "55pbx:backfill:<id da mensagem>".
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Dict, Iterable, List, Optional

import httpx

from .audio import AudioError, fetch_mp3, host_allowed
from .chatwoot import Chatwoot
from .config import Settings
from .normalize import mask
from .store import Store

log = logging.getLogger("pbx_bridge.backfill")
URL_RE = re.compile(r"https?://[^\s<>\"'\)\]|]+?\.(?:wav|mp3|gsm|ogg)\b", re.IGNORECASE)
MARK = "URL do Áudio"


def bf_source_id(message_id: int) -> str:
    return "55pbx:backfill:%d" % message_id


def find_audio_url(content: str, allowed: List[str]) -> Optional[str]:
    if not content or MARK.lower() not in content.lower():
        return None
    for u in URL_RE.findall(content):
        if host_allowed(u, allowed):
            return u
    return None


def iter_conversations(cw: Chatwoot, label: str, inbox_id: Optional[int] = None) -> Iterable[Dict[str, Any]]:
    q: List[Dict[str, Any]] = [{"attribute_key": "labels", "filter_operator": "equal_to", "values": [label],
                                "query_operator": "and" if inbox_id else None}]
    if inbox_id:
        q.append({"attribute_key": "inbox_id", "filter_operator": "equal_to", "values": [inbox_id], "query_operator": None})
    page = 1
    while True:
        r = cw.filter_conversations(q, page)
        items = r.get("payload", [])
        if not items:
            return
        for it in items:
            yield it
        page += 1


def run(s: Settings, store: Store, cw: Chatwoot, limit: int = 0, dry_run: bool = False, sleep: float = 3.0,
        label: str = "55pbx", inbox_id: Optional[int] = None, conversation_ids: Optional[List[int]] = None,
        max_attempts: int = 3, fetcher=fetch_mp3, sleeper=time.sleep) -> Dict[str, int]:
    st = {"conversas": 0, "mensagens_com_audio": 0, "ja_feitas": 0, "anexadas": 0, "falhas": 0, "puladas": 0,
          "bytes_original": 0, "bytes_mp3": 0}
    convs: Iterable[Dict[str, Any]]
    convs = ({"id": i} for i in conversation_ids) if conversation_ids else iter_conversations(cw, label, inbox_id)
    done_work = 0
    for conv in convs:
        st["conversas"] += 1
        msgs = cw.messages(conv["id"])
        existing = {m.get("source_id") for m in msgs if m.get("source_id")}
        for m in msgs:
            url = find_audio_url(m.get("content") or "", s.audio_allowed_hosts)
            if not url:
                continue
            if limit and done_work >= limit:
                return _finish(st, dry_run)
            st["mensagens_com_audio"] += 1
            prev = store.backfill_get(m["id"])
            if bf_source_id(m["id"]) in existing or (prev and prev["status"] == "done"):
                if not prev or prev["status"] != "done":
                    store.backfill_set(m["id"], conv["id"], "done")
                st["ja_feitas"] += 1
                continue
            if prev and prev["status"] in ("failed", "skipped") and prev["attempts"] >= max_attempts:
                st["puladas"] += 1
                continue
            done_work += 1
            if dry_run:
                log.info("[dry-run] conversa #%s mensagem %s: %s", conv["id"], m["id"], mask(url))
                continue
            try:
                mp3, size = fetcher(url, s.audio_allowed_hosts, s.audio_max_mb, s.ffmpeg_bin, s.audio_bitrate, None)
                note = cw.create_message(
                    conv["id"],
                    "**Gravação da ligação 55PBX** (recuperada do histórico)\n\nOriginal: %s" % url,
                    True, bf_source_id(m["id"]),
                    attachment=("ligacao-55pbx-msg-%d.mp3" % m["id"], mp3, "audio/mpeg"),
                    content_attributes={"in_reply_to": m["id"]})
                store.backfill_set(m["id"], conv["id"], "done", note_message_id=(note or {}).get("id"),
                                   bytes_wav=size, bytes_mp3=len(mp3))
                st["anexadas"] += 1
                st["bytes_original"] += size
                st["bytes_mp3"] += len(mp3)
            except AudioError as e:
                store.backfill_set(m["id"], conv["id"], "skipped" if e.permanent else "failed", error=str(e))
                st["falhas"] += 1
                log.warning("conversa #%s mensagem %s: %s", conv["id"], m["id"], mask(str(e)))
            except Exception as e:  # noqa: BLE001
                store.backfill_set(m["id"], conv["id"], "failed", error="%s: %s" % (type(e).__name__, mask(str(e))))
                st["falhas"] += 1
                log.warning("conversa #%s mensagem %s: %s", conv["id"], m["id"], type(e).__name__)
            if sleep:
                sleeper(sleep)
    return _finish(st, dry_run)


def _finish(st: Dict[str, int], dry_run: bool) -> Dict[str, int]:
    st["dry_run"] = int(dry_run)
    return st


def estimate(urls: List[str], timeout: float = 20.0, client: Optional[httpx.Client] = None) -> Dict[str, Any]:
    """HEAD (sem baixar conteúdo) numa amostra de URLs: tamanho, tipo e se exige autenticação."""
    c = client or httpx.Client(timeout=timeout, follow_redirects=False)
    res = []
    for u in urls:
        try:
            r = c.head(u)
            res.append({"status": r.status_code, "bytes": int(r.headers.get("content-length") or 0),
                        "type": r.headers.get("content-type"), "auth": r.headers.get("www-authenticate") is not None,
                        "server": r.headers.get("server"), "cache": r.headers.get("cache-control")})
        except httpx.TransportError as e:
            res.append({"status": 0, "error": type(e).__name__, "bytes": 0})
    ok = [r for r in res if r["status"] == 200 and r["bytes"]]
    total = sum(r["bytes"] for r in ok)
    return {"amostra": len(urls), "ok_200": len(ok), "status": sorted({r["status"] for r in res}),
            "media_bytes": (total / len(ok)) if ok else 0, "total_bytes_amostra": total, "itens": res}
