"""Google Gemini client using the official Google Gen AI SDK."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from app.services.llm import call_with_retry

logger = logging.getLogger(__name__)

PING_TOKEN = "PING_OK"


class GeminiClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: Any | None = None,
        sleep: Callable[[float], None] = time.sleep,
        attempts: int = 3,
    ) -> None:
        if not api_key and client is None:
            raise ValueError("GEMINI_API_KEY is not set")
        if client is None:
            from google import genai

            client = genai.Client(api_key=api_key)
        self._client = client
        self._model = model
        self._sleep = sleep
        self._attempts = attempts

    def generate_text(self, prompt: str) -> str:
        logger.info("Gemini request model=%s characters=%s", self._model, len(prompt))

        def operation() -> str:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
            )
            text = getattr(response, "text", None)
            if text is None or not str(text).strip():
                raise RuntimeError("Gemini returned an empty response")
            return str(text).strip()

        return call_with_retry(
            operation,
            attempts=self._attempts,
            sleep=self._sleep,
        )

    def ping(self) -> str:
        """Confirm the key and model with a response that must contain a fixed token."""
        text = self.generate_text(
            f"Reply with exactly this token and nothing else: {PING_TOKEN}"
        )
        if PING_TOKEN not in text:
            raise RuntimeError(f"Gemini ping did not contain {PING_TOKEN}")
        return text
