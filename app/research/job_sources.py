"""Job listings from public JSON APIs. Descriptions are fetched only for title matches."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from app.research.http_client import HttpClient
from app.research.normalize import canonical_url, classify_workplace, strip_html
from app.services.matching import title_is_relevant

logger = logging.getLogger(__name__)

GREENHOUSE_BOARDS = ("anthropic", "scaleai")
MAX_DETAILS_PER_BOARD = 4
MAX_REMOTEOK = 8


def collect_jobs(client: HttpClient) -> tuple[list[dict[str, Any]], list[str]]:
    found: list[dict[str, Any]] = []
    errors: list[str] = []
    for collector in (_remoteok, _greenhouse):
        try:
            found.extend(collector(client))
        except Exception as exc:
            logger.exception("Job source failed")
            errors.append(str(exc))
    return found, errors


def _remoteok(client: HttpClient) -> list[dict[str, Any]]:
    payload = client.get_json("https://remoteok.com/api")
    rows: list[dict[str, Any]] = []
    if not isinstance(payload, list):
        raise RuntimeError("Remote OK returned an unexpected payload")
    for item in payload:
        if not isinstance(item, dict) or not item.get("position"):
            continue
        title = str(item["position"]).strip()
        description = strip_html(str(item.get("description") or ""))
        if not title_is_relevant(title, description):
            continue
        location = str(item.get("location") or "").strip() or None
        workplace, remote_scope = classify_workplace(location, description)
        if workplace == "unknown":
            workplace = "remote"
        apply_url = str(item.get("apply_url") or item.get("url") or "").strip()
        source_url = str(item.get("url") or apply_url).strip()
        if not source_url.startswith("http"):
            continue
        rows.append(
            {
                "provider": "remoteok",
                "source_name": "Remote OK",
                "base_url": "https://remoteok.com/api",
                "title": title,
                "company": str(item.get("company") or "Unknown company").strip(),
                "description": description[:6000],
                "location": location,
                "workplace_type": workplace,
                "remote_scope": remote_scope,
                "salary_text": _salary(item.get("salary_min"), item.get("salary_max")),
                "experience_text": _experience_snippet(description),
                "education_text": _education_snippet(description),
                "published_at": _parse_time(item.get("date")),
                "application_url": apply_url if apply_url.startswith("http") else source_url,
                "source_url": source_url,
                "canonical_url": canonical_url(source_url),
                "raw_payload": {"id": item.get("id"), "slug": item.get("slug"), "tags": item.get("tags") or []},
            }
        )
        if len(rows) >= MAX_REMOTEOK:
            break
    return rows


def _greenhouse(client: HttpClient) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for board in GREENHOUSE_BOARDS:
        listing = client.get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs")
        jobs = listing.get("jobs") if isinstance(listing, dict) else None
        if not isinstance(jobs, list):
            raise RuntimeError(f"Greenhouse board {board} returned an unexpected payload")
        taken = 0
        for job in jobs:
            title = str(job.get("title") or "").strip()
            if not title or not title_is_relevant(title):
                continue
            job_id = job.get("id")
            if job_id is None:
                continue
            detail = client.get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}")
            description = strip_html(str(detail.get("content") or ""))
            location_name = (detail.get("location") or {}).get("name") or (job.get("location") or {}).get("name")
            location = str(location_name).strip() if location_name else None
            workplace, remote_scope = classify_workplace(location, description)
            absolute = str(detail.get("absolute_url") or job.get("absolute_url") or "").strip()
            if not absolute.startswith("http"):
                continue
            rows.append(
                {
                    "provider": "greenhouse",
                    "source_name": f"Greenhouse {board}",
                    "base_url": f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs",
                    "title": title,
                    "company": str(detail.get("company_name") or board).strip(),
                    "description": description[:6000],
                    "location": location,
                    "workplace_type": workplace,
                    "remote_scope": remote_scope,
                    "salary_text": None,
                    "experience_text": _experience_snippet(description),
                    "education_text": _education_snippet(description),
                    "deadline": None,
                    "published_at": _parse_time(detail.get("first_published") or job.get("first_published")),
                    "application_url": absolute,
                    "source_url": absolute,
                    "canonical_url": canonical_url(absolute),
                    "raw_payload": {"board": board, "id": job_id},
                }
            )
            taken += 1
            if taken >= MAX_DETAILS_PER_BOARD:
                break
    return rows


def _salary(low: object, high: object) -> str | None:
    try:
        low_n = int(low or 0)
        high_n = int(high or 0)
    except (TypeError, ValueError):
        return None
    if low_n <= 0 and high_n <= 0:
        return None
    return (
        f"Source listed a numeric range of {low_n}–{high_n}. "
        "The API payload did not name the currency."
    )


def _experience_snippet(text: str) -> str | None:
    match = re.search(r".{0,40}\d+\s*\+?\s*years.{0,40}", text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(0).strip()


def _education_snippet(text: str) -> str | None:
    match = re.search(r".{0,50}(ph\.?d|doctorate|bachelor|master'?s|degree).{0,50}", text, flags=re.IGNORECASE)
    if not match:
        return None
    return match.group(0).strip()


def _parse_time(value: object) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
