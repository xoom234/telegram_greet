#!/usr/bin/env python3
"""Telegram-бот: спрашивает имя и присылает приветствие, работает бесконечно (polling)."""

import asyncio
import logging
import os
import sys

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

ASK_NAME = "Как вас зовут?"
EMPTY_NAME = "Имя не может быть пустым. Попробуйте ещё раз."


async def cmd_start(message: Message) -> None:
    await message.answer(ASK_NAME)


async def greet_user(message: Message) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(EMPTY_NAME)
        return

    await message.answer(f"Привет, {name}!")
    await message.answer(ASK_NAME)


async def ask_again(message: Message) -> None:
    await message.answer(ASK_NAME)


async def main() -> None:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        print("Задайте BOT_TOKEN в файле .env (см. .env.example).", file=sys.stderr)
        sys.exit(1)

    bot = Bot(token=token)
    dp = Dispatcher()
    dp.message.register(cmd_start, CommandStart())
    dp.message.register(greet_user, F.text)
    dp.message.register(ask_again)

    print("Бот запущен. Остановка: Ctrl+C")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nБот остановлен.")
