import json

import httpx
import pytest
import respx

from qa_pipeline.config import ConfigError, Settings
from qa_pipeline.events import envelope, parse_message
from qa_pipeline.llm import LlmError, build_llm
from qa_pipeline.llm.providers import AnthropicLlm, GeminiLlm, LocalLlm, OpenAiCompatibleLlm, parse_json
from qa_pipeline.stt import build_stt
from qa_pipeline.stt.external import OpenAiCompatibleStt


# ---------------------------------------------------------------- eventos
def test_parse_sdops_envelope_type_plus_data():
    env = {"type": "recording.stored", "id": "e1", "tenant_id": "dev55", "version": 1, "source": "sd-ops",
           "correlation_id": "c1", "subject": {"call_id": "call-9", "conversation_id": 1234},
           "payload": {"recording_id": "r1", "storage_key": "recordings/dev55/2026/10/r1.mp3"}}
    ev = parse_message({b"type": b"recording.stored", b"data": json.dumps(env).encode()})
    assert ev["type"] == "recording.stored" and ev["event_id"] == "e1" and ev["tenant_id"] == "dev55"
    assert ev["payload"]["call_id"] == "call-9" and ev["payload"]["conversation_id"] == 1234


def test_envelope_roundtrip():
    fields = envelope("qa.completed", {"recording_id": "r1", "call_id": "c1", "score": 90}, "dev55", "corr")
    assert set(fields) == {"type", "data"}
    ev = parse_message(fields)
    assert ev["type"] == "qa.completed" and ev["payload"]["score"] == 90 and ev["correlation_id"] == "corr"
    assert json.loads(fields["data"])["source"] == "qa-pipeline"


def test_invalid_envelope():
    assert parse_message({"data": "{nao json"}) is None
    assert parse_message({"foo": "bar"}) is None


# ------------------------------------------------------- política de custo
def test_external_ai_blocked_without_authorization():
    s = Settings()
    s.llm_provider, s.allow_external_ai, s.llm_model, s.llm_api_key = "openai", False, "x", "k"
    with pytest.raises(ConfigError):
        build_llm(s)
    s.llm_provider, s.stt_provider = "mock", "openai"
    with pytest.raises(ConfigError):
        build_stt(s)


def test_default_providers_are_free():
    s = Settings()
    assert s.llm_provider == "mock" and s.stt_provider == "faster_whisper" and s.allow_external_ai is False


# --------------------------------------------- adapters (HTTP mockado, sem chamada real)
@respx.mock
def test_openai_json_mode_and_no_store():
    route = respx.post("https://api.openai.com/v1/chat/completions").mock(return_value=httpx.Response(200, json={
        "model": "m", "choices": [{"message": {"content": '{"criteria": []}'}}], "usage": {"total_tokens": 10}}))
    out = OpenAiCompatibleLlm(model="m", api_key="k").complete_json("s", "u", task="qa")
    body = json.loads(route.calls[0].request.content)
    assert out.data == {"criteria": []} and body["store"] is False
    assert body["response_format"] == {"type": "json_object"}


@respx.mock
def test_anthropic_messages_format():
    route = respx.post("https://api.anthropic.com/v1/messages").mock(return_value=httpx.Response(200, json={
        "model": "m", "content": [{"type": "text", "text": "```json\n{\"a\": 1}\n```"}]}))
    out = AnthropicLlm(model="m", api_key="k").complete_json("s", "u", task="qa")
    req = route.calls[0].request
    assert out.data == {"a": 1} and req.headers["x-api-key"] == "k" and req.headers["anthropic-version"]


@respx.mock
def test_gemini_generate_content():
    respx.post("https://generativelanguage.googleapis.com/v1beta/models/g:generateContent").mock(
        return_value=httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"b": 2}'}]}}]}))
    assert GeminiLlm(model="g", api_key="k").complete_json("s", "u", task="qa").data == {"b": 2}


@respx.mock
def test_local_endpoint_and_errors():
    respx.post("http://ollama:11434/v1/chat/completions").mock(side_effect=[
        httpx.Response(503), httpx.Response(401), httpx.ConnectError("x")])
    llm = LocalLlm(model="llama", base_url="http://ollama:11434/v1")
    with pytest.raises(LlmError) as e1:
        llm.complete_json("s", "u", task="qa")
    assert not e1.value.permanent
    with pytest.raises(LlmError) as e2:
        llm.complete_json("s", "u", task="qa")
    assert e2.value.permanent
    with pytest.raises(LlmError):
        llm.complete_json("s", "u", task="qa")


def test_parse_json_variants():
    assert parse_json('texto antes {"x": 1} depois') == {"x": 1}
    with pytest.raises(LlmError):
        parse_json("sem json")


@respx.mock
def test_openai_stt_verbose_json(tmp_path):
    f = tmp_path / "a.mp3"
    f.write_bytes(b"ID3" + b"0" * 100)
    respx.post("https://api.openai.com/v1/audio/transcriptions").mock(return_value=httpx.Response(200, json={
        "language": "portuguese", "duration": 10.0,
        "segments": [{"start": 0, "end": 2.5, "text": " Bom dia", "avg_logprob": -0.1, "no_speech_prob": 0.01}]}))
    res = OpenAiCompatibleStt(api_key="k").transcribe(str(f), expected_duration_s=30)
    assert res.language == "pt" and res.segments[0].text == "Bom dia" and res.partial is True
