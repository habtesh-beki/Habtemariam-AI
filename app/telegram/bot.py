"""Telegram bot process."""

from __future__ import annotations

import logging

from telegram import Update

from app.config import Settings
from app.database.bootstrap import prepare_database
from app.telegram.commands import build_application

logger = logging.getLogger(__name__)


def run_bot(settings: Settings) -> None:
    prepare_database(settings)
    application = build_application(settings)
    logger.info(
        "Telegram bot polling started for %s allowed user(s)",
        len(settings.allowed_user_ids),
    )
    application.run_polling(allowed_updates=Update.ALL_TYPES)
