# Personal AI intelligence agent

Phase 1 is the foundation: configuration, PostgreSQL, the full database schema, a profile stored in the database, a Gemini client, and a Telegram bot that can show that profile.

Research modules are not included yet. `/jobs`, `/news`, `/opportunities`, `/report`, `/settings`, and `/feedback` answer, and they say which phase adds the real work.

## What you need

- Python 3.12 or newer
- Docker, for PostgreSQL with pgvector
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- Your numeric Telegram user id from [@userinfobot](https://t.me/userinfobot)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
docker compose up -d
alembic upgrade head
```

`.env` is already created for the local database. Fill in the blanks:

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | Already set for the Docker database |
| `GEMINI_API_KEY` | Google AI Studio key |
| `GEMINI_MODEL` | Defaults to `gemini-3.8-flash` |
| `TELEGRAM_BOT_TOKEN` | Token from BotFather |
| `TELEGRAM_ALLOWED_USER_IDS` | Your numeric Telegram user id |

The database password in `docker-compose.yml` is for this local project. Postgres listens on `127.0.0.1:5434` so it does not collide with Postgres already using ports 5432 and 5433.

## Run

Check the database and, when the key is present, Gemini:

```bash
python -m app.main --check
```

Start the bot:

```bash
python -m app.main
```

In Telegram, send `/start` and `/profile`. The profile text comes from the `user_profile` row. A second run does not overwrite edits you make in the database.

Anyone whose user id is not in `TELEGRAM_ALLOWED_USER_IDS` gets “This bot is private.” If you message the bot and are rejected, the process log prints the user id that was refused.

## Edit the profile

The seed file `seeds/profile.json` is loaded only when `user_profile` is empty. After that, change the row:

```bash
docker compose exec db psql -U agent -d personal_ai_agent
```

```sql
UPDATE user_profile
SET full_name = 'Your Name',
    updated_at = now();
```

Then send `/profile` again. No code change is required.

`years_of_experience` is unset on purpose. Add it inside `preferences` when you want the later matcher to use a number.

## Test

```bash
docker compose up -d
pytest
```

Unit tests cover settings, the allow-list, profile text, and Gemini retries. Tests that need Postgres are skipped when Docker is not running.

## Run both services in Docker

After `.env` contains the Telegram token and your user id:

```bash
docker compose --profile app up -d --build
```

The app container overrides `DATABASE_URL` so it talks to the `db` service. It applies migrations on startup, then starts the bot.

## Layout

```
app/
  main.py                  check command and bot startup
  config.py                environment settings
  database/                models, sessions, profile repository, Alembic
  schemas/profile.py       seed validation
  services/                Gemini client behind a small provider interface
  telegram/                auth, commands, profile text
seeds/profile.json         initial profile, inserted once
tests/
```

Phase 2 adds job discovery, matching, and the Telegram job buttons.

## Credentials still unused in Phase 1

`TAVILY_API_KEY` is not required yet. It arrives with web search in Phase 2.
