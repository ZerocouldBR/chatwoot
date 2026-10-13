import httpx
import respx

from pbx_bridge.audio import AudioError
from pbx_bridge.backfill import estimate, find_audio_url, run
from tests.conftest import FakeAudio

URL = "https://vsa19.55pbx.com/webphone/webphone-0000/2026/01/02/audio-teste.WAV"
IMPORTADA = "Atualização de ligação da  55PBX:    Tipo de ligaçãoativoTempo falado103Tempo total de ligação118URL do Áudio" + URL


def seed(cw, n=3):
    ids = []
    for i in range(n):
        conv = cw.create_conversation({"inbox_id": 3, "contact_id": 1})
        cw.add_labels(conv["id"], ["55pbx"])
        cw.create_message(conv["id"], "Registro de ligação 55PBX: CPF ...", True, "zd:comment:%d" % i)
        cw.create_message(conv["id"], IMPORTADA.replace("teste", "t%d" % i), True, "zd:comment:x%d" % i)
        ids.append(conv["id"])
    return ids


def test_find_audio_url():
    assert find_audio_url(IMPORTADA, ["*.55pbx.com"]) == URL
    assert find_audio_url("URL do Áudio https://evil.test/a.wav", ["*.55pbx.com"]) is None
    assert find_audio_url("sem marcador " + URL, ["*.55pbx.com"]) is None


def test_dry_run_e_limite(env):
    s, store, cw, proc, audio = env
    seed(cw)
    r = run(s, store, cw, limit=2, dry_run=True, sleep=0, fetcher=audio)
    assert r["mensagens_com_audio"] == 2 and audio.calls == 0 and r["anexadas"] == 0


def test_backfill_idempotente(env):
    s, store, cw, proc, audio = env
    ids = seed(cw)
    r = run(s, store, cw, sleep=0, fetcher=audio)
    assert r["anexadas"] == 3 and r["bytes_original"] == 3 * 123456
    nota = cw.msgs[ids[0]][-1]
    assert nota["private"] and nota["attachments"] and nota["content_attributes"]["in_reply_to"] == cw.msgs[ids[0]][1]["id"]
    r2 = run(s, store, cw, sleep=0, fetcher=audio)
    assert r2["anexadas"] == 0 and r2["ja_feitas"] == 3 and audio.calls == 3
    # estado local perdido: o source_id no ServiceDesk impede duplicar
    store.db.execute("delete from backfill")
    r3 = run(s, store, cw, sleep=0, fetcher=audio)
    assert r3["anexadas"] == 0 and r3["ja_feitas"] == 3


def test_backfill_falha_e_pula_apos_tentativas(env):
    s, store, cw, proc, audio = env
    seed(cw, 1)
    f = FakeAudio(fail=[AudioError("x")] * 3)
    for _ in range(3):
        assert run(s, store, cw, sleep=0, fetcher=f)["falhas"] == 1
    assert run(s, store, cw, sleep=0, fetcher=f)["puladas"] == 1


@respx.mock
def test_estimate_head():
    respx.head("https://a.55pbx.com/1.wav").mock(return_value=httpx.Response(200, headers={"content-length": "1000"}))
    respx.head("https://a.55pbx.com/2.wav").mock(return_value=httpx.Response(401, headers={"www-authenticate": "Basic"}))
    r = estimate(["https://a.55pbx.com/1.wav", "https://a.55pbx.com/2.wav"])
    assert r["ok_200"] == 1 and r["media_bytes"] == 1000 and r["status"] == [200, 401]
