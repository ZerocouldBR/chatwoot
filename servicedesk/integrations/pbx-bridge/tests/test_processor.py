from pbx_bridge.audio import AudioError
from pbx_bridge.normalize import normalize
from tests.conftest import FakeAudio, report02_row


def sources(cw, cid):
    return [m["source_id"] for m in cw.msgs[cid]]


def creations(cw):
    return len([c for c in cw.calls if c[0] in ("create_message", "create_conversation", "create_contact")])


def test_receptiva_completa(env):
    s, store, cw, proc, audio = env
    call = proc.handle(normalize(report02_row()))
    cid = call["conversation_id"]
    conv = cw.convs[cid]
    assert conv["inbox_id"] == 7 and conv["meta"]["team"]["name"] == "Suporte" and conv["meta"]["assignee"]["id"] == 11
    assert conv["labels"] == ["55pbx", "55pbx_receptivo"]
    ca = conv["custom_attributes"]
    assert ca["pbx_call_id"] == "1767385476.86238" and ca["pbx_tipo"] == "receptivo" and ca["pbx_ramal"] == "5005"
    assert ca["pbx_numero"] == "+5511999990001" and ca["pbx_duracao_total"] == 118 and ca["pbx_tempo_falado"] == 103
    assert ca["zd_area_interna"] == "Suporte" and ca["zd_onboarding_relacionamento"] == "Ligação"
    assert ca["zd_status"] == "Aberto"
    assert conv["additional_attributes"]["pbx_call_id"] == "1767385476.86238"
    assert sources(cw, cid) == ["55pbx:1767385476.86238:registro", "55pbx:1767385476.86238:atualizacao",
                                "55pbx:1767385476.86238:acao_desconexao"]
    assert all(m["private"] for m in cw.msgs[cid])
    assert cw.msgs[cid][1]["attachments"] == ["ligacao-55pbx-1767385476.86238.mp3"]
    assert call["audio_status"] == "done" and audio.calls == 1
    assert cw.contacts[0]["phone_number"] == "+5511999990001"
    assert not any(c[0] == "messages" for c in cw.calls)  # conversa nova: não precisa conferir mensagens


def test_idempotente(env):
    s, store, cw, proc, audio = env
    proc.handle(normalize(report02_row()))
    n = creations(cw)
    proc.handle(normalize(report02_row()))
    proc.handle(normalize(report02_row()))
    assert len(cw.convs) == 1 and len(cw.contacts) == 1
    assert creations(cw) == n
    assert audio.calls == 1


def test_em_duas_etapas_inicio_e_fim(env):
    s, store, cw, proc, audio = env
    inicio = {k: v for k, v in report02_row().items()
              if k not in ("call_time_total_duration", "call_time_spoken", "call_time_waiting", "call_url_audio",
                           "call_disconnection")}
    call = proc.handle(normalize(inicio))
    cid = call["conversation_id"]
    assert sources(cw, cid) == ["55pbx:1767385476.86238:registro"]
    proc.handle(normalize(report02_row()))
    assert len(cw.msgs[cid]) == 3 and cw.convs[cid]["custom_attributes"]["pbx_tempo_falado"] == 103


def test_contato_existente_reutilizado_variacao_9(env):
    s, store, cw, proc, audio = env
    cw.contacts.append({"id": 5, "name": "Hotel Ficticio", "phone_number": "+551199990001"})
    call = proc.handle(normalize(report02_row()))
    assert cw.convs[call["conversation_id"]]["contact_id"] == 5 and len(cw.contacts) == 1


def test_interna_sem_audio(env):
    s, store, cw, proc, audio = env
    row = report02_row(call_id="1767390000.1", type_call="interno", call_number="5010", call_area_code="",
                       call_url_audio="", queue_name="undefined", call_disconnection="")
    call = proc.handle(normalize(row))
    conv = cw.convs[call["conversation_id"]]
    assert cw.contacts[-1]["identifier"] == "55pbx-ramal-5010"
    assert conv["labels"] == ["55pbx", "55pbx_interno"]
    assert call["audio_status"] == "absent" and audio.calls == 0
    assert "URL do Áudio: sem gravação" in cw.msgs[call["conversation_id"]][1]["content"]


def test_gatilho_encerra_ativo_novos_negocios(env):
    s, store, cw, proc, audio = env
    row = report02_row(call_id="1767391111.2", type_call="ativo", branch_number_agent="5010", name="Bruno Ficticio",
                       queue_name="0000-ativo", call_number="21988880002", call_area_code="")
    call = proc.handle(normalize(row))
    conv = cw.convs[call["conversation_id"]]
    assert conv["meta"]["team"]["name"] == "Novos Negócios"
    assert conv["status"] == "resolved"
    assert conv["custom_attributes"]["zd_novos_negocios"] == "Prospecção"
    assert conv["custom_attributes"]["zd_status"] == "Resolvido"
    assert conv["custom_attributes"]["zd_area_interna"] == "Novos negócios"


