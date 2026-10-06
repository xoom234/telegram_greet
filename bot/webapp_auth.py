"""Проверка Telegram Mini App initData (заголовок Authorization: tma <initData>)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from aiogram.utils.web_app import WebAppUser, safe_parse_webapp_init_data

MAX_INIT_DATA_AGE = timedelta(hours=24)


class AuthError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def authenticate(
    authorization: str | None,
    *,
    bot_token: str,
    allowed_user_ids: frozenset[int],
    now: datetime | None = None,
) -> WebAppUser:
    scheme, _, init_data = (authorization or "").partition(" ")
    if scheme.lower() != "tma" or not init_data.strip():
        raise AuthError(401, "Откройте приложение из Telegram")
    try:
        data = safe_parse_webapp_init_data(bot_token, init_data.strip())
    except ValueError:
        raise AuthError(401, "Подпись Telegram не прошла проверку") from None
    if data.user is None:
        raise AuthError(401, "Telegram не передал пользователя")

    now = now or datetime.now(timezone.utc)
    auth_date = data.auth_date
    if auth_date.tzinfo is None:
        auth_date = auth_date.replace(tzinfo=timezone.utc)
    if now - auth_date > MAX_INIT_DATA_AGE:
        raise AuthError(401, "Сессия устарела, откройте приложение заново")

    if allowed_user_ids and data.user.id not in allowed_user_ids:
        raise AuthError(403, f"Нет доступа. Напишите владельцу бота ваш id: {data.user.id}")
    return data.user
