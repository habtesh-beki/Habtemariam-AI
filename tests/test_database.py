from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from telegram.ext import CommandHandler

from app.config import PROJECT_ROOT, Settings
from app.database.models import Base, UserProfile
from app.database.repository import ProfileRepository, load_profile_seed
from app.database.session import get_engine, reset_engine
from app.telegram.commands import build_application
from app.telegram.formatting import format_profile
from app.telegram.keyboards import menu_keyboard


def _can_connect() -> bool:
    try:
        settings = Settings()
    except Exception:
        return False
    from sqlalchemy import create_engine

    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def database_ready():
    if not _can_connect():
        pytest.skip("PostgreSQL is not running. Start it with: docker compose up -d")
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config(str(PROJECT_ROOT / "alembic.ini")), "head")
    reset_engine()
    yield
    reset_engine()


@pytest.fixture
def db_session(database_ready):
    """Use a transaction that always rolls back, so tests cannot wipe the real profile."""
    connection = get_engine().connect()
    outer = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session.execute(text("TRUNCATE user_profile CASCADE"))
    session.commit()
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


def test_migrated_schema_matches_models(database_ready) -> None:
    inspector = inspect(get_engine())
    assert set(Base.metadata.tables) <= set(inspector.get_table_names())
    for name, table in Base.metadata.tables.items():
        database_columns = {column["name"] for column in inspector.get_columns(name)}
        model_columns = {column.name for column in table.columns}
        assert database_columns == model_columns, name


def test_vector_extension_is_installed(database_ready) -> None:
    with get_engine().connect() as connection:
        found = connection.execute(
            text("SELECT extname FROM pg_extension WHERE extname = 'vector'")
        ).scalar_one()
    assert found == "vector"


def test_seed_inserts_once_and_preserves_edits(db_session) -> None:
    repository = ProfileRepository(db_session)
    profile, created = repository.seed_if_empty(load_profile_seed())
    assert created is True
    db_session.commit()

    profile.full_name = "Edited Name"
    profile.location = "Addis Ababa, Ethiopia"
    db_session.commit()

    again, created_again = repository.seed_if_empty(load_profile_seed())
    db_session.commit()
    assert created_again is False
    assert again.id == profile.id
    assert again.full_name == "Edited Name"

    text = format_profile(again)
    assert "Edited Name" in text
    assert "Aegis Health" in text


def test_second_profile_row_is_rejected(db_session) -> None:
    repository = ProfileRepository(db_session)
    first, _created = repository.seed_if_empty(load_profile_seed())
    db_session.commit()
    db_session.add(
        UserProfile(
            singleton=True,
            full_name=None,
            education=first.education,
            target_roles=first.target_roles,
            target_job_titles=first.target_job_titles,
            skills=first.skills,
            projects=first.projects,
            location=first.location,
            preferences=first.preferences,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_registered_commands() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://agent:agent@127.0.0.1:5432/personal_ai_agent",
        telegram_bot_token="123456789:" + ("A" * 35),
        telegram_allowed_user_ids="42",
    )
    application = build_application(settings)
    names: set[str] = set()
    for handler in application.handlers[0]:
        if isinstance(handler, CommandHandler):
            names.update(handler.commands)
    assert names == {
        "start",
        "profile",
        "report",
        "jobs",
        "news",
        "opportunities",
        "settings",
        "feedback",
    }


def test_menu_keyboard_lists_sections() -> None:
    labels = [button.text for row in menu_keyboard().keyboard for button in row]
    assert labels == ["/jobs", "/news", "/opportunities", "/report", "/profile", "/settings"]


def test_bot_refuses_to_build_without_an_allow_list() -> None:
    settings = Settings(
        database_url="postgresql+psycopg://agent:agent@127.0.0.1:5432/personal_ai_agent",
        telegram_bot_token="123456789:" + ("A" * 35),
        telegram_allowed_user_ids="",
    )
    with pytest.raises(SystemExit):
        build_application(settings)