def test_gatilho_nao_dispara_para_suporte(env):
    s, store, cw, proc, audio = env
    call = proc.handle(normalize(report02_row(call_id="5.5", type_call="ativo")))
    assert cw.convs[call["conversation_id"]]["status"] == "open"


def test_gatilho_desligado(env):
    s, store, cw, proc, audio = env
    s.trigger_close_enabled = False
    row = report02_row(call_id="5.6", type_call="ativo", branch_number_agent="5010", queue_name="0000-ativo")
    call = proc.handle(normalize(row))
    assert cw.convs[call["conversation_id"]]["status"] == "open"


def test_audio_tentativa_posterior(env):
    s, store, cw, proc, audio = env
    proc.audio_fetcher = FakeAudio(fail=[AudioError("ainda não disponível")])
    t = [1000.0]
    proc.now = lambda: t[0]
    call = proc.handle(normalize(report02_row()))
    cid = call["conversation_id"]
    assert call["audio_status"] == "pending" and cw.msgs[cid][1]["attachments"] == []
    proc.retry_audio(call["call_id"])  # antes do prazo (relógio do processador): nada
    assert len(cw.msgs[cid]) == 3
    t[0] += 3600
    proc.retry_audio(call["call_id"])
    assert sources(cw, cid)[-1] == "55pbx:1767385476.86238:gravacao"
    assert cw.msgs[cid][-1]["attachments"] == ["ligacao-55pbx-1767385476.86238.mp3"]
    assert store.get_call(call["call_id"])["audio_status"] == "done"
    proc.retry_audio(call["call_id"])
    assert len(cw.msgs[cid]) == 4


def test_audio_falha_permanente(env):
    s, store, cw, proc, audio = env
    proc.audio_fetcher = FakeAudio(fail=[AudioError("host fora", permanent=True)])
    call = proc.handle(normalize(report02_row()))
    assert call["audio_status"] == "failed"


def test_download_desligado(env):
    s, store, cw, proc, audio = env
    s.download_recordings = False
    call = proc.handle(normalize(report02_row()))
    assert call["audio_status"] == "disabled" and audio.calls == 0
    assert "URL do Áudio: https://" in cw.msgs[call["conversation_id"]][1]["content"]


def test_recupera_conversa_sem_estado_local(env, tmp_path):
    s, store, cw, proc, audio = env
    proc.handle(normalize(report02_row()))
    from pbx_bridge.processor import Processor
    from pbx_bridge.store import Store
    proc2 = Processor(s, Store(str(tmp_path / "novo.sqlite3")), cw, audio_fetcher=audio)
    proc2.handle(normalize(report02_row(humor="5")))
    cid = list(cw.convs)[0]
    assert len(cw.convs) == 1
    assert sources(cw, cid).count("55pbx:1767385476.86238:registro") == 1
    assert sources(cw, cid)[-1] == "55pbx:1767385476.86238:acao_humor"
    assert "Humor do Cliente: 5/5" in cw.msgs[cid][-1]["content"]


def test_gatilho_atribuicao(env):
    s, store, cw, proc, audio = env
    row = report02_row(call_id="6.6", branch_number_agent="7777", name="Desconhecido")
    call = proc.handle(normalize(row))
    cid = call["conversation_id"]
    assert cw.convs[cid]["meta"]["assignee"] is None
    assert cw.convs[cid]["meta"]["team"]["name"] == "Suporte"  # receptiva pela fila
    ev = {"event": "message_created", "sender": {"id": 12, "type": "user"},
          "conversation": {"id": cid, "inbox_id": 7, "labels": ["55pbx"], "meta": {"assignee": None}}}
    assert proc.handle_chatwoot_event(dict(ev, sender={"id": 99, "type": "user"})) == "ignorado: integração"
    assert proc.handle_chatwoot_event(dict(ev, sender={"id": 3, "type": "contact"})) == "ignorado: remetente"
    assert proc.handle_chatwoot_event(dict(ev, conversation=dict(ev["conversation"], inbox_id=8))) == "ignorado: inbox"
    assert proc.handle_chatwoot_event(dict(ev, event="conversation_updated")) == "ignorado: evento"
    assert proc.handle_chatwoot_event(ev) == "atribuído"
    assert cw.convs[cid]["meta"]["assignee"]["id"] == 12
