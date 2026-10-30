"""Profile seed loaded once into PostgreSQL."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EducationItem(BaseModel):
    institution: str
    credential: str
    location: str
    status: str


class ProjectItem(BaseModel):
    name: str
    summary: str


class ProfilePreferences(BaseModel):
    """Editable career preferences. Extra keys are kept so the row can grow."""

    model_config = ConfigDict(extra="allow")

    open_to_international_remote: bool
    open_to_ethiopia: bool
    open_to_international: bool
    experience_band: str | None = None
    years_of_experience: int | None = None
    career_goals: list[str] = Field(default_factory=list)
    target_locations: list[str] = Field(default_factory=list)
    feedback_weights: dict[str, float] = Field(default_factory=dict)


class ProfileSeed(BaseModel):
    full_name: str = ""
    education: list[EducationItem]
    target_roles: list[str]
    target_job_titles: list[str]
    skills: dict[str, list[str]]
    projects: list[ProjectItem]
    location: str
    preferences: ProfilePreferences
