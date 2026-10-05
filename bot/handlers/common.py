"""Общие хендлеры: /start, /help и глобальная обработка ошибок."""
from __future__ import annotations

import logging
import re

from aiogram import Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import ErrorEvent, Message

from bot.errors import UserFacingError

logger = logging.getLogger(__name__)

GENERIC_ERROR_TEXT = "Произошла ошибка. Попробуйте позже или повторите команду."

HELP_TEXT = (
    "Бот склада табака\n\n"
    "Команды:\n"
    "/приход 04.10.2026 Сарма классик Буратино 200 г 10 Федя\n"
    "/расход 04.10.2026 Сарма классик Буратино 200 г 5 Федя\n"
    "/остатки — все остатки\n"
    "/остатки Сарма классик — по бренду\n"
    "/инфо 04.10.2026 — кто что внёс за день\n\n"
    "Алиасы: /in /out /stock /info"
)


async def cmd_start(message: Message) -> None:
    await message.answer("Бот склада запущен.\nНапишите /help — список команд.")


async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


async def on_error(event: ErrorEvent) -> bool:
    """Глобальный errors handler: пользователю — короткий текст, в лог — трейсбек."""
    exc = event.exception
    logger.exception("Необработанное исключение в хендлере", exc_info=exc)

    if isinstance(exc, UserFacingError):
        text = exc.user_message
    else:
        text = GENERIC_ERROR_TEXT

    update = event.update
    try:
        if update.message:
            await update.message.answer(text)
        elif update.callback_query and update.callback_query.message:
            await update.callback_query.message.answer(text)
            await update.callback_query.answer()
        elif update.callback_query:
            await update.callback_query.answer(text, show_alert=True)
    except Exception:
        logger.exception("Не удалось отправить сообщение об ошибке пользователю")

    return True


def register_common_handlers(dp: Dispatcher) -> None:
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(
        cmd_help,
        F.text.regexp(re.compile(r"^/(help|помощь)(\s|$)", re.I)),
    )
    dp.errors.register(on_error)


def register_error_handlers(dp: Dispatcher) -> None:
    """Совместимость со старым именем."""
    register_common_handlers(dp)
