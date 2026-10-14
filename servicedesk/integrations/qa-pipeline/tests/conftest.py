"""Fixtures: Postgres de teste (servicedesk_ops_test, schema qa via Alembic), Redis falso (fakeredis),
storage local temporário, STT mock com transcrições sintéticas e LLM mock. Nenhuma IA paga."""
from __future__ import annotations

import json
import os
import subprocess
import sys

import fakeredis
import pytest
from sqlalchemy import text

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from qa_pipeline import db  # noqa: E402
from qa_pipeline.config import Settings, reset_settings  # noqa: E402
from qa_pipeline.events import EventBus  # noqa: E402
from qa_pipeline.llm import MockLlm  # noqa: E402
from qa_pipeline.pipeline import Pipeline  # noqa: E402
from qa_pipeline.storage import LocalStorage  # noqa: E402
from qa_pipeline.stt import MockStt  # noqa: E402

from .fixtures import BAD, GOOD, as_json  # noqa: E402

TEST_DB = os.environ.get("TEST_DATABASE_URL")
TABLES = ["access_log", "recording_marks", "qa_review_events", "review_tasks", "qa_criteria_scores", "qa_evaluations",
          "call_summaries", "transcription_segments", "transcriptions", "processing_jobs", "processed_events",
          "csat_responses", "outbox", "rubric_versions", "prompt_versions"]


@pytest.fixture(scope="session")
def database():
    if not TEST_DB:
        pytest.skip("TEST_DATABASE_URL não definido")
    env = {**os.environ, "DATABASE_URL": TEST_DB}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=env, check=True,
                   capture_output=True)
    db.init_engine(TEST_DB)
    return TEST_DB


@pytest.fixture()
def clean_db(database):
    with db.engine().begin() as c:
        c.execute(text("TRUNCATE " + ",".join(f"qa.{t}" for t in TABLES) + " RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture()
def settings(tmp_path, database):
    s = Settings()
    s.env = "dev"
    s.enabled = True
    s.tenant_default = "t1"
    s.database_url = database
    s.storage_local_root = str(tmp_path / "storage")
    s.stt_provider = "mock"
    s.llm_provider = "mock"
    s.max_attempts = 3
    s.audio_wait_attempts = 3
    s.retry_base_s = 0
    s.post_notes = False
    s.console_base_url = "https://helpdesk.exemplo.test/sd-console"
    os.makedirs(s.storage_local_root, exist_ok=True)
    reset_settings(s)
    return s


@pytest.fixture()
def redis_client():
    return fakeredis.FakeRedis()


@pytest.fixture()
def bus(redis_client):
    b = EventBus(redis_client, "sd:events", "qa-pipeline", "test-1", "0")
    b.ensure_group()
    return b


class AudioFactory:
    """Grava um 'áudio' (cabeçalho ID3 válido para a checagem de tipo) e a transcrição sintética do mock."""

    def __init__(self, root: str, fixtures_dir: str):
        self.root, self.fixtures_dir = root, fixtures_dir
        os.makedirs(fixtures_dir, exist_ok=True)

    def put(self, key: str, rows=None, duration=None, partial=False, write_audio=True, raw: bytes = None):
        path = os.path.join(self.root, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if write_audio:
            with open(path, "wb") as fh:
                fh.write(raw if raw is not None else b"ID3\x03\x00\x00\x00\x00\x00\x00" + os.urandom(2048))
        if rows is not None:
            with open(os.path.join(self.fixtures_dir, os.path.basename(key) + ".transcript.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(as_json(rows, duration, partial), fh, ensure_ascii=False)
        return path

    def flag(self, key: str, suffix: str):
        open(os.path.join(self.fixtures_dir, os.path.basename(key) + suffix), "w").close()


@pytest.fixture()
def audio(settings, tmp_path):
    return AudioFactory(settings.storage_local_root, str(tmp_path / "stt-fixtures"))


@pytest.fixture()
def pipeline(settings, bus, audio, clean_db):
    return Pipeline(settings, stt=MockStt(audio.fixtures_dir), llm=MockLlm(),
                    storage=LocalStorage(settings.storage_local_root), bus=bus)


def recording_event(rec="rec-1", key="recordings/t1/2026/10/rec-1.mp3", tenant="t1", **extra):
    payload = {"recording_id": rec, "call_id": f"call-{rec}", "leg_id": "leg-1", "ticket_id": f"tk-{rec}",
               "conversation_id": "101", "storage_key": key, "mime": "audio/mpeg", "duration_s": None,
               "size_bytes": 2058, "sha256": None, "expected_talk_s": None, "integrity": "ok", **extra}
    return {"type": "recording.stored", "id": f"ev-{rec}-{os.urandom(3).hex()}", "occurred_at": "2026-10-13T18:06:40Z",
            "tenant_id": tenant, "version": 1, "source": "sd-ops", "correlation_id": f"corr-{rec}", "caused_by": None,
            "subject": {"call_id": payload["call_id"], "ticket_id": payload["ticket_id"], "conversation_id": 101},
            "payload": payload}


def xadd(redis_client, env: dict) -> None:
    redis_client.xadd("sd:events", {"type": env["type"], "data": json.dumps(env)})


__all__ = ["GOOD", "BAD", "recording_event", "xadd"]
