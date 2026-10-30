"""Fetch live sources and store only new records."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import AiDevelopment, Job, JobMatch, Opportunity, Source, UserProfile
from app.research.http_client import HttpClient
from app.research.job_sources import collect_jobs
from app.research.news_sources import collect_news
from app.research.normalize import content_hash
from app.research.opportunity_sources import collect_opportunities
from app.services.matching import JobFacts, score_job

logger = logging.getLogger(__name__)

FRESH_FOR = timedelta(hours=12)


class ResearchSummary:
    def __init__(self) -> None:
        self.saved = {"jobs": 0, "news": 0, "opportunities": 0}
        self.errors: list[str] = []

    def line(self) -> str:
        if not self.errors:
            return ""
        return "Some sources failed: " + "; ".join(self.errors[:4])


def ensure_fresh(session: Session, kinds: set[str]) -> ResearchSummary:
    summary = ResearchSummary()
    client = HttpClient()
    try:
        if "jobs" in kinds and _is_stale(session, Job.created_at):
            _save_jobs(session, client, summary)
        if "news" in kinds and _is_stale(session, AiDevelopment.created_at):
            _save_news(session, client, summary)
        if "opportunities" in kinds and _is_stale(session, Opportunity.created_at):
            _save_opportunities(session, client, summary)
    finally:
        client.close()
    return summary


def _is_stale(session: Session, column) -> bool:
    latest = session.scalar(select(func.max(column)))
    if latest is None:
        return True
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    return datetime.now(UTC) - latest > FRESH_FOR


def _save_jobs(session: Session, client: HttpClient, summary: ResearchSummary) -> None:
    profile = session.scalar(select(UserProfile).limit(1))
    if profile is None:
        summary.errors.append("No profile is stored, so jobs were not scored.")
        return
    rows, errors = collect_jobs(client)
    summary.errors.extend(errors)
    for row in rows:
        if _url_exists(session, Job, row["canonical_url"]):
            continue
        source = _source(session, row, "job")
        facts = JobFacts(
            title=row["title"],
            description=row["description"],
            location=row["location"],
            workplace_type=row["workplace_type"],
            remote_scope=row["remote_scope"],
            salary_text=row["salary_text"],
            experience_text=row["experience_text"],
            education_text=row["education_text"],
        )
        match = score_job(profile, facts)
        job = Job(
            source_id=source.id,
            title=row["title"],
            company=row["company"],
            description=row["description"] or row["title"],
            location=row["location"],
            workplace_type=row["workplace_type"],
            remote_scope=row["remote_scope"],
            experience_text=row["experience_text"],
            education_text=row["education_text"],
            salary_text=row["salary_text"],
            published_at=row["published_at"],
            application_url=row["application_url"],
            source_url=row["source_url"],
            canonical_url=row["canonical_url"],
            content_hash=content_hash(row["title"], row["company"], row["location"] or ""),
            raw_payload=row["raw_payload"],
            verified_at=datetime.now(UTC),
        )
        try:
            with session.begin_nested():
                session.add(job)
                session.flush()
                session.add(
                    JobMatch(
                        job_id=job.id,
                        profile_id=profile.id,
                        score=match.score,
                        score_breakdown=match.breakdown,
                        why_match=match.why_match,
                        relevant_skills=match.relevant_skills,
                        missing_skills=match.missing_skills,
                        should_apply=match.should_apply,
                        seniority_fit=match.seniority_fit,
                        recommendation=match.recommendation,
                    )
                )
                session.flush()
        except IntegrityError:
            logger.info("Skipped duplicate job %s", row["canonical_url"])
            continue
        summary.saved["jobs"] += 1
    session.commit()


def _save_news(session: Session, client: HttpClient, summary: ResearchSummary) -> None:
    rows, errors = collect_news(client)
    summary.errors.extend(errors)
    for row in rows:
        if _url_exists(session, AiDevelopment, row["canonical_url"]):
            continue
        source = _source(session, row, "news")
        try:
            with session.begin_nested():
                session.add(
                    AiDevelopment(
                        source_id=source.id,
                        title=row["title"],
                        category=row["category"],
                        summary=row["summary"],
                        why_it_matters=row["why"],
                        practical_use=row["practical_use"],
                        should_investigate=row["should_investigate"],
                        source_url=row["source_url"],
                        canonical_url=row["canonical_url"],
                        published_at=row["published_at"],
                        content_hash=content_hash(row["title"], row["source_url"]),
                        relevance_score=row["relevance_score"],
                        raw_excerpt=row["raw_excerpt"],
                    )
                )
                session.flush()
        except IntegrityError:
            logger.info("Skipped duplicate development %s", row["canonical_url"])
            continue
        summary.saved["news"] += 1
    session.commit()


def _save_opportunities(session: Session, client: HttpClient, summary: ResearchSummary) -> None:
    rows, errors = collect_opportunities(client)
    summary.errors.extend(errors)
    for row in rows:
        if _url_exists(session, Opportunity, row["canonical_url"]):
            continue
        source = _source(session, row, "opportunity")
        try:
            with session.begin_nested():
                session.add(
                    Opportunity(
                        source_id=source.id,
                        name=row["name"],
                        organization=row["organization"],
                        benefits=row["benefits"],
                        eligibility_text=row["eligibility_text"],
                        eligibility_status=row["eligibility_status"],
                        ethiopia_eligible=row["ethiopia_eligible"],
                        deadline=row["deadline"],
                        application_url=row["application_url"],
                        source_url=row["source_url"],
                        canonical_url=row["canonical_url"],
                        why_relevant=row["why_relevant"],
                        content_hash=content_hash(row["name"], row["organization"]),
                        raw_excerpt=row["raw_excerpt"],
                    )
                )
                session.flush()
        except IntegrityError:
            logger.info("Skipped duplicate opportunity %s", row["canonical_url"])
            continue
        summary.saved["opportunities"] += 1
    session.commit()


def recent_jobs(session: Session, limit: int = 5) -> list[tuple[Job, JobMatch]]:
    rows = session.execute(
        select(Job, JobMatch)
        .join(JobMatch, JobMatch.job_id == Job.id)
        .order_by(JobMatch.score.desc(), Job.created_at.desc())
        .limit(limit)
    ).all()
    return [(row[0], row[1]) for row in rows]


def recent_news(session: Session, limit: int = 5) -> list[AiDevelopment]:
    return list(
        session.scalars(
            select(AiDevelopment)
            .order_by(AiDevelopment.relevance_score.desc(), AiDevelopment.published_at.desc())
            .limit(limit)
        )
    )


def recent_opportunities(session: Session, limit: int = 5) -> list[Opportunity]:
    return list(
        session.scalars(
            select(Opportunity)
            .where(Opportunity.eligibility_status != "ineligible")
            .order_by(Opportunity.created_at.desc())
            .limit(limit)
        )
    )


def _url_exists(session: Session, model, url: str) -> bool:
    return session.scalar(select(model.id).where(model.canonical_url == url).limit(1)) is not None


def _source(session: Session, row: dict[str, Any], category: str) -> Source:
    source = session.scalar(
        select(Source).where(Source.provider == row["provider"], Source.base_url == row["base_url"])
    )
    now = datetime.now(UTC)
    if source is None:
        source = Source(
            name=row["source_name"],
            category=category,
            base_url=row["base_url"],
            provider=row["provider"],
            enabled=True,
            config={},
            last_fetched_at=now,
        )
        session.add(source)
        session.flush()
        return source
    source.last_fetched_at = now
    return source
