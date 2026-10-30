"""Official program pages. Eligibility stays uncertain unless the page states it."""

from __future__ import annotations

import logging
import re
from typing import Any

from app.research.http_client import HttpClient
from app.research.normalize import canonical_url, excerpt

logger = logging.getLogger(__name__)

PAGES = (
    {
        "url": "https://aws.amazon.com/startups",
        "organization": "Amazon Web Services",
        "title_terms": ("startup", "aws"),
        "why": "AWS publishes a startups page that can include cloud credits for builders.",
    },
    {
        "url": "https://cloud.google.com/startup",
        "organization": "Google Cloud",
        "title_terms": ("startup", "google"),
        "why": "Google Cloud publishes a startups program page for cloud credits.",
    },
    {
        "url": "https://www.microsoft.com/en-us/startups",
        "organization": "Microsoft",
        "title_terms": ("startup", "microsoft"),
        "why": "Microsoft publishes a startups page that can include Azure credits.",
    },
)


def collect_opportunities(client: HttpClient) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    errors: list[str] = []
    for page in PAGES:
        try:
            rows.append(_fetch_page(client, page))
        except Exception as exc:
            logger.exception("Opportunity page failed: %s", page["url"])
            errors.append(f"{page['organization']}: {exc}")
    return [row for row in rows if row], errors


def _fetch_page(client: HttpClient, page: dict[str, Any]) -> dict[str, Any]:
    html = client.get_text(page["url"])
    title = _title(html)
    lowered = title.lower()
    if not title or not any(term in lowered for term in page["title_terms"]):
        raise RuntimeError(f"Page title did not match the expected program: {title or 'missing title'}")
    description = _meta_description(html)
    benefits = description or "The fetched page had no meta description. Open the official link for the current benefits."
    return {
        "provider": "official-page",
        "source_name": page["organization"],
        "base_url": page["url"],
        "name": title,
        "organization": page["organization"],
        "benefits": excerpt(benefits, 500),
        "eligibility_text": (
            "Eligibility was not confirmed from a structured field on this page. "
            "Treat it as uncertain until you read the official requirements."
        ),
        "eligibility_status": "uncertain",
        "ethiopia_eligible": "unknown",
        "deadline": None,
        "application_url": page["url"],
        "source_url": page["url"],
        "canonical_url": canonical_url(page["url"]),
        "why_relevant": page["why"],
        "raw_excerpt": excerpt(description or title, 500),
    }


def _title(html: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if not match:
        return ""
    return " ".join(re.sub(r"<[^>]+>", " ", match.group(1)).split())


def _meta_description(html: str) -> str:
    patterns = (
        r'(?is)<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        r'(?is)<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, html)
        if match:
            return " ".join(match.group(1).split())
    return ""
