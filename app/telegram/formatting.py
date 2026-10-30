"""Plain-text profile used by Telegram and the local check command."""

from __future__ import annotations

from app.database.models import UserProfile

SKILL_LABELS = {
    "backend": "Backend",
    "frontend": "Frontend",
    "ai": "AI and machine learning",
    "databases": "Databases",
    "automation": "Automation",
}


def format_profile(profile: UserProfile) -> str:
    lines: list[str] = []
    if profile.full_name:
        lines.append(profile.full_name)
        lines.append("")
    lines.append("Your professional profile")
    lines.append("")

    lines.append("Education")
    for item in profile.education or []:
        bits = [
            part
            for part in (
                item.get("credential", ""),
                item.get("institution", ""),
                item.get("location", ""),
            )
            if part
        ]
        status = item.get("status") or ""
        suffix = f" ({status})" if status else ""
        lines.append(f"- {', '.join(bits)}{suffix}" if bits else f"- {status}")
    lines.append("")

    lines.append("Professional direction")
    for role in profile.target_roles or []:
        lines.append(f"- {role}")
    lines.append("")

    lines.append("Target job titles")
    for title in profile.target_job_titles or []:
        lines.append(f"- {title}")
    lines.append("")

    lines.append("Technical skills")
    skills = profile.skills or {}
    seen: set[str] = set()
    for key, label in SKILL_LABELS.items():
        values = skills.get(key) or []
        if values:
            lines.append(f"{label}: {', '.join(values)}")
            seen.add(key)
    for key, values in skills.items():
        if key not in seen and values:
            lines.append(f"{key}: {', '.join(values)}")
    lines.append("")

    lines.append("Projects")
    for project in profile.projects or []:
        name = project.get("name") or "Project"
        summary = project.get("summary") or ""
        if summary:
            lines.append(f"- {name}: {summary}")
        else:
            lines.append(f"- {name}")
    lines.append("")

    lines.append("Location")
    lines.append(profile.location)
    preferences = profile.preferences or {}
    target_locations = preferences.get("target_locations") or []
    if target_locations:
        lines.append("Open to:")
        for place in target_locations:
            lines.append(f"- {place}")
    lines.append("")

    band = preferences.get("experience_band")
    years = preferences.get("years_of_experience")
    if band or years is not None:
        lines.append("Experience")
        if band:
            lines.append(f"Level: {band}")
        if years is None:
            lines.append("Years: not set. Add years_of_experience in preferences when you want a number used.")
        else:
            lines.append(f"Years: {years}")
        lines.append("")

    goals = preferences.get("career_goals") or []
    if goals:
        lines.append("Career goals")
        for goal in goals:
            lines.append(f"- {goal}")
        lines.append("")

    lines.append("This profile is read from PostgreSQL. Edit the user_profile row to change it.")
    return "\n".join(lines).strip()
