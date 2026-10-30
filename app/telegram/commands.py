"""Telegram commands. Research commands read PostgreSQL and refresh stale sources."""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from app.config import Settings
from app.database.models import Interaction
from app.database.repository import ProfileRepository
from app.database.session import session_scope
from app.services.research_runner import (
    ensure_fresh,
    recent_jobs,
    recent_news,
    recent_opportunities,
)
from app.telegram.auth import is_allowed
from app.telegram.formatting import format_profile
from app.telegram.keyboards import ACTIONS, BOT_COMMANDS, job_keyboard, menu_keyboard
from app.telegram.listings import (
    format_development,
    format_job,
    format_opportunity,
    format_report,
    format_settings,
)

logger = logging.getLogger(__name__)

TELEGRAM_MESSAGE_LIMIT = 3900

START_TEXT = """Personal AI intelligence agent

This bot delivers research. It is not a chat assistant.

The buttons under the message box open each section. The same list is in the menu beside the input field.

/jobs — job matches
/news — AI developments
/opportunities — program pages
/report — combined findings
/profile — your profile
/settings — stored preferences
/feedback — a note, or the buttons under a job

The first request after a quiet period checks the live sources. That can take a minute."""


async def _guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    settings: Settings = context.application.bot_data["settings"]
    user = update.effective_user
    user_id = user.id if user is not None else None
    if is_allowed(user_id, settings.allowed_user_ids):
        return True
    logger.info("Rejected Telegram user id %s", user_id)
    message = update.effective_message
    if message is not None:
        await message.reply_text("This bot is private.")
    elif update.callback_query is not None:
        await update.callback_query.answer("This bot is private.", show_alert=True)
    return False


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update, context):
        return
    if update.effective_message is not None:
        await update.effective_message.reply_text(START_TEXT, reply_markup=menu_keyboard())


async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update, context):
        return
    message = update.effective_message
    if message is None:
        return
    with session_scope() as session:
        profile = ProfileRepository(session).get()
        text = format_profile(profile) if profile is not None else ""
    if not text:
        await message.reply_text("No profile is stored yet.")
        return
    await _reply_chunks(message, text)


async def jobs_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update, context):
        return
    message = update.effective_message
    if message is None:
        return
    await message.reply_text("Checking job sources. This can take a minute.", reply_markup=menu_keyboard())
    note, rows = await asyncio.to_thread(_load_jobs)
    if note:
        await message.reply_text(note)
    if not rows:
        await message.reply_text("No job matches are stored. Nothing was invented to fill this list.")
        return
    for index, (text, job_id) in enumerate(rows, start=1):
        await message.reply_text(text, reply_markup=job_keyboard(job_id))


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update, context):
        return
    message = update.effective_message
    if message is None:
        return
    await message.reply_text("Checking AI sources. This can take a minute.", reply_markup=menu_keyboard())
    note, text = await asyncio.to_thread(_load_news)
    if note:
        await message.reply_text(note)
    await _reply_chunks(message, text)


async def opportunities_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update, context):
        return
    message = update.effective_message
    if message is None:
        return
    await message.reply_text("Checking official program pages.", reply_markup=menu_keyboard())
    note, text = await asyncio.to_thread(_load_opportunities)
    if note:
        await message.reply_text(note)
    await _reply_chunks(message, text)


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update, context):
        return
    message = update.effective_message
    if message is None:
        return
    await message.reply_text(
        "Building the report from stored research. Missing sections are fetched first.",
        reply_markup=menu_keyboard(),
    )
    note, text = await asyncio.to_thread(_load_report)
    if note:
        await message.reply_text(note)
    await _reply_chunks(message, text)


async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update, context):
        return
    message = update.effective_message
    if message is None:
        return
    with session_scope() as session:
        profile = ProfileRepository(session).get()
        text = format_settings(profile) if profile is not None else "No profile is stored yet."
    await message.reply_text(text)


async def feedback_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update, context):
        return
    message = update.effective_message
    if message is None:
        return
    note = " ".join(context.args or []).strip()
    if not note:
        await message.reply_text(
            "Use the buttons under a job, or send /feedback followed by a short note."
        )
        return
    with session_scope() as session:
        profile = ProfileRepository(session).get()
        if profile is None:
            await message.reply_text("No profile is stored yet.")
            return
        session.add(
            Interaction(
                profile_id=profile.id,
                entity_type="report",
                entity_id=profile.id,
                action="feedback",
                note=note[:2000],
            )
        )
    await message.reply_text("Saved. Later ranking will read this note.")


