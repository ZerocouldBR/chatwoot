"""Unitários (sem banco): normalização do manual 55PBX, horário comercial, protocolo, storage, gravação."""
from __future__ import annotations

import datetime as dt
import json

from pbx_bridge.normalize import parse_body
from sd_ops.normalize55 import canonicalize, fix_isodate, mask_e164, phase
from sd_ops.recordings import backoff, detect, wav_duration
from sd_ops.sla import BusinessHours
from sd_ops.storage import LocalStorage, parse_range
from sd_ops.tickets import luhn_digit, luhn_ok
from tests.sdops.conftest import wav

UTC = dt.timezone.utc

# Exemplo LITERAL do manual integration_endpoint.pdf v2.0 (p. 5), com ISODate e vírgula final.
MANUAL = '''{
 "central_id" : "1000",
 "branch_mask" : 5000,
 "call_id" : "1479477009.5199",
 "call_date" : ISODate("2012-05-01 12:30:00"),
 "call_terminal" : "",
 "call_type" : "active",
 "call_number" : "987654321",
 "call_area_code" : "11",
 "call_country_code" : "55",
 "call_document" : "",
 "call_order" : "",
 "call_ura" : "",
 "call_queue" : "",
 "call_status" : "",
 "call_disconnection" : "externo",
 "call_time" : 11,
 "call_time_waiting" : 8,
 "call_duration" : 3,
 "call_tax_type" : "VC2",
 "call_tax" : 0.58,
 "call_cost" : 0.58,
 "call_balance" : 9999759.12,
 "call_url_audio" : "https://sip1.55pbx.com/webphone-1000/2016/11/18/audio-2016-11-18_11-50-09-100001-11987654321-1479477009.5199.wav",
 "call_audio_file" : "audio-2016-11-18_11-50-09-100001-119876543211479477009.5199.wav",
 "call_transfer_id" : "1479477009.5198"
}'''


def test_manual_exemplo_isodate_e_campos():
    recs, _ = parse_body(fix_isodate(MANUAL).encode(), "application/json")
    assert len(recs) == 1
    d, anomalies = canonicalize(recs[0])
    assert d["call_id"] == "1479477009.5199" and d["central_id"] == "1000" and d["branch"] == "5000"
    assert d["type"] == "ativo" and d["transfer_id"] == "1479477009.5198" and d["cost"] == 0.58
    # leitura pelos exemplos: call_time (11) = total, call_duration (3) = falado (11 = 3 + 8 de espera)
    assert d["spoken"] == 3 and d["total_duration"] == 11 and d["waiting"] == 8 and anomalies == []
    assert d["audio_url"].startswith("https://sip1.55pbx.com/") and "balance" not in json.dumps(d)
    assert phase(d, "webhook") == "transfer"


def test_readme_exemplo_receptive_status():
    rec = {"central_id": "15", "branch_mask": "5000", "call_id": "1601659421", "call_date": "Invalid Date",
           "call_type": "receptive", "call_number": "+5511987468223", "call_area_code": "11", "call_country_code": 55,
           "call_queue": "testePedro", "call_status": "call_attended", "call_disconnection": "interno",
           "call_time": "44", "call_duration": "9", "call_time_waiting": "7", "call_total_time": "44",
           "branch_email": "email@55pbx.com", "call_rating": "4", "call_rating_form_id": "12"}
    d, anomalies = canonicalize(rec)
    assert d["type"] == "receptivo" and d["queue"] == "testePedro" and d["status_key"] == "call_attended"
    assert d["total_duration"] == 44 and d["spoken"] == 9           # call_total_time vence como total
    assert "call_date_invalid" in anomalies and "call_date" not in d
    assert d["branch_email"] == "email@55pbx.com" and d["rating"] == 4.0
    assert phase(d, "webhook") == "end"
    assert phase({"call_id": "1", "number": "1"}, "webhook") == "start"


def test_campos_pela_tabela_do_manual_e_troca():
    d, a = canonicalize({"call_id": "1", "call_time": 20, "call_duration": 100}, "descriptions")
    assert d["spoken"] == 20 and d["total_duration"] == 100 and a == []
    d, a = canonicalize({"call_id": "1", "call_time": 100, "call_duration": 20}, "descriptions")
    assert d["spoken"] == 20 and d["total_duration"] == 100 and a == ["time_fields_swapped"]


def test_horario_comercial_padrao_b2b():
    bh = BusinessHours()
    seg_17h = dt.datetime(2026, 10, 12, 20, 0, tzinfo=UTC)          # segunda 17:00 em São Paulo
    assert bh.is_open(seg_17h)
    assert bh.add(seg_17h, 120) == dt.datetime(2026, 10, 13, 13, 0, tzinfo=UTC)   # 1 h hoje + 1 h amanhã às 10:00
    sex_17h = dt.datetime(2026, 10, 16, 20, 0, tzinfo=UTC)
    assert bh.add(sex_17h, 90) == dt.datetime(2026, 10, 19, 12, 30, tzinfo=UTC)   # pula o fim de semana
    sab = dt.datetime(2026, 10, 17, 15, 0, tzinfo=UTC)
    assert not bh.is_open(sab) and bh.next_open(sab) == dt.datetime(2026, 10, 19, 12, 0, tzinfo=UTC)
    assert bh.seconds_between(seg_17h, dt.datetime(2026, 10, 13, 13, 0, tzinfo=UTC)) == 7200
    bh2 = BusinessHours(holidays=["2026-11-02"])
    assert bh2.add(dt.datetime(2026, 10, 30, 20, 30, tzinfo=UTC), 60) == dt.datetime(2026, 11, 3, 12, 30, tzinfo=UTC)


def test_protocolo_luhn():
    base = "2026000123"
    num = base + luhn_digit(base)
    assert len(num) == 11 and luhn_ok(num)
    errado = num[:-1] + str((int(num[-1]) + 1) % 10)
    assert not luhn_ok(errado)
    assert not luhn_ok(num[:4] + num[5] + num[4] + num[6:]) or num[4] == num[5]   # troca de dígitos vizinhos


def test_gravacao_tipo_duracao_backoff():
    w = wav(12.5)
    assert detect(w) == ("audio/wav", "wav") and abs(wav_duration(w) - 12.5) < 0.01
    assert detect(b"ID3\x04....") == ("audio/mpeg", "mp3") and detect(b"<html>") is None
    assert [backoff(n) for n in (1, 2, 3, 10)] == [300, 600, 1200, 21600]


def test_storage_local_e_range(tmp_path):
    st = LocalStorage(str(tmp_path / "r"))
    st.put("recordings/t/2026/10/x.wav", b"0123456789", "audio/wav")
    assert st.size("recordings/t/2026/10/x.wav") == 10
    assert b"".join(st.iter_range("recordings/t/2026/10/x.wav", 2, 5)) == b"2345"
    assert parse_range("bytes=2-5", 10) == (2, 5) and parse_range("bytes=-3", 10) == (7, 9)
    assert parse_range("bytes=20-", 10) is None
    import os
    assert oct(os.stat(str(tmp_path / "r")).st_mode)[-3:] == "700"
    try:
        st.put("../fora.wav", b"x", "audio/wav")
        assert False, "path traversal"
    except Exception as e:  # noqa: BLE001
        assert "fora" in str(e)


def test_mascara_e164():
    assert mask_e164("+5511999990001") == "+55119****0001"
