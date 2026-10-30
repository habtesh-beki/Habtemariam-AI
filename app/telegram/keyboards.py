"""Chat buttons for sections and for a stored job."""

from __future__ import annotations

from uuid import UUID

from telegram import (
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

BOT_COMMANDS = (
    BotCommand("jobs", "Job matches"),
    BotCommand("news", "AI developments"),
    BotCommand("opportunities", "Programs and credits"),
    BotCommand("report", "Combined report"),
    BotCommand("profile", "Your profile"),
    BotCommand("settings", "Stored preferences"),
    BotCommand("feedback", "Save a note"),
    BotCommand("start", "Show the section buttons"),
)


def menu_keyboard() -> ReplyKeyboardMarkup:
    """Buttons that stay under the message box."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton("/jobs"), KeyboardButton("/news")],
            [KeyboardButton("/opportunities"), KeyboardButton("/report")],
            [KeyboardButton("/profile"), KeyboardButton("/settings")],
        ],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Choose a section",
    )

ACTIONS = {
    "i": "interested",
    "n": "not_relevant",
    "a": "applied",
    "s": "save_for_later",
}


def job_keyboard(job_id: UUID) -> InlineKeyboardMarkup:
    token = str(job_id)
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Interested", callback_data=f"job:i:{token}"),
                InlineKeyboardButton("Not relevant", callback_data=f"job:n:{token}"),
            ],
            [
                InlineKeyboardButton("Applied", callback_data=f"job:a:{token}"),
                InlineKeyboardButton("Save for later", callback_data=f"job:s:{token}"),
            ],
        ]
    )