async def job_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await _guard(update, context):
        return
    query = update.callback_query
    if query is None or not query.data:
        return
    try:
        _prefix, code, raw_id = query.data.split(":", 2)
        action = ACTIONS[code]
        job_id = UUID(raw_id)
    except (ValueError, KeyError):
        await query.answer("That button is no longer valid.")
        return
    with session_scope() as session:
        profile = ProfileRepository(session).get()
        if profile is None:
            await query.answer("No profile is stored.")
            return
        session.add(
            Interaction(
                profile_id=profile.id,
                entity_type="job",
                entity_id=job_id,
                action=action,
            )
        )
    await query.answer("Saved")
    labels = {
        "interested": "Interested",
        "not_relevant": "Not relevant",
        "applied": "Applied",
        "save_for_later": "Save for later",
    }
    await query.edit_message_reply_markup(reply_markup=None)
    if query.message is not None:
        await query.message.reply_text(f"Saved: {labels[action]}.")


def _load_jobs() -> tuple[str, list[tuple[str, UUID]]]:
    with session_scope() as session:
        summary = ensure_fresh(session, {"jobs"})
        rows = recent_jobs(session)
        payload = [(format_job(index, job, match), job.id) for index, (job, match) in enumerate(rows, start=1)]
        return summary.line(), payload


def _load_news() -> tuple[str, str]:
    with session_scope() as session:
        summary = ensure_fresh(session, {"news"})
        rows = recent_news(session)
        if not rows:
            return summary.line(), "No AI developments are stored. Nothing was invented to fill this list."
        text = "\n\n".join(format_development(index, item) for index, item in enumerate(rows, start=1))
        return summary.line(), text


def _load_opportunities() -> tuple[str, str]:
    with session_scope() as session:
        summary = ensure_fresh(session, {"opportunities"})
        rows = recent_opportunities(session)
        if not rows:
            return summary.line(), "No opportunities are stored. Nothing was invented to fill this list."
        text = "\n\n".join(format_opportunity(index, item) for index, item in enumerate(rows, start=1))
        return summary.line(), text


def _load_report() -> tuple[str, str]:
    with session_scope() as session:
        summary = ensure_fresh(session, {"jobs", "news", "opportunities"})
        text = format_report(recent_jobs(session), recent_news(session), recent_opportunities(session))
        return summary.line(), text


async def _reply_chunks(message, text: str) -> None:
    remaining = text.strip()
    while remaining:
        if len(remaining) <= TELEGRAM_MESSAGE_LIMIT:
            await message.reply_text(remaining)
            return
        cut = remaining.rfind("\n", 0, TELEGRAM_MESSAGE_LIMIT)
        if cut < 200:
            cut = TELEGRAM_MESSAGE_LIMIT
        await message.reply_text(remaining[:cut])
        remaining = remaining[cut:].strip()


def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("jobs", jobs_command))
    application.add_handler(CommandHandler("news", news_command))
    application.add_handler(CommandHandler("opportunities", opportunities_command))
    application.add_handler(CommandHandler("report", report_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("feedback", feedback_command))
    application.add_handler(CallbackQueryHandler(job_callback, pattern=r"^job:"))


def build_application(settings: Settings) -> Application:
    if not settings.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set. Add it to .env and start again.")
    if not settings.allowed_user_ids:
        raise SystemExit(
            "TELEGRAM_ALLOWED_USER_IDS is not set. Add your numeric Telegram user id to .env."
        )
    async def post_init(application: Application) -> None:
        await application.bot.set_my_commands(list(BOT_COMMANDS))
        for user_id in settings.allowed_user_ids:
            try:
                await application.bot.send_message(
                    chat_id=user_id,
                    text="The section buttons are under the message box. They stay there, so you do not need to scroll back to the first message.",
                    reply_markup=menu_keyboard(),
                )
            except Exception:
                logger.exception("Could not deliver the section buttons to user %s", user_id)

    application = (
        Application.builder()
        .token(settings.telegram_bot_token)
        .post_init(post_init)
        .build()
    )
    application.bot_data["settings"] = settings
    register_handlers(application)

    async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.exception("Telegram handler failed", exc_info=context.error)
        if isinstance(update, Update) and update.effective_message is not None:
            await update.effective_message.reply_text("Something went wrong. Try again in a moment.")

    application.add_error_handler(on_error)
    return application
