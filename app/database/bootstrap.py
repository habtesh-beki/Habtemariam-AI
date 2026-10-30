"""Startup database checks and the one-time profile seed."""

from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.database.models import UserProfile
from app.database.repository import ProfileRepository, load_profile_seed
from app.database.session import get_engine, session_scope

logger = logging.getLogger(__name__)


def prepare_database(settings: Settings) -> UserProfile:
    """Connect, then insert the profile only when the table is empty."""
    logger.info("Preparing database for timezone %s", settings.timezone)
    engine = get_engine()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except OperationalError:
        logger.exception("Database connection failed")
        raise

    with session_scope() as session:
        profile, created = ProfileRepository(session).seed_if_empty(load_profile_seed())
        logger.info("Profile %s", "seeded" if created else "already present")
        return profile
