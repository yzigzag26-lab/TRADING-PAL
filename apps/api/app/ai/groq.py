"""Minimal asynchronous Groq Chat Completions client using HTTPX.

The provider boundary is deliberately small so another model provider can be
introduced without changing Baymax classification or analysis logic.
"""

from __future__ import annotations

from typing import Protocol

import httpx


GROQ_CHAT_COMPLETIONS_URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqUnavailable(Exception):
    """Raised when Groq cannot provide a usable completion."""


class ChatMessage(Protocol):
    role: str
    content: str


class GroqChatClient:
    """Small, bounded-timeout client for Groq's OpenAI-compatible API."""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str = "openai/gpt-oss-20b",
        timeout_seconds: float = 25.0,
    ) -> None:
        self._api_key = api_key.strip() if api_key else None
        self.model = model
        self._timeout = httpx.Timeout(timeout_seconds, connect=5.0)
        self._client: httpx.AsyncClient | None = None

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    async def start(self) -> None:
        """Create the reusable HTTP connection pool when credentials exist."""
        if self.configured and self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)

    async def close(self) -> None:
        """Release the HTTP connection pool."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def complete(
        self,
        *,
        messages: list[dict[str, str]],
        response_format: dict[str, object] | None = None,
        max_tokens: int = 1200,
        temperature: float = 0.2,
    ) -> str:
        """Return assistant text or raise a provider-safe exception."""
        if not self.configured:
            raise GroqUnavailable("Groq is not configured")
        await self.start()
        if self._client is None or self._api_key is None:
            raise GroqUnavailable("Groq client is unavailable")

        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format is not None:
            payload["response_format"] = response_format

        try:
            response = await self._client.post(
                GROQ_CHAT_COMPLETIONS_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            body = response.json()
            choices = body.get("choices")
            if not isinstance(choices, list) or not choices:
                raise GroqUnavailable("Groq returned no completion choices")
            choice = choices[0]
            if not isinstance(choice, dict):
                raise GroqUnavailable("Groq returned an invalid completion")
            message = choice.get("message")
            if not isinstance(message, dict):
                raise GroqUnavailable("Groq returned an invalid message")
            content = message.get("content")
            if not isinstance(content, str) or not content.strip():
                raise GroqUnavailable("Groq returned an empty completion")
            return content.strip()
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise GroqUnavailable("Groq completion request failed") from exc
