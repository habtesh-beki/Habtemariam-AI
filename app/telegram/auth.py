"""Decide whether a Telegram user may use this bot."""

from __future__ import annotations


def is_allowed(user_id: int | None, allowed: frozenset[int] | set[int]) -> bool:
    """Fail closed. An empty allow-list rejects every account."""
    if user_id is None or not allowed:
        return False
    return user_id in allowed
