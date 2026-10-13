"""Clientes HTTP com HTTP mockado (respx) e conversão real com ffmpeg."""
import datetime as dt
import os
import shutil
import subprocess

import httpx
import pytest
import respx

from pbx_bridge.audio import AudioError, download, fetch_mp3, host_allowed, to_mp3
from pbx_bridge.chatwoot import Chatwoot, ChatwootError
from pbx_bridge.pbx_api import PbxApi, PbxError, fmt_date
from tests.conftest import report02_row

BASE = "http://cw.test/api/v1/accounts/1"
FFMPEG = os.environ.get("FFMPEG_BIN") or shutil.which("ffmpeg")


def cw():
    return Chatwoot("http://cw.test", "tok", 1, sleep=lambda s: None)


@respx.mock
def test_chatwoot_retry_get_e_token_no_header():
    route = respx.get(BASE + "/agents").mock(side_effect=[httpx.Response(502), httpx.Response(200, json=[{"id": 1}])])
    assert cw().agents() == [{"id": 1}]
    assert route.call_count == 2
    assert route.calls[0].request.headers["api_access_token"] == "tok"


@respx.mock
def test_chatwoot_post_nao_repete_sozinho():
    route = respx.post(BASE + "/conversations").mock(return_value=httpx.Response(502))
    with pytest.raises(ChatwootError):
        cw().create_conversation({"inbox_id": 1})
    assert route.call_count == 1


@respx.mock
def test_chatwoot_busca_contato_exata_e_labels_merge():
    respx.get(BASE + "/contacts/search").mock(return_value=httpx.Response(200, json={"payload": [
        {"id": 1, "phone_number": "+5511999990001999"}, {"id": 2, "phone_number": "+5511999990001"}]}))
    assert cw().find_contact_by_phone(["+5511999990001"])["id"] == 2
    respx.get(BASE + "/conversations/5/labels").mock(return_value=httpx.Response(200, json={"payload": ["vip"]}))
    post = respx.post(BASE + "/conversations/5/labels").mock(return_value=httpx.Response(200, json={}))
    assert cw().add_labels(5, ["55pbx"]) == ["55pbx", "vip"]
    assert b'"vip"' in post.calls[0].request.content


@respx.mock
def test_chatwoot_anexo_multipart():
    route = respx.post(BASE + "/conversations/5/messages").mock(return_value=httpx.Response(200, json={"id": 9}))
    cw().create_message(5, "nota", True, "55pbx:1:x", attachment=("a.mp3", b"ID3", "audio/mpeg"))
    body = route.calls[0].request.content
    assert b'name="attachments[]"; filename="a.mp3"' in body and b"audio/mpeg" in body and b"55pbx:1:x" in body


@respx.mock
def test_report02_url_header_e_retry():
    api = PbxApi("https://pbx.test/api/pbx/reports/metrics", "chave-ficticia", "key", sleep=lambda s: None)
    start = dt.datetime(2020, 5, 22, 3, 0, tzinfo=dt.timezone.utc)
    assert fmt_date(start) == "Fri May 22 2020 00:00:00 GMT -0300"
    url = api.report02_url(start, start + dt.timedelta(hours=1))
    assert url.endswith("/all_queues/all_numbers/all_agent/report_02/undefined/undefined/-3")
    assert "Fri%20May%2022%202020%2000%3A00%3A00%20GMT%20-0300" in url
    route = respx.get(url).mock(side_effect=[httpx.ConnectError("x"), httpx.Response(
        200, json={"data_report02": [report02_row()], "reportCount": 1})])
    rows = api.report02(start, start + dt.timedelta(hours=1))
    assert len(rows) == 1 and route.calls[-1].request.headers["key"] == "chave-ficticia"


@respx.mock
def test_report02_chave_recusada():
    api = PbxApi("https://pbx.test/m", "k", "x-api-key", sleep=lambda s: None)
    respx.get(url__startswith="https://pbx.test/m/").mock(return_value=httpx.Response(401))
    with pytest.raises(PbxError, match="recusou a chave"):
        api.report02(dt.datetime.now(dt.timezone.utc), dt.datetime.now(dt.timezone.utc))


def test_host_allowlist_ssrf():
    al = ["*.55pbx.com"]
    assert host_allowed("https://vsa19.55pbx.com/a.wav", al)
    assert not host_allowed("http://169.254.169.254/latest", al)
    assert not host_allowed("https://55pbx.com.evil.test/a.wav", al)
    assert not host_allowed("file:///etc/passwd", al)
    with pytest.raises(AudioError) as e:
        fetch_mp3("http://127.0.0.1/a.wav", al, 1, "ffmpeg", "32k")
    assert e.value.permanent


@respx.mock
def test_download_limites():
    respx.get("https://a.55pbx.com/404.wav").mock(return_value=httpx.Response(404))
    respx.get("https://a.55pbx.com/grande.wav").mock(return_value=httpx.Response(200, content=b"x" * 2000))
    respx.get("https://a.55pbx.com/auth.wav").mock(return_value=httpx.Response(401))
    with pytest.raises(AudioError) as e:
        download("https://a.55pbx.com/404.wav", 1000)
    assert not e.value.permanent
    with pytest.raises(AudioError) as e:
        download("https://a.55pbx.com/grande.wav", 1000)
    assert e.value.permanent
    with pytest.raises(AudioError) as e:
        download("https://a.55pbx.com/auth.wav", 1000)
    assert e.value.permanent


@pytest.mark.skipif(not FFMPEG, reason="ffmpeg ausente")
def test_conversao_mp3_mono_32k(tmp_path):
    wav = tmp_path / "t.wav"
    subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
                    "-ar", "8000", "-ac", "2", str(wav)], check=True)
    mp3 = to_mp3(wav.read_bytes(), FFMPEG, "32k")
    assert mp3[:3] == b"ID3" or mp3[:2] == b"\xff\xf3" or mp3[:2] == b"\xff\xfb"
    assert 15000 < len(mp3) < 30000  # ~5 s a 32 kbps
    with pytest.raises(AudioError):
        to_mp3(b"nao e audio", FFMPEG)
