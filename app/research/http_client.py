"""Small HTTP getter with a timeout and a couple of retries."""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "personal-ai-agent/0.1 (personal career research)"


class HttpClient:
    def __init__(self, timeout: float = 25.0, attempts: int = 3) -> None:
        self._timeout = timeout
        self._attempts = attempts
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": USER_AGENT, "Accept": "application/json, application/xml, text/html"},
        )

    def close(self) -> None:
        self._client.close()

    def get_text(self, url: str) -> str:
        return self._get(url).text

    def get_json(self, url: str):
        response = self._get(url)
        return response.json()

    def _get(self, url: str) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self._attempts + 1):
            try:
                response = self._client.get(url)
                if response.status_code in {408, 429, 500, 502, 503, 504} and attempt < self._attempts:
                    time.sleep(0.4 * attempt)
                    continue
                response.raise_for_status()
                return response
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_error = exc
                logger.warning("Fetch failed for %s (%s)", url, exc.__class__.__name__)
                if attempt == self._attempts:
                    break
                time.sleep(0.4 * attempt)
        raise RuntimeError(f"Could not fetch {url}") from last_error
