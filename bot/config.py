"""Конфигурация бота из .env."""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

DEFAULT_WEBAPP_URL = "https://telegram-greet-omega.vercel.app/"


@dataclass(frozen=True)
class Settings:
    bot_token: str
    allowed_user_ids: frozenset[int]
    default_author: str
    cache_ttl: int
    webapp_url: str = DEFAULT_WEBAPP_URL
    admin_chat_id: int | None = None


def _parse_ids(raw: str) -> frozenset[int]:
    ids: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.add(int(part))
        except ValueError:
            logger.warning("Пропущен некорректный ALLOWED_USER_IDS: %r", part)
    return frozenset(ids)


@lru_cache(maxsize=1)
def load_settings() -> Settings:
    load_dotenv(override=True)
    token = os.getenv("BOT_TOKEN", "").strip()
    allowed = _parse_ids(os.getenv("ALLOWED_USER_IDS", ""))
    if not allowed:
        logger.warning(
            "ALLOWED_USER_IDS пуст — бот отвечает всем. "
            "Рекомендуется указать свой Telegram id."
        )
    default_author = os.getenv("DEFAULT_AUTHOR", "Федор").strip() or "Федор"
    try:
        cache_ttl = max(0, int(os.getenv("CACHE_TTL_SECONDS", "300").strip() or "300"))
    except ValueError:
        cache_ttl = 300
    return Settings(
        bot_token=token,
        allowed_user_ids=allowed,
        default_author=default_author,
        cache_ttl=cache_ttl,
        webapp_url=os.getenv("WEBAPP_URL", "").strip() or DEFAULT_WEBAPP_URL,
        admin_chat_id=_parse_admin(os.getenv("ADMIN_CHAT_ID", "")),
    )


def _parse_admin(raw: str) -> int | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError:
        logger.warning("Некорректный ADMIN_CHAT_ID: %r — уведомления об ошибках выключены", raw)
        return None
