"""Deterministic cleanup for URLs, HTML, and remote-work wording."""

from __future__ import annotations

import hashlib
import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

TRACKING_PREFIXES = ("utm_",)
RESTRICTED_PHRASES = (
    "us only",
    "usa only",
    "u.s. only",
    "united states only",
    "uk only",
    "united kingdom only",
    "eu only",
    "europe only",
    "european union only",
    "canada only",
    "north america only",
    "us citizens",
    "must be located in the us",
    "must be based in the us",
)
WORLDWIDE_PHRASES = (
    "worldwide",
    "work from anywhere",
    "anywhere in the world",
    "global remote",
    "remote - worldwide",
    "remote worldwide",
)


def strip_html(value: str) -> str:
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def canonical_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    query = [
        (key, item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.lower().startswith(TRACKING_PREFIXES)
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit(
        (
            parsed.scheme.lower() or "https",
            parsed.netloc.lower(),
            path,
            urlencode(query),
            "",
        )
    )


def content_hash(*parts: str) -> str:
    normalized = "|".join(re.sub(r"\s+", " ", part).strip().lower() for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def classify_workplace(location: str | None, text: str) -> tuple[str, str]:
    """Return workplace type and remote scope. Unknown remote is not treated as worldwide."""
    blob = f"{location or ''}\n{text[:1500]}".lower()
    restricted = any(phrase in blob for phrase in RESTRICTED_PHRASES)
    worldwide = any(phrase in blob for phrase in WORLDWIDE_PHRASES)
    remote = "remote" in blob or "work from home" in blob
    if remote:
        if restricted and not worldwide:
            return "remote", "country_restricted"
        if worldwide and not restricted:
            return "remote", "worldwide"
        return "remote", "unknown"
    if (location or "").strip():
        return "onsite", "onsite"
    return "unknown", "unknown"


def excerpt(text: str, limit: int = 420) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "…"
