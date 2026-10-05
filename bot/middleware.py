"""Middleware доступа по ALLOWED_USER_IDS."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.config import load_settings


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        settings = load_settings()
        allowed = settings.allowed_user_ids
        if not allowed:
            return await handler(event, data)

        user = None
        if isinstance(event, Message):
            user = event.from_user
        elif isinstance(event, CallbackQuery):
            user = event.from_user

        if user is None or user.id not in allowed:
            uid = user.id if user else "?"
            text = (
                "Нет доступа. Напишите владельцу бота ваш id: "
                f"{uid}"
            )
            if isinstance(event, Message):
                await event.answer(text)
            elif isinstance(event, CallbackQuery):
                if event.message:
                    await event.message.answer(text)
                await event.answer()
            return None

        return await handler(event, data)
