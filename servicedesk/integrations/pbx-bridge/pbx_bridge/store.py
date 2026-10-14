"""Estado local em SQLite (volume): fila de eventos, ligações processadas e backfill."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, List, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  received_at REAL NOT NULL,
  source TEXT NOT NULL,              -- webhook | poller | manual
  call_id TEXT,
  content_type TEXT,
  raw TEXT NOT NULL,                 -- payload bruto (fica só no volume; nunca vai para log)
  data TEXT,                         -- campos normalizados
  status TEXT NOT NULL DEFAULT 'pending',   -- pending | done | error | unparsed | ignored
  attempts INTEGER NOT NULL DEFAULT 0,
  next_attempt_at REAL NOT NULL DEFAULT 0,
  last_error TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_status ON events(status, next_attempt_at);
CREATE INDEX IF NOT EXISTS ix_events_call ON events(call_id);
CREATE TABLE IF NOT EXISTS calls (
  call_id TEXT PRIMARY KEY,
  data TEXT NOT NULL,
  conversation_id INTEGER,
  contact_id INTEGER,
  parts TEXT NOT NULL DEFAULT '[]',
  audio_status TEXT NOT NULL DEFAULT 'none',  -- none | pending | done | failed | absent | disabled
  audio_attempts INTEGER NOT NULL DEFAULT 0,
  audio_next_at REAL NOT NULL DEFAULT 0,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_calls_audio ON calls(audio_status, audio_next_at);
CREATE TABLE IF NOT EXISTS backfill (
  message_id INTEGER PRIMARY KEY,
  conversation_id INTEGER NOT NULL,
  status TEXT NOT NULL,              -- done | failed | skipped
  attempts INTEGER NOT NULL DEFAULT 0,
  note_message_id INTEGER,
  bytes_wav INTEGER,
  bytes_mp3 INTEGER,
  last_error TEXT,
  updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
"""


class Store:
    def __init__(self, path: str):
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.path = path
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None, timeout=30)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    # ---------------------------------------------------------- events
    def add_event(self, source: str, raw: str, content_type: str, call_id: Optional[str],
                  data: Optional[Dict[str, Any]], status: str = "pending") -> int:
        with self.lock:
            cur = self.db.execute(
                "INSERT INTO events(received_at, source, call_id, content_type, raw, data, status) VALUES (?,?,?,?,?,?,?)",
                (time.time(), source, call_id, content_type, raw, json.dumps(data, ensure_ascii=False) if data else None, status))
            return int(cur.lastrowid)

    def next_events(self, limit: int = 20) -> List[sqlite3.Row]:
        with self.lock:
            return list(self.db.execute(
                "SELECT * FROM events WHERE status='pending' AND next_attempt_at<=? ORDER BY id LIMIT ?",
                (time.time(), limit)))

    def event_done(self, eid: int, status: str = "done") -> None:
        with self.lock:
            self.db.execute("UPDATE events SET status=?, last_error=NULL WHERE id=?", (status, eid))

    def event_failed(self, eid: int, error: str, max_attempts: int) -> None:
        with self.lock:
            row = self.db.execute("SELECT attempts FROM events WHERE id=?", (eid,)).fetchone()
            n = (row["attempts"] if row else 0) + 1
            delay = min(30 * (2 ** (n - 1)), 3600)
            status = "error" if n >= max_attempts else "pending"
            self.db.execute("UPDATE events SET attempts=?, next_attempt_at=?, status=?, last_error=? WHERE id=?",
                            (n, time.time() + delay, status, error[:500], eid))

    def counts(self) -> Dict[str, int]:
        with self.lock:
            out = {"events_" + r[0]: r[1] for r in self.db.execute("SELECT status, count(*) FROM events GROUP BY status")}
            out["calls"] = self.db.execute("SELECT count(*) FROM calls").fetchone()[0]
            for r in self.db.execute("SELECT audio_status, count(*) FROM calls GROUP BY audio_status"):
                out["audio_" + r[0]] = r[1]
            return out

    def purge(self, days: int) -> int:
        """LGPD: apaga eventos já tratados (payload bruto) mais antigos que N dias."""
        if days <= 0:
            return 0
        with self.lock:
            cur = self.db.execute("DELETE FROM events WHERE status IN ('done','ignored','unparsed','error') AND received_at < ?",
                                  (time.time() - days * 86400,))
            return cur.rowcount

    # ---------------------------------------------------------- calls
    def get_call(self, call_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            r = self.db.execute("SELECT * FROM calls WHERE call_id=?", (call_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["data"] = json.loads(d["data"])
        d["parts"] = set(json.loads(d["parts"]))
        return d

    def save_call(self, call: Dict[str, Any]) -> None:
        now = time.time()
        with self.lock:
            self.db.execute(
                """INSERT INTO calls(call_id, data, conversation_id, contact_id, parts, audio_status, audio_attempts,
                   audio_next_at, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(call_id) DO UPDATE SET data=excluded.data, conversation_id=excluded.conversation_id,
                   contact_id=excluded.contact_id, parts=excluded.parts, audio_status=excluded.audio_status,
                   audio_attempts=excluded.audio_attempts, audio_next_at=excluded.audio_next_at, updated_at=excluded.updated_at""",
                (call["call_id"], json.dumps(call["data"], ensure_ascii=False), call.get("conversation_id"),
                 call.get("contact_id"), json.dumps(sorted(call.get("parts", set()))), call.get("audio_status", "none"),
                 call.get("audio_attempts", 0), call.get("audio_next_at", 0), call.get("created_at", now), now))

    def is_complete(self, call_id: str) -> bool:
        c = self.get_call(call_id)
        return bool(c and "atualizacao" in c["parts"] and c["audio_status"] not in ("pending",))

    def audio_due(self, limit: int = 10) -> List[str]:
        with self.lock:
            return [r[0] for r in self.db.execute(
                "SELECT call_id FROM calls WHERE audio_status='pending' AND audio_next_at<=? ORDER BY audio_next_at LIMIT ?",
                (time.time(), limit))]

    # ---------------------------------------------------------- backfill
    def backfill_get(self, message_id: int) -> Optional[sqlite3.Row]:
        with self.lock:
            return self.db.execute("SELECT * FROM backfill WHERE message_id=?", (message_id,)).fetchone()

    def backfill_set(self, message_id: int, conversation_id: int, status: str, **kw: Any) -> None:
        prev = self.backfill_get(message_id)
        attempts = (prev["attempts"] if prev else 0) + (1 if status == "failed" else 0)
        with self.lock:
            self.db.execute(
                """INSERT INTO backfill(message_id, conversation_id, status, attempts, note_message_id, bytes_wav, bytes_mp3,
                   last_error, updated_at) VALUES (?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(message_id) DO UPDATE SET status=excluded.status, attempts=excluded.attempts,
                   note_message_id=excluded.note_message_id, bytes_wav=excluded.bytes_wav, bytes_mp3=excluded.bytes_mp3,
                   last_error=excluded.last_error, updated_at=excluded.updated_at""",
                (message_id, conversation_id, status, attempts, kw.get("note_message_id"), kw.get("bytes_wav"),
                 kw.get("bytes_mp3"), (kw.get("error") or "")[:500] or None, time.time()))

    # ---------------------------------------------------------- kv
    def kv_get(self, k: str) -> Optional[str]:
        with self.lock:
            r = self.db.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
            return r[0] if r else None

    def kv_set(self, k: str, v: str) -> None:
        with self.lock:
            self.db.execute("INSERT INTO kv(k,v) VALUES (?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))
