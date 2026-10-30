"""PostgreSQL tables for the personal research agent.

The full schema is created in Phase 1. Later phases fill the research tables.
Vector columns use 768 dimensions so pgvector can index them.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.config import EMBEDDING_DIMENSIONS

WORKPLACE_TYPES = ("remote", "hybrid", "onsite", "unknown")
REMOTE_SCOPES = ("worldwide", "country_restricted", "onsite", "unknown")
SOURCE_CATEGORIES = ("job", "news", "opportunity")
DEVELOPMENT_CATEGORIES = ("model", "agent", "tool", "machine_learning", "industry")
ELIGIBILITY_STATUSES = ("confirmed", "uncertain", "ineligible")
ETHIOPIA_ELIGIBILITY = ("yes", "no", "unknown")
REPORT_STATUSES = ("pending", "delivered", "failed", "empty")
INTERACTION_ACTIONS = (
    "interested",
    "not_relevant",
    "applied",
    "save_for_later",
    "feedback",
)
ENTITY_TYPES = ("job", "development", "opportunity", "report")
RUN_STATUSES = ("running", "succeeded", "partial", "failed")


def _in_clause(column: str, values: tuple[str, ...], name: str) -> CheckConstraint:
    rendered = ", ".join(f"'{value}'" for value in values)
    return CheckConstraint(f"{column} IN ({rendered})", name=name)


class Base(DeclarativeBase):
    pass


class Source(Base):
    """A configured research source. Rows are data, so new boards do not need code edits."""

    __tablename__ = "sources"
    __table_args__ = (
        UniqueConstraint("provider", "base_url", name="uq_sources_provider_base_url"),
        _in_clause("category", SOURCE_CATEGORIES, "ck_sources_category"),
        Index("ix_sources_category_enabled", "category", "enabled"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    last_fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    jobs: Mapped[list[Job]] = relationship(back_populates="source")
    developments: Mapped[list[AiDevelopment]] = relationship(back_populates="source")
    opportunities: Mapped[list[Opportunity]] = relationship(back_populates="source")


class UserProfile(Base):
    """The single professional profile. Edit this row; do not hardcode the person in agents."""

    __tablename__ = "user_profile"
    __table_args__ = (
        UniqueConstraint("singleton", name="uq_user_profile_singleton"),
        CheckConstraint("singleton", name="ck_user_profile_singleton_true"),
        Index(
            "ix_user_profile_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    singleton: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    full_name: Mapped[str | None] = mapped_column(Text)
    education: Mapped[list] = mapped_column(JSONB, nullable=False)
    target_roles: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    target_job_titles: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False)
    skills: Mapped[dict] = mapped_column(JSONB, nullable=False)
    projects: Mapped[list] = mapped_column(JSONB, nullable=False)
    location: Mapped[str] = mapped_column(Text, nullable=False)
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    matches: Mapped[list[JobMatch]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    interactions: Mapped[list[Interaction]] = relationship(back_populates="profile", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_jobs_canonical_url"),
        _in_clause("workplace_type", WORKPLACE_TYPES, "ck_jobs_workplace_type"),
        _in_clause("remote_scope", REMOTE_SCOPES, "ck_jobs_remote_scope"),
        Index("ix_jobs_content_hash", "content_hash"),
        Index("ix_jobs_source_id", "source_id"),
        Index("ix_jobs_published_at", "published_at"),
        Index(
            "ix_jobs_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    company: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    location: Mapped[str | None] = mapped_column(Text)
    workplace_type: Mapped[str] = mapped_column(Text, nullable=False)
    remote_scope: Mapped[str] = mapped_column(Text, nullable=False)
    allowed_countries: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    skills_required: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    skills_preferred: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    experience_text: Mapped[str | None] = mapped_column(Text)
    education_text: Mapped[str | None] = mapped_column(Text)
    salary_text: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[date | None] = mapped_column(Date)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    application_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    source: Mapped[Source | None] = relationship(back_populates="jobs")
    matches: Mapped[list[JobMatch]] = relationship(back_populates="job", cascade="all, delete-orphan")


class JobMatch(Base):
    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("job_id", "profile_id", name="uq_job_matches_job_profile"),
        Index("ix_job_matches_profile_score", "profile_id", "score"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user_profile.id", ondelete="CASCADE"), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    why_match: Mapped[str] = mapped_column(Text, nullable=False)
    relevant_skills: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    missing_skills: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, server_default=text("'{}'::text[]"))
    should_apply: Mapped[bool | None] = mapped_column(Boolean)
    seniority_fit: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    job: Mapped[Job] = relationship(back_populates="matches")
    profile: Mapped[UserProfile] = relationship(back_populates="matches")


class AiDevelopment(Base):
    __tablename__ = "ai_developments"
    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_ai_developments_canonical_url"),
        _in_clause("category", DEVELOPMENT_CATEGORIES, "ck_ai_developments_category"),
        Index("ix_ai_developments_content_hash", "content_hash"),
        Index("ix_ai_developments_source_id", "source_id"),
        Index("ix_ai_developments_category", "category"),
        Index(
            "ix_ai_developments_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    why_it_matters: Mapped[str] = mapped_column(Text, nullable=False)
    practical_use: Mapped[str] = mapped_column(Text, nullable=False)
    should_investigate: Mapped[bool | None] = mapped_column(Boolean)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    relevance_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    raw_excerpt: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    source: Mapped[Source | None] = relationship(back_populates="developments")


class Opportunity(Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("canonical_url", name="uq_opportunities_canonical_url"),
        _in_clause("eligibility_status", ELIGIBILITY_STATUSES, "ck_opportunities_eligibility_status"),
        _in_clause("ethiopia_eligible", ETHIOPIA_ELIGIBILITY, "ck_opportunities_ethiopia_eligible"),
        Index("ix_opportunities_content_hash", "content_hash"),
        Index("ix_opportunities_source_id", "source_id"),
        Index("ix_opportunities_deadline", "deadline"),
        Index(
            "ix_opportunities_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    source_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(Text, nullable=False)
    organization: Mapped[str] = mapped_column(Text, nullable=False)
    benefits: Mapped[str] = mapped_column(Text, nullable=False)
    eligibility_text: Mapped[str] = mapped_column(Text, nullable=False)
    eligibility_status: Mapped[str] = mapped_column(Text, nullable=False)
    ethiopia_eligible: Mapped[str] = mapped_column(Text, nullable=False)
    deadline: Mapped[date | None] = mapped_column(Date)
    application_url: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_url: Mapped[str] = mapped_column(Text, nullable=False)
    why_relevant: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    raw_excerpt: Mapped[str | None] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    source: Mapped[Source | None] = relationship(back_populates="opportunities")


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        UniqueConstraint("report_date", name="uq_reports_report_date"),
        _in_clause("status", REPORT_STATUSES, "ck_reports_status"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    sections: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    module_errors: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    runs: Mapped[list[ResearchRun]] = relationship(back_populates="report")


class Interaction(Base):
    """Button presses and written feedback. Later ranking reads this table."""

    __tablename__ = "interactions"
    __table_args__ = (
        _in_clause("entity_type", ENTITY_TYPES, "ck_interactions_entity_type"),
        _in_clause("action", INTERACTION_ACTIONS, "ck_interactions_action"),
        Index("ix_interactions_entity", "entity_type", "entity_id"),
        Index("ix_interactions_profile_created", "profile_id", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user_profile.id", ondelete="CASCADE"), nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    profile: Mapped[UserProfile] = relationship(back_populates="interactions")


class ResearchRun(Base):
    """One execution of the daily pipeline, including partial failures."""

    __tablename__ = "research_runs"
    __table_args__ = (
        _in_clause("status", RUN_STATUSES, "ck_research_runs_status"),
        Index("ix_research_runs_report_id", "report_id"),
        Index("ix_research_runs_started_at", "started_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    report_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("reports.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, nullable=False)
    module_status: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    report: Mapped[Report | None] = relationship(back_populates="runs")
