"""Adapters de LLM que devolvem JSON. Externos ficam bloqueados sem ALLOW_EXTERNAL_AI=true.

Nenhum modelo pago foi chamado neste projeto (sem autorização de custo): os adapters externos
foram testados apenas com HTTP mockado (respx). Os formatos seguem a documentação oficial:
- OpenAI Chat Completions: POST {base}/chat/completions, response_format={"type":"json_object"}.
- Anthropic Messages: POST https://api.anthropic.com/v1/messages, headers x-api-key e anthropic-version.
- Google Gemini: POST .../v1beta/models/{model}:generateContent, header x-goog-api-key,
  generationConfig.responseMimeType="application/json".
- Local: qualquer servidor compatível com a API da OpenAI (Ollama, vLLM, llama.cpp server).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

import httpx


class LlmError(RuntimeError):
    def __init__(self, message: str, permanent: bool = False, code: str = "llm_error"):
        super().__init__(message)
        self.permanent = permanent
        self.code = code


@dataclass
class LlmResponse:
    data: dict
    provider: str
    model: str
    usage: dict = field(default_factory=dict)


def parse_json(text: str) -> dict:
    text = (text or "").strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass
    raise LlmError("resposta do LLM não é JSON válido", code="llm_bad_json")


class LlmProvider:
    name = "base"
    external = False
    model = ""

    def complete_json(self, system: str, user: str, *, task: str, context: Optional[dict] = None) -> LlmResponse:
        raise NotImplementedError  # pragma: no cover


def _raise_for(resp: httpx.Response, who: str) -> None:
    if resp.status_code in (400, 401, 403, 404, 422):
        raise LlmError(f"{who} recusou a requisição (HTTP {resp.status_code})", permanent=True, code="llm_rejected")
    if resp.status_code >= 300:
        raise LlmError(f"{who} indisponível (HTTP {resp.status_code})", code="llm_unavailable")


class _HttpProvider(LlmProvider):
    def __init__(self, model: str, api_key: str = "", base_url: str = "", timeout_s: int = 120,
                 temperature: float = 0.0):
        if not model:
            raise LlmError(f"LLM_MODEL obrigatório para o provedor {self.name}", permanent=True, code="config")
        self.model = model
        self.api_key = api_key
        self.base_url = (base_url or "").rstrip("/")
        self.timeout_s = timeout_s
        self.temperature = temperature

    def _post(self, url: str, headers: dict, body: dict) -> httpx.Response:
        try:
            return httpx.post(url, headers=headers, json=body, timeout=self.timeout_s)
        except httpx.HTTPError as exc:
            raise LlmError(f"{self.name} indisponível: {type(exc).__name__}", code="llm_unavailable") from exc


class OpenAiCompatibleLlm(_HttpProvider):
    name = "openai"
    external = True

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.base_url = self.base_url or "https://api.openai.com/v1"
        if self.external and not self.api_key:
            raise LlmError("LLM_API_KEY ausente", permanent=True, code="config")

    def complete_json(self, system, user, *, task, context=None):
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        body = {"model": self.model, "temperature": self.temperature,
                "response_format": {"type": "json_object"},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.external:
            body["store"] = False  # não guardar a conversa no provedor
        resp = self._post(f"{self.base_url}/chat/completions", headers, body)
        _raise_for(resp, self.name)
        payload = resp.json()
        text = payload["choices"][0]["message"]["content"]
        return LlmResponse(parse_json(text), self.name, payload.get("model", self.model), payload.get("usage") or {})


class LocalLlm(OpenAiCompatibleLlm):
    """Endpoint local/privado compatível com OpenAI (dados não saem da infraestrutura)."""
    name = "local"
    external = False

    def __init__(self, *a, **kw):
        _HttpProvider.__init__(self, *a, **kw)
        if not self.base_url:
            raise LlmError("LLM_BASE_URL obrigatório para LLM local", permanent=True, code="config")


class AnthropicLlm(_HttpProvider):
    name = "anthropic"
    external = True

    def complete_json(self, system, user, *, task, context=None):
        if not self.api_key:
            raise LlmError("LLM_API_KEY ausente", permanent=True, code="config")
        url = (self.base_url or "https://api.anthropic.com") + "/v1/messages"
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        body = {"model": self.model, "max_tokens": 4096, "temperature": self.temperature, "system": system,
                "messages": [{"role": "user", "content": user}]}
        resp = self._post(url, headers, body)
        _raise_for(resp, self.name)
        payload = resp.json()
        text = "".join(b.get("text", "") for b in payload.get("content", []) if b.get("type") == "text")
        return LlmResponse(parse_json(text), self.name, payload.get("model", self.model), payload.get("usage") or {})


class GeminiLlm(_HttpProvider):
    name = "gemini"
    external = True

    def complete_json(self, system, user, *, task, context=None):
        if not self.api_key:
            raise LlmError("LLM_API_KEY ausente", permanent=True, code="config")
        base = self.base_url or "https://generativelanguage.googleapis.com/v1beta"
        url = f"{base}/models/{self.model}:generateContent"
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        body = {"systemInstruction": {"parts": [{"text": system}]},
                "contents": [{"role": "user", "parts": [{"text": user}]}],
                "generationConfig": {"temperature": self.temperature, "responseMimeType": "application/json"}}
        resp = self._post(url, headers, body)
        _raise_for(resp, self.name)
        payload = resp.json()
        try:
            text = "".join(p.get("text", "") for p in payload["candidates"][0]["content"]["parts"])
        except (KeyError, IndexError) as exc:
            raise LlmError("resposta do Gemini sem conteúdo", code="llm_bad_json") from exc
        return LlmResponse(parse_json(text), self.name, self.model, payload.get("usageMetadata") or {})
