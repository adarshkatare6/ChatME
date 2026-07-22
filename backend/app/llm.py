"""LLM provider abstraction.

Supports both:
1. OpenAI Responses API (POST /v1/responses) with stateful previous_response_id chaining
2. OpenAI-compatible /chat/completions fallback for gateways like OpenRouter
"""

from __future__ import annotations

from typing import Protocol

import httpx

from .config import get_settings

settings = get_settings()

ChatMessage = dict[str, str]  # {"role": ..., "content": ...}


class LLMError(RuntimeError):
    pass


class LLMProvider(Protocol):
    def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        previous_response_id: str | None = None,
    ) -> tuple[str, str | None]: ...


class OpenAIResponsesProvider:
    """Uses official OpenAI Responses API (POST /v1/responses) with stateful response chaining."""

    def __init__(self, api_key: str, default_model: str, timeout_s: float):
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout_s

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        previous_response_id: str | None = None,
    ) -> tuple[str, str | None]:
        if not self._api_key:
            raise LLMError(
                "OPENAI_API_KEY is not configured. Set it in backend/.env to enable chat."
            )

        # Extract system prompt instructions
        instructions_list = [m["content"] for m in messages if m["role"] == "system"]
        instructions = "\n\n".join(instructions_list) if instructions_list else None

        # Extract user input
        user_msgs = [m["content"] for m in messages if m["role"] == "user"]
        user_input = user_msgs[-1] if user_msgs else ""

        payload: dict = {
            "model": model or self._default_model,
            "input": user_input,
        }
        if instructions:
            payload["instructions"] = instructions
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    "https://api.openai.com/v1/responses",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"OpenAI Responses API returned {e.response.status_code}: {e.response.text[:300]}"
            )
        except httpx.HTTPError as e:
            raise LLMError(f"Responses API request failed: {e}")

        try:
            output_text = data.get("output_text")
            if output_text is None:
                parts = []
                for item in data.get("output", []):
                    for content in item.get("content", []):
                        if content.get("type") == "text":
                            parts.append(content.get("text", ""))
                output_text = "".join(parts)

            response_id = data.get("id")
            return output_text or "", response_id
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"Unexpected Responses API shape: {str(data)[:300]}")


class OpenAICompatibleProvider:
    """Works against OpenRouter and compatible /chat/completions gateways."""

    def __init__(self, base_url: str, api_key: str, default_model: str, timeout_s: float):
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._default_model = default_model
        self._timeout = timeout_s

    def complete(
        self,
        messages: list[ChatMessage],
        *,
        model: str | None = None,
        previous_response_id: str | None = None,
    ) -> tuple[str, str | None]:
        if not self._api_key:
            raise LLMError(
                "LLM_API_KEY is not configured. Set it in backend/.env to enable chat."
            )
        payload: dict = {"model": model or self._default_model, "messages": messages}

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(
                    f"{self._base_url}/chat/completions",
                    json=payload,
                    headers=headers,
                )
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPStatusError as e:
            raise LLMError(
                f"Provider returned {e.response.status_code}: {e.response.text[:300]}"
            )
        except httpx.HTTPError as e:
            raise LLMError(f"Provider request failed: {e}")

        try:
            content = data["choices"][0]["message"]["content"] or ""
            response_id = data.get("id")
            return content, response_id
        except (KeyError, IndexError, TypeError):
            raise LLMError(f"Unexpected provider response shape: {str(data)[:300]}")


_provider: LLMProvider | None = None


def get_provider() -> LLMProvider:
    global _provider
    if _provider is None:
        key = settings.effective_openai_api_key
        if key and ("api.openai.com" in settings.llm_base_url or key.startswith("sk-")):
            _provider = OpenAIResponsesProvider(
                api_key=key,
                default_model=settings.llm_model if "gpt" in settings.llm_model else "gpt-4o-mini",
                timeout_s=settings.llm_timeout_s,
            )
        else:
            _provider = OpenAICompatibleProvider(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                default_model=settings.llm_model,
                timeout_s=settings.llm_timeout_s,
            )
    return _provider
