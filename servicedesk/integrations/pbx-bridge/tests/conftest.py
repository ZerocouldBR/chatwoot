import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pbx_bridge.config import Settings  # noqa: E402
from pbx_bridge.processor import Processor  # noqa: E402
from pbx_bridge.store import Store  # noqa: E402
from tests.fakes import FakeCW  # noqa: E402

SECRET = "s" * 40


def report02_row(**kw):
    """Linha FICTÍCIA no formato do Report02 da 55PBX."""
    row = {
        "call_id": "1767385476.86238", "ws_ticket_id": "", "name": "Ana Teste", "call_disconnection": "operator",
        "call_time_total_duration": "00:01:58", "call_time_waiting": "00:00:15", "call_time_spoken": "00:01:43",
        "call_url_audio": "https://vsa19.55pbx.com/webphone/webphone-0000/2026/01/02/audio-teste.WAV",
        "branch_number_agent": "5005", "call_number": "999990001", "call_area_code": "11", "wg_country_code": "55",
        "wf_states": "SP", "call_date": "02/01/2026", "queue_name": "0000-FILA_SUPORTE_1", "type_call": "receptivo",
        "call_number_input": "1130000000", "call_document": "", "call_order": "undefined", "way_ura": "Opcao - 2",
        "call_time_URA": "00:00:10", "wl_time_attended": "2026-01-02T20:24:51.000Z", "call_id_origin": "",
        "wb_call_hour": "17:24:36", "week_day": "sexta", "wt_agents_called": "1", "wu_call_cost": "0",
    }
    row.update(kw)
    return row


class FakeAudio:
    def __init__(self, fail=None):
        self.calls = 0
        self.fail = fail  # lista de exceções a levantar nas primeiras chamadas

    def __call__(self, url, allowed, max_mb, ffmpeg, bitrate, headers):
        self.calls += 1
        if self.fail:
            raise self.fail.pop(0)
        return b"ID3fake-mp3", 123456


@pytest.fixture
def settings(tmp_path):
    s = Settings(enabled=True, chatwoot_url="http://cw.test", chatwoot_api_token="t", chatwoot_account_id=1,
                 pbx_inbox_id=7, integration_user_id=99, webhook_secret=SECRET, db_path=str(tmp_path / "b.sqlite3"),
                 audio_allowed_hosts=["*.55pbx.com"], trigger_close_teams=["Novos Negócios"], trigger_close_types=["ativo"])
    s2 = Settings.from_env()
    s.queue_team_map = s2.queue_team_map
    s.team_area_map = s2.team_area_map
    s.trigger_close_attrs = s2.trigger_close_attrs
    s.branch_agent_map = {"5005": "ana.teste@exemplo.test", "5010": "bruno.ficticio@exemplo.test"}
    return s


@pytest.fixture
def env(settings):
    store = Store(settings.db_path)
    cw = FakeCW()
    audio = FakeAudio()
    proc = Processor(settings, store, cw, audio_fetcher=audio)
    return settings, store, cw, proc, audio
