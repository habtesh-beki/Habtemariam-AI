"""Provider-neutral language-model interface.

Gemini is the first implementation. Another provider can be added beside it
without changing the research agents.
"""

from __future__ import annotations

from typing import Protocol


class LLMClient(Protocol):
    def generate_text(self, prompt: str) -> str:
        """Return plain text for a single prompt."""


def is_retryable_error(exc: Exception) -> bool:
    """Retry rate limits and temporary server failures. Do not retry auth or bad requests."""
    status = getattr(exc, "code", None)
    if status is None:
        status = getattr(exc, "status_code", None)
    if status in {408, 429, 500, 502, 503, 504}:
        return True
    return exc.__class__.__name__ in {"ServerError", "APIConnectionError"}


def call_with_retry(
    operation,
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    sleep,
    retry_on=is_retryable_error,
):
    """Call operation, waiting longer after each retryable failure."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1")
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt == attempts or not retry_on(exc):
                raise
            sleep(base_delay * (2 ** (attempt - 1)))
    if last_error is not None:
        raise last_error
    raise RuntimeError("retry loop ended without a result")
