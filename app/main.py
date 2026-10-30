"""Process entrypoint for the check command and the Telegram bot."""

from __future__ import annotations

import argparse
import logging

from sqlalchemy.exc import OperationalError

from app.config import Settings, get_settings
from app.database.bootstrap import prepare_database
from app.logging_config import setup_logging
from app.services.gemini_service import GeminiClient
from app.telegram.bot import run_bot
from app.telegram.formatting import format_profile

logger = logging.getLogger(__name__)


def run_checks(settings: Settings) -> int:
    try:
        profile = prepare_database(settings)
    except OperationalError:
        print("Could not connect to PostgreSQL.")
        print("Start the database with: docker compose up -d")
        print("Then confirm DATABASE_URL in .env matches docker-compose.yml.")
        return 1

    print(format_profile(profile))
    print("---")

    if settings.gemini_api_key:
        try:
            GeminiClient(settings.gemini_api_key, settings.gemini_model).ping()
        except Exception:
            logger.exception("Gemini check failed")
            print("Gemini check failed. Confirm GEMINI_API_KEY and GEMINI_MODEL.")
            return 1
        print(f"Gemini responded using model {settings.gemini_model}.")
    else:
        print("GEMINI_API_KEY is not set. Skipping the Gemini check.")

    if settings.telegram_bot_token and settings.allowed_user_ids:
        print("Telegram token and allowed user id are set.")
    elif not settings.telegram_bot_token:
        print("TELEGRAM_BOT_TOKEN is not set. The bot will not start until it is set.")
    else:
        print("TELEGRAM_ALLOWED_USER_IDS is not set. The bot will not start until it is set.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="personal-ai-agent")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify the database, seed the profile if needed, and ping Gemini when a key is set.",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    setup_logging(settings.log_level)
    if args.check:
        return run_checks(settings)
    run_bot(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
