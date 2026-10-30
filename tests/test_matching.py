from __future__ import annotations

from app.database.models import UserProfile
from app.research.job_sources import _salary
from app.research.normalize import canonical_url, classify_workplace
from app.services.matching import JobFacts, score_job, title_is_relevant


def _profile() -> UserProfile:
    return UserProfile(
        singleton=True,
        full_name=None,
        education=[],
        target_roles=["AI Engineer"],
        target_job_titles=["AI Engineer"],
        skills={
            "backend": ["Python", "FastAPI"],
            "ai": ["LLMs", "LangGraph"],
            "databases": ["PostgreSQL"],
        },
        projects=[],
        location="Addis Ababa, Ethiopia",
        preferences={"experience_band": "early-career"},
    )


def test_canonical_url_drops_tracking_and_slash() -> None:
    assert (
        canonical_url("HTTPS://Example.com/jobs/1/?utm_source=newsletter&ref=a")
        == "https://example.com/jobs/1?ref=a"
    )


def test_remote_restriction_is_not_worldwide() -> None:
    workplace, scope = classify_workplace("Remote", "US only. Must be located in the US.")
    assert workplace == "remote"
    assert scope == "country_restricted"


def test_blank_remote_is_unknown() -> None:
    workplace, scope = classify_workplace("", "This is a remote role.")
    assert workplace == "remote"
    assert scope == "unknown"


def test_title_filter_keeps_ai_work_and_skips_generic_roles() -> None:
    assert title_is_relevant("Applied AI Engineer")
    assert title_is_relevant("Senior Backend Engineer", "Build AI agents and APIs")
    assert not title_is_relevant("Senior Backend Engineer")
    assert not title_is_relevant("Frontend Engineer")
    assert not title_is_relevant("DESARROLLADOR FULL STACK")
    assert not title_is_relevant("Engineering Manager, Applied AI")


def test_zero_salary_is_not_invented() -> None:
    assert _salary(0, 0) is None
    assert _salary(None, None) is None
    text = _salary(80000, 100000)
    assert text is not None
    assert "80000" in text
    assert "currency" in text.lower()


def test_country_restricted_job_is_not_recommended() -> None:
    result = score_job(
        _profile(),
        JobFacts(
            title="Applied AI Engineer",
            description="Python, FastAPI, and LLMs. US only.",
            location="Remote, United States",
            workplace_type="remote",
            remote_scope="country_restricted",
            salary_text=None,
            experience_text=None,
            education_text=None,
        ),
    )
    assert result.should_apply is False
    assert "python" in result.relevant_skills
    assert result.breakdown["location"] == 0.1


def test_worldwide_remote_scores_location_fully() -> None:
    result = score_job(
        _profile(),
        JobFacts(
            title="LLM Engineer",
            description="Build agents with LangGraph and PostgreSQL.",
            location="Remote worldwide",
            workplace_type="remote",
            remote_scope="worldwide",
            salary_text=None,
            experience_text=None,
            education_text=None,
        ),
    )
    assert result.breakdown["location"] == 1.0
    assert result.should_apply is True
    assert "langgraph" in result.relevant_skills
