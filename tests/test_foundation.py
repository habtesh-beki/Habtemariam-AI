from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.config import Settings, parse_user_ids
from app.database.models import Base
from app.database.repository import load_profile_seed
from app.services.gemini_service import GeminiClient
from app.services.llm import call_with_retry
from app.telegram.auth import is_allowed
from app.telegram.formatting import format_profile
from app.database.models import UserProfile


EXPECTED_TABLES = {
    "sources",
    "user_profile",
    "jobs",
    "job_matches",
    "ai_developments",
    "opportunities",
    "reports",
    "interactions",
    "research_runs",
}


def _settings(**overrides) -> Settings:
    values = {
        "database_url": "postgresql+psycopg://agent:agent@127.0.0.1:5432/personal_ai_agent",
        "telegram_allowed_user_ids": "",
        "gemini_api_key": "",
        "telegram_bot_token": "",
    }
    values.update(overrides)
    return Settings(**values)


def test_expected_tables_are_mapped() -> None:
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_parse_user_ids() -> None:
    assert parse_user_ids(" 42, 7 ") == frozenset({42, 7})
    assert parse_user_ids("") == frozenset()


def test_parse_user_ids_rejects_text() -> None:
    with pytest.raises(ValueError):
        parse_user_ids("42, me")


def test_settings_reads_allowed_ids() -> None:
    settings = _settings(telegram_allowed_user_ids="11,12")
    assert settings.allowed_user_ids == frozenset({11, 12})


def test_settings_reject_unknown_timezone() -> None:
    with pytest.raises(ValidationError):
        _settings(timezone="Not/AZone")


def test_settings_reject_non_postgres_url() -> None:
    with pytest.raises(ValidationError):
        _settings(database_url="sqlite:///local.db")


def test_allow_list_fails_closed() -> None:
    assert is_allowed(5, frozenset()) is False
    assert is_allowed(None, frozenset({5})) is False
    assert is_allowed(5, frozenset({5})) is True
    assert is_allowed(9, frozenset({5})) is False


def test_profile_text_comes_from_seed_fields() -> None:
    seed = load_profile_seed()
    profile = UserProfile(
        singleton=True,
        full_name=None,
        education=[item.model_dump() for item in seed.education],
        target_roles=list(seed.target_roles),
        target_job_titles=list(seed.target_job_titles),
        skills=dict(seed.skills),
        projects=[item.model_dump() for item in seed.projects],
        location=seed.location,
        preferences=seed.preferences.model_dump(),
    )
    text = format_profile(profile)
    for snippet in (
        "Your professional profile",
        "Electrical and Computer Engineering",
        "AASTU",
        "AI Engineer",
        "LangGraph",
        "FastAPI",
        "Aegis Health",
        "Addis Ababa, Ethiopia",
        "International remote positions",
        "early-career",
        "PostgreSQL",
    ):
        assert snippet in text


def test_retry_waits_then_succeeds() -> None:
    calls = {"count": 0}
    delays: list[float] = []

    def operation() -> str:
        calls["count"] += 1
        if calls["count"] < 3:
            error = RuntimeError("unavailable")
            error.code = 503
            raise error
        return "ok"

    assert call_with_retry(operation, attempts=3, base_delay=0.25, sleep=delays.append) == "ok"
    assert delays == [0.25, 0.5]


def test_retry_skips_auth_errors() -> None:
    def operation() -> str:
        error = RuntimeError("denied")
        error.code = 401
        raise error

    def fail_if_called(_delay: float) -> None:
        raise AssertionError("auth errors must not be retried")

    with pytest.raises(RuntimeError, match="denied"):
        call_with_retry(operation, attempts=3, sleep=fail_if_called)


def test_gemini_ping_uses_injected_client() -> None:
    class Models:
        def generate_content(self, model: str, contents: str):
            assert model == "gemini-3.8-flash"
            assert "PING_OK" in contents
            return SimpleNamespace(text="PING_OK")

    class Client:
        models = Models()

    client = GeminiClient("test-key", "gemini-3.8-flash", client=Client(), sleep=lambda _delay: None)
    assert client.ping() == "PING_OK"


def test_gemini_rejects_empty_response() -> None:
    class Models:
        def generate_content(self, model: str, contents: str):
            return SimpleNamespace(text="  ")

    class Client:
        models = Models()

    client = GeminiClient("test-key", "gemini-3.8-flash", client=Client(), sleep=lambda _delay: None, attempts=1)
    with pytest.raises(RuntimeError, match="empty"):
        client.generate_text("hello")
