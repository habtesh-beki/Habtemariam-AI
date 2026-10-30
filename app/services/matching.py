"""Python job score. Gemini is not required for the number."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from app.database.models import UserProfile

SKILL_ALIASES = {
    "python": ("python",),
    "node.js": ("node.js", "nodejs", "node js"),
    "nestjs": ("nestjs", "nest.js"),
    "fastapi": ("fastapi", "fast api"),
    "rest apis": ("rest api", "restful"),
    "react": ("react",),
    "next.js": ("next.js", "nextjs", "next js"),
    "typescript": ("typescript",),
    "tailwind css": ("tailwind",),
    "llms": ("llm", "llms", "large language model"),
    "rag": ("rag", "retrieval-augmented", "retrieval augmented"),
    "ai agents": ("ai agent", "ai agents", "agentic"),
    "langgraph": ("langgraph",),
    "langchain": ("langchain",),
    "pytorch": ("pytorch", "torch"),
    "scikit-learn": ("scikit-learn", "sklearn"),
    "machine learning": ("machine learning",),
    "postgresql": ("postgresql", "postgres"),
    "redis": ("redis",),
    "pgvector": ("pgvector",),
    "vector databases": ("vector database", "vector db"),
    "n8n": ("n8n",),
}

TITLE_TERMS = (
    "ai engineer",
    "applied ai",
    "llm",
    "machine learning",
    "ml engineer",
    "rag",
    "generative",
    "research engineer",
    "agent",
)
SUPPORT_TERMS = ("backend", "back-end", "python")
SUPPORT_CONTEXT = ("ai", "llm", "machine learning", "rag", "agent", "api", "fastapi", "django")
TITLE_SKIPS = (
    "manager",
    "director",
    "vice president",
    "vp ",
    "recruiter",
    "sales",
    "accountant",
    "counsel",
    "front end",
    "frontend",
    "front-end",
)


@dataclass(frozen=True)
class JobFacts:
    title: str
    description: str
    location: str | None
    workplace_type: str
    remote_scope: str
    salary_text: str | None
    experience_text: str | None
    education_text: str | None


@dataclass(frozen=True)
class MatchResult:
    score: Decimal
    breakdown: dict[str, float]
    why_match: str
    relevant_skills: list[str]
    missing_skills: list[str]
    should_apply: bool | None
    seniority_fit: str
    recommendation: str


def title_is_relevant(title: str, description: str = "") -> bool:
    lowered = title.lower()
    if any(skip in lowered for skip in TITLE_SKIPS):
        return False
    if any(term in lowered for term in TITLE_TERMS):
        return True
    if any(term in lowered for term in SUPPORT_TERMS):
        context = f"{lowered}\n{description[:800].lower()}"
        return any(term in context for term in SUPPORT_CONTEXT)
    return False


def score_job(profile: UserProfile, facts: JobFacts) -> MatchResult:
    detected = _detect_skills(f"{facts.title}\n{facts.description}")
    owned = _owned_skills(profile)
    relevant = sorted(detected & owned)
    missing = sorted(detected - owned)
    skill_score = _skill_score(detected, owned)
    experience_score = _experience_score(facts.title, facts.experience_text)
    education_score = _education_score(facts.education_text)
    location_score = _location_score(facts.location, facts.workplace_type, facts.remote_scope)
    growth_score = 0.9 if title_is_relevant(facts.title) else 0.45
    pay_score = 0.7 if facts.salary_text else 0.6
    breakdown = {
        "technical_skills": round(skill_score, 4),
        "experience": round(experience_score, 4),
        "education": round(education_score, 4),
        "location": round(location_score, 4),
        "career_growth": round(growth_score, 4),
        "compensation": round(pay_score, 4),
    }
    weighted = (
        skill_score * 35
        + experience_score * 20
        + education_score * 10
        + location_score * 15
        + growth_score * 10
        + pay_score * 10
    )
    score = Decimal(str(round(weighted, 2)))
    seniority = _seniority(facts.title, facts.experience_text)
    should_apply = _should_apply(float(score), location_score)
    return MatchResult(
        score=score,
        breakdown=breakdown,
        why_match=_why(facts, relevant, location_score),
        relevant_skills=relevant,
        missing_skills=missing,
        should_apply=should_apply,
        seniority_fit=seniority,
        recommendation=_recommendation(facts, float(score), location_score, seniority, missing),
    )


def _owned_skills(profile: UserProfile) -> set[str]:
    owned: set[str] = set()
    for values in (profile.skills or {}).values():
        for value in values:
            owned.add(value.lower())
    return owned


def _detect_skills(text: str) -> set[str]:
    lowered = text.lower()
    found: set[str] = set()
    for name, aliases in SKILL_ALIASES.items():
        if any(re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lowered) for alias in aliases):
            found.add(name)
    return found


def _skill_score(detected: set[str], owned: set[str]) -> float:
    if not detected:
        return 0.5
    return len(detected & owned) / len(detected)


def _experience_score(title: str, experience_text: str | None) -> float:
    years = _years(experience_text or "")
    senior = _is_senior(title)
    if years is None:
        return 0.55 if senior else 0.85
    if years <= 2:
        return 0.9
    if years <= 4:
        return 0.7
    return 0.4 if senior else 0.55


def _education_score(education_text: str | None) -> float:
    text = (education_text or "").lower()
    if not text:
        return 0.85
    if "phd" in text or "ph.d" in text or "doctorate" in text:
        return 0.25
    return 0.9


def _location_score(location: str | None, workplace_type: str, remote_scope: str) -> float:
    loc = (location or "").lower()
    if "addis" in loc or "ethiopia" in loc:
        return 1.0
    if remote_scope == "worldwide":
        return 1.0
    if workplace_type == "remote" and remote_scope == "unknown":
        return 0.55
    if remote_scope == "country_restricted":
        return 0.1
    if workplace_type == "onsite" or remote_scope == "onsite":
        return 0.15
    return 0.4


def _years(text: str) -> int | None:
    match = re.search(r"(\d+)\s*\+?\s*years", text.lower())
    if not match:
        return None
    return int(match.group(1))


def _is_senior(title: str) -> bool:
    lowered = title.lower()
    return any(word in lowered for word in ("senior", "staff", "principal", "lead "))


def _seniority(title: str, experience_text: str | None) -> str:
    years = _years(experience_text or "")
    if _is_senior(title) or (years is not None and years >= 5):
        return "stretch for early-career"
    return "plausible for early-career"


def _should_apply(score: float, location_score: float) -> bool | None:
    if location_score < 0.2:
        return False
    if score >= 62:
        return True
    return None


def _why(facts: JobFacts, relevant: list[str], location_score: float) -> str:
    parts = [f"Title: {facts.title}."]
    if relevant:
        parts.append("Overlapping skills: " + ", ".join(relevant) + ".")
    else:
        parts.append("No overlapping skills were detected in the posting text.")
    if location_score >= 1:
        parts.append("Location is compatible with Addis Ababa or worldwide remote work.")
    elif location_score <= 0.15:
        parts.append("Location looks onsite or limited to other countries.")
    elif facts.remote_scope == "unknown":
        parts.append("The posting is remote, and the source did not say whether it is open worldwide.")
    return " ".join(parts)


def _recommendation(
    facts: JobFacts,
    score: float,
    location_score: float,
    seniority: str,
    missing: list[str],
) -> str:
    if location_score < 0.2:
        return "Skip unless the company separately accepts applicants in Ethiopia. The source does not show that."
    if score >= 62 and seniority == "plausible for early-career":
        return "Worth applying. The title and detected skills line up with your profile."
    if score >= 62:
        return "Possible stretch application. The work matches, and the seniority ask is above early-career."
    missing_note = f" Missing from your profile: {', '.join(missing[:4])}." if missing else ""
    if facts.remote_scope == "unknown":
        return "Read the posting before applying. Remote scope was not stated." + missing_note
    return "Lower priority than the stronger matches." + missing_note
