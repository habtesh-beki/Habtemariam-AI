"""Database access for Phase 1. Research repositories arrive with their modules."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import seed_path
from app.database.models import UserProfile
from app.schemas.profile import ProfileSeed


def load_profile_seed() -> ProfileSeed:
    payload = json.loads(seed_path().read_text(encoding="utf-8"))
    return ProfileSeed.model_validate(payload)


class ProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self) -> UserProfile | None:
        return self.session.scalar(select(UserProfile).limit(1))

    def seed_if_empty(self, seed: ProfileSeed) -> tuple[UserProfile, bool]:
        """Insert the profile once. Later edits in the database are left untouched."""
        existing = self.get()
        if existing is not None:
            return existing, False

        profile = UserProfile(
            singleton=True,
            full_name=seed.full_name.strip() or None,
            education=[item.model_dump() for item in seed.education],
            target_roles=list(seed.target_roles),
            target_job_titles=list(seed.target_job_titles),
            skills=dict(seed.skills),
            projects=[item.model_dump() for item in seed.projects],
            location=seed.location,
            preferences=seed.preferences.model_dump(),
        )
        self.session.add(profile)
        self.session.flush()
        return profile, True
