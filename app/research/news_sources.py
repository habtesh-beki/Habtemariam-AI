"""AI developments from arXiv, Hugging Face, and GitHub public APIs."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any

from app.research.http_client import HttpClient
from app.research.normalize import canonical_url, excerpt

logger = logging.getLogger(__name__)

ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_URL = (
    "https://export.arxiv.org/api/query?"
    "search_query=all:LangGraph+OR+all:RAG+OR+all:%22AI+agent%22+OR+all:LLM"
    "&start=0&max_results=6&sortBy=submittedDate&sortOrder=descending"
)
HF_URL = "https://huggingface.co/api/models?sort=trendingScore&direction=-1&limit=20&pipeline_tag=text-generation"
GITHUB_URL = (
    "https://api.github.com/search/repositories?"
    "q=langgraph+OR+%22ai+agent%22+OR+rag+language:Python&sort=updated&per_page=5"
)
MODEL_NAMES = ("qwen", "llama", "gemma", "mistral", "deepseek", "phi", "command-r", "gpt")


def collect_news(client: HttpClient) -> tuple[list[dict[str, Any]], list[str]]:
    found: list[dict[str, Any]] = []
    errors: list[str] = []
    for collector in (_arxiv, _huggingface, _github):
        try:
            found.extend(collector(client))
        except Exception as exc:
            logger.exception("News source failed")
            errors.append(str(exc))
    return found, errors


def _arxiv(client: HttpClient) -> list[dict[str, Any]]:
    root = ET.fromstring(client.get_text(ARXIV_URL))
    rows: list[dict[str, Any]] = []
    for entry in root.findall(f"{ATOM}entry"):
        title = _text(entry, "title")
        summary = _text(entry, "summary")
        link = ""
        for item in entry.findall(f"{ATOM}link"):
            if item.attrib.get("rel") == "alternate" and item.attrib.get("href"):
                link = item.attrib["href"]
        if not title or not link.startswith("http"):
            continue
        published = _parse_time(_text(entry, "published"))
        rows.append(
            _row(
                provider="arxiv",
                source_name="arXiv",
                base_url="https://export.arxiv.org/api/query",
                title=title,
                category="machine_learning",
                summary=excerpt(summary or title),
                why="It is a newly submitted paper in the arXiv query for LLMs, agents, LangGraph, or RAG.",
                practical_use="Read the abstract on arXiv before spending time on the method.",
                should_investigate=True,
                source_url=link,
                published_at=published,
                relevance_score=70,
                raw_excerpt=excerpt(summary or "", 700),
            )
        )
    return rows


def _huggingface(client: HttpClient) -> list[dict[str, Any]]:
    payload = client.get_json(HF_URL)
    if not isinstance(payload, list):
        raise RuntimeError("Hugging Face returned an unexpected payload")
    rows: list[dict[str, Any]] = []
    for model in payload:
        if not isinstance(model, dict):
            continue
        model_id = str(model.get("id") or "")
        if not any(name in model_id.lower() for name in MODEL_NAMES):
            continue
        downloads = model.get("downloads") or 0
        if not isinstance(downloads, int) or downloads < 100:
            continue
        url = f"https://huggingface.co/{model_id}"
        pipeline = str(model.get("pipeline_tag") or "text-generation")
        created = _parse_time(model.get("createdAt"))
        rows.append(
            _row(
                provider="huggingface",
                source_name="Hugging Face",
                base_url="https://huggingface.co/api/models",
                title=model_id,
                category="model",
                summary=f"Hugging Face model {model_id}. Pipeline tag from the API: {pipeline}.",
                why="The model id matches a current open-model family used in LLM engineering.",
                practical_use="Open the model card and check the license before you depend on it.",
                should_investigate=True,
                source_url=url,
                published_at=created,
                relevance_score=64,
                raw_excerpt=f"pipeline_tag={pipeline}; downloads={model.get('downloads')}",
            )
        )
        if len(rows) >= 4:
            break
    return rows


def _github(client: HttpClient) -> list[dict[str, Any]]:
    payload = client.get_json(GITHUB_URL)
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise RuntimeError("GitHub returned an unexpected payload")
    rows: list[dict[str, Any]] = []
    for repo in items:
        if not isinstance(repo, dict):
            continue
        url = str(repo.get("html_url") or "")
        name = str(repo.get("full_name") or "")
        if not url.startswith("http") or not name:
            continue
        description = str(repo.get("description") or "").strip()
        stars = repo.get("stargazers_count")
        summary = description or "GitHub did not include a description for this repository."
        rows.append(
            _row(
                provider="github",
                source_name="GitHub",
                base_url="https://api.github.com/search/repositories",
                title=name,
                category="tool",
                summary=excerpt(summary),
                why="The repository matched a GitHub search for LangGraph, AI agents, or RAG in Python.",
                practical_use="Check the README and license, then try it only if it fits a project you are building.",
                should_investigate=isinstance(stars, int) and stars >= 100,
                source_url=url,
                published_at=_parse_time(repo.get("updated_at")),
                relevance_score=65 if not isinstance(stars, int) else min(90, 50 + stars // 100),
                raw_excerpt=f"stars={stars}; language={repo.get('language')}",
            )
        )
    return rows


def _row(**kwargs: Any) -> dict[str, Any]:
    source_url = str(kwargs["source_url"])
    return {
        **kwargs,
        "canonical_url": canonical_url(source_url),
    }


def _text(entry: ET.Element, name: str) -> str:
    node = entry.find(f"{ATOM}{name}")
    if node is None or node.text is None:
        return ""
    return " ".join(node.text.split())


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
