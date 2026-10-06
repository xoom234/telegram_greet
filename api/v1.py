"""Vercel-функция: HTTP API для Telegram Mini App (/api/v1/*)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bot.api import app  # noqa: E402,F401
from bot.logging_setup import setup_logging  # noqa: E402

setup_logging()
