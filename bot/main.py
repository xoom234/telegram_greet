"""Точка входа бота склада."""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from bot.config import load_settings
from bot.handlers.common import register_common_handlers
from bot.handlers.movement import register_movement_handlers
from bot.handlers.reports import register_report_handlers
from bot.logging_setup import setup_logging
from bot.middleware import AccessMiddleware

logger = logging.getLogger(__name__)


async def run() -> None:
    load_dotenv(override=True)
    setup_logging()
    # сброс кэша settings после обновления .env
    load_settings.cache_clear()
    settings = load_settings()

    token = settings.bot_token
    if not token or "your_telegram" in token:
        print("Задайте настоящий BOT_TOKEN в файле .env", file=sys.stderr)
        sys.exit(1)

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())

    register_common_handlers(dp)
    register_movement_handlers(dp)
    register_report_handlers(dp)

    me = await bot.get_me()
    logger.info("Бот запущен как @%s", me.username)
    print(f"Бот запущен: @{me.username}. Остановка: Ctrl+C")
    await dp.start_polling(bot)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\nБот остановлен.")


if __name__ == "__main__":
    main()
