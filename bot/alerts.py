"""Уведомления владельцу об ошибках в Telegram.

На Vercel Hobby логи хранятся час, поэтому всё, что требует внимания,
дублируется сообщением в личный чат с ботом (ADMIN_CHAT_ID).
"""
from __future__ import annotations

import asyncio
import logging
import time
import traceback

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError

from bot.config import load_settings
from bot.errors import TemporaryError

logger = logging.getLogger(__name__)

REPEAT_SILENCE_SEC = 600
MAX_TEXT = 3500
_last_sent: dict[str, float] = {}

TEMPORARY_ERRORS = (
    TemporaryError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
    asyncio.TimeoutError,
    TimeoutError,
)


def is_temporary(exc: BaseException) -> bool:
    return isinstance(exc, TEMPORARY_ERRORS)


def _describe(exc: BaseException) -> str:
    frames = traceback.extract_tb(exc.__traceback__)[-3:]
    where = "\n".join(f"  {f.filename.rsplit('/', 1)[-1]}:{f.lineno} {f.name}" for f in frames)
    return f"{type(exc).__name__}: {exc}" + (f"\n{where}" if where else "")


async def notify_admin(source: str, exc: BaseException, context: str = "") -> None:
    """Отправить владельцу сообщение об ошибке. Никогда не бросает исключений.

    Разовые сбои Google и Telegram только пишутся в лог: пользователь уже получил
    «повторите», а длительный простой заметит UptimeRobot.
    """
    if is_temporary(exc):
        logger.warning("Разовый сбой (%s), без уведомления: %s", source, exc)
        return
    chat_id = load_settings().admin_chat_id
    if chat_id is None:
        return
    key = f"{source}|{type(exc).__name__}|{exc}"
    now = time.monotonic()
    if now - _last_sent.get(key, -REPEAT_SILENCE_SEC) < REPEAT_SILENCE_SEC:
        return
    _last_sent[key] = now

    text = f"⚠️ Ошибка: {source}\n"
    if context:
        text += f"{context}\n"
    text += f"\n{_describe(exc)}"
    try:
        async with Bot(token=load_settings().bot_token) as bot:
            await bot.send_message(chat_id, text[:MAX_TEXT])
    except Exception:
        logger.warning("Не удалось отправить уведомление об ошибке", exc_info=True)
