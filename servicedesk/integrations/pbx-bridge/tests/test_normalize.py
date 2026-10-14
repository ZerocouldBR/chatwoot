import json

from pbx_bridge import notes
from pbx_bridge.normalize import (call_datetime, mask, mobile_variants, normalize, parse_body, queue_key, to_e164,
                                  to_seconds)
from tests.conftest import report02_row


def test_report02_row_normalizado():
    d = normalize(report02_row())
    assert d["call_id"] == "1767385476.86238"
    assert d["total_duration"] == 118 and d["spoken"] == 103 and d["waiting"] == 15 and d["ura_time"] == 10
    assert d["type"] == "receptivo" and d["disconnection"] == "operador"
    assert d["branch"] == "5005" and d["queue"] == "0000-FILA_SUPORTE_1"
    assert d["audio_url"].endswith(".WAV")
    assert "cpf" not in d and "order" not in d  # vazio/undefined descartados


def test_variacoes_de_chave_e_tipo():
    d = normalize({"callId": "1.2", "Tipo": "outbound", "Ramal": 5010, "Telefone": "+55 (21) 98888-0002",
                   "recordingUrl": "https://x.55pbx.com/a.wav", "billsec": "42", "Humor do Cliente": "4/5"})
    assert d == {"call_id": "1.2", "type": "ativo", "branch": "5010", "number": "+55 (21) 98888-0002",
                 "audio_url": "https://x.55pbx.com/a.wav", "spoken": 42, "humor": 4}


def test_ivr_steps():
    d = normalize({"call_id": "9", "wk_ivr_1_name": "Menu", "wk_ivr_1_option": "2", "wk_ivr_1_option_name": "Suporte"})
    assert d["ivr"] == "Menu: Suporte"


def test_to_seconds():
    assert to_seconds("00:01:05") == 65 and to_seconds("01:05") == 65 and to_seconds("65") == 65
    assert to_seconds("undefined") is None and to_seconds(12.7) == 12


def test_e164():
    assert to_e164("999990001", "11") == "+5511999990001"
    assert to_e164("1130000000") == "+551130000000"
    assert to_e164("5511999990001") == "+5511999990001"
    assert to_e164("011999990001") == "+5511999990001"
    assert to_e164("+1 415 555 0100") == "+14155550100"
    assert to_e164("5005") is None
    assert to_e164("30000000") is None  # sem DDD
    assert mobile_variants("+5511999990001") == ["+5511999990001", "+551199990001"]
    assert mobile_variants("+551199990001") == ["+551199990001", "+5511999990001"]


def test_parse_json_embrulhado_e_lista():
    body = json.dumps({"data_report02": [report02_row(), report02_row(call_id="2.2")], "uuid": "x"}).encode()
    recs, _ = parse_body(body, "application/json")
    assert [normalize(r)["call_id"] for r in recs] == ["1767385476.86238", "2.2"]
    recs, _ = parse_body(json.dumps({"event": "hangup", "data": {"callid": "3.3", "ramal": "5005"}}).encode(), "")
    assert normalize(recs[0])["call_id"] == "3.3" and normalize(recs[0])["event"] == "hangup"


def test_parse_form_urlencoded():
    recs, _ = parse_body(b"call_id=4.4&type_call=interno&branch_number_agent=5005&call_number=5010",
                         "application/x-www-form-urlencoded")
    d = normalize(recs[0])
    assert d["call_id"] == "4.4" and d["type"] == "interno"


def test_parse_lixo():
    recs, raw = parse_body(b"isso nao e um payload", "text/plain")
    assert recs == [] and raw


def test_mask():
    assert mask("tel 11999990001 cpf 12345678900") == "tel 11*******01 cpf 12*******00"
    assert "99999" not in mask("https://vsa19.55pbx.com/x/audio-5511999990001.WAV")


def test_datetime_e_ficha():
    d = normalize(report02_row())
    assert call_datetime(d).strftime("%d/%m/%Y %H:%M:%S") == "02/01/2026 17:24:36"
    d2 = {"call_id": "1767385476.86238"}
    assert call_datetime(d2).strftime("%d/%m/%Y %H:%M") == "02/01/2026 17:24"
    txt = notes.registro(d)
    for linha in ("CPF: Informação não disponível para esta ligação", "Tipo da ligação: receptivo", "Número: 999990001",
                  "Ramal: 5005", "DDD: 11", "Data da ligação: 02/01/2026 17:24:36", "Call ID: 1767385476.86238",
                  "Fila: 0000-FILA_SUPORTE_1", "URA: Opcao - 2"):
        assert linha in txt
    up = notes.atualizacao(d)
    assert "Tempo falado (s): 103" in up and "Tempo total de ligação (s): 118" in up and "URL do Áudio: https://" in up
    assert notes.acao_desconexao(d).endswith("Ligação terminada pelo operador")
    assert queue_key("3855-FILA_NOVOS_NEGÓCIOS") == "fila_novos_negocios" and queue_key("Fila Suporte 1") == "fila_suporte_1"
