"""Short Telegram text for stored findings."""

from __future__ import annotations

from app.database.models import AiDevelopment, Job, JobMatch, Opportunity, UserProfile


def format_job(index: int, job: Job, match: JobMatch) -> str:
    apply = job.application_url or job.source_url
    missing = ", ".join(match.missing_skills[:5]) if match.missing_skills else "None detected in the posting."
    relevant = ", ".join(match.relevant_skills[:6]) if match.relevant_skills else "None detected."
    decision = {True: "Yes", False: "No", None: "Read it first"}[match.should_apply]
    location = job.location or "Not stated"
    return (
        f"{index}. {job.title}\n"
        f"Company: {job.company}\n"
        f"Location: {location}\n"
        f"Score: {match.score}\n"
        f"Why: {match.why_match}\n"
        f"Relevant skills: {relevant}\n"
        f"Missing: {missing}\n"
        f"Seniority: {match.seniority_fit}\n"
        f"Apply: {decision}\n"
        f"Link: {apply}\n"
        f"{match.recommendation}"
    )


def format_development(index: int, item: AiDevelopment) -> str:
    published = item.published_at.date().isoformat() if item.published_at else "date not provided"
    investigate = "Yes" if item.should_investigate else "Only if you have time"
    return (
        f"{index}. {item.title}\n"
        f"{item.summary}\n"
        f"Why it matters: {item.why_it_matters}\n"
        f"Look into it: {investigate}\n"
        f"Published: {published}\n"
        f"Link: {item.source_url}"
    )


def format_opportunity(index: int, item: Opportunity) -> str:
    deadline = item.deadline.isoformat() if item.deadline else "not listed"
    ethiopia = {"yes": "yes", "no": "no", "unknown": "not confirmed"}[item.ethiopia_eligible]
    return (
        f"{index}. {item.name}\n"
        f"Organization: {item.organization}\n"
        f"Benefits: {item.benefits}\n"
        f"Eligibility: {item.eligibility_status}. Ethiopian applicants: {ethiopia}.\n"
        f"{item.eligibility_text}\n"
        f"Deadline: {deadline}\n"
        f"Why: {item.why_relevant}\n"
        f"Link: {item.application_url or item.source_url}"
    )


def format_settings(profile: UserProfile) -> str:
    preferences = profile.preferences or {}
    locations = preferences.get("target_locations") or []
    lines = [
        "Research settings stored in the database",
        "",
        f"Location: {profile.location}",
        f"Experience level: {preferences.get('experience_band') or 'not set'}",
        f"Years: {preferences.get('years_of_experience') if preferences.get('years_of_experience') is not None else 'not set'}",
        "",
        "Target locations",
    ]
    lines.extend(f"- {place}" for place in locations)
    lines.extend(
        [
            "",
            "Target titles",
        ]
    )
    lines.extend(f"- {title}" for title in profile.target_job_titles or [])
    lines.append("")
    lines.append("To change these, edit the user_profile row. /profile will show the new text.")
    return "\n".join(lines)


def format_report(jobs: list[tuple[Job, JobMatch]], news: list[AiDevelopment], opportunities: list[Opportunity]) -> str:
    parts = ["PERSONAL AI INTELLIGENCE REPORT", ""]
    parts.append("1. JOB OPPORTUNITIES")
    if jobs:
        parts.extend(format_job(index, job, match) for index, (job, match) in enumerate(jobs, start=1))
    else:
        parts.append("No new job matches are stored.")
    parts.extend(["", "2. IMPORTANT AI DEVELOPMENTS"])
    if news:
        parts.extend(format_development(index, item) for index, item in enumerate(news, start=1))
    else:
        parts.append("No AI developments are stored.")
    parts.extend(["", "3. NEW OPPORTUNITIES"])
    if opportunities:
        parts.extend(format_opportunity(index, item) for index, item in enumerate(opportunities, start=1))
    else:
        parts.append("No opportunities are stored.")
    parts.extend(
        [
            "",
            "4. CAREER INSIGHTS",
            _insight(jobs),
            "",
            "5. TODAY'S RECOMMENDED ACTION",
            _action(jobs, news, opportunities),
        ]
    )
    return "\n\n".join(parts)


def _insight(jobs: list[tuple[Job, JobMatch]]) -> str:
    counts: dict[str, int] = {}
    for _job, match in jobs:
        for skill in match.missing_skills:
            counts[skill] = counts.get(skill, 0) + 1
    if not counts:
        return "The stored postings did not show a repeated missing skill yet."
    ranked = sorted(counts, key=counts.get, reverse=True)[:3]
    return "Skills that showed up in these postings and are not in your profile: " + ", ".join(ranked) + "."


def _action(jobs, news, opportunities) -> str:
    if jobs:
        job, _match = jobs[0]
        link = job.application_url or job.source_url
        return f"Open the strongest stored job and decide whether to apply: {job.title} at {job.company}. {link}"
    if opportunities:
        item = opportunities[0]
        return f"Read the official page before treating it as eligible: {item.application_url or item.source_url}"
    if news:
        return f"Skim one primary source: {news[0].source_url}"
    return "No action today. The sources that were checked did not produce a stored finding."
