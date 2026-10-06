"""Глубокая проверка для внешнего мониторинга (UptimeRobot): таблица и webhook бота."""
from __future__ import annotations

import asyncio
import time

from aiogram import Bot

from bot.config import load_settings
from bot.repository import check_sheet_access

CHECK_TIMEOUT_SEC = 10
RECENT_ERROR_SEC = 15 * 60
MAX_PENDING_UPDATES = 20
RESULT_CACHE_SEC = 30

_cached: tuple[float, dict[str, str]] | None = None


class HealthProblem(Exception):
    pass


async def _check_sheet() -> None:
    await check_sheet_access()


async def _check_webhook() -> None:
    async with Bot(token=load_settings().bot_token) as bot:
        info = await bot.get_webhook_info()
    if not info.url.endswith("/api/webhook"):
        raise HealthProblem(f"webhook не установлен или указывает не туда: {info.url or 'пусто'}")
    if info.pending_update_count > MAX_PENDING_UPDATES:
        raise HealthProblem(f"в очереди {info.pending_update_count} необработанных сообщений")
    if info.last_error_date and time.time() - info.last_error_date.timestamp() < RECENT_ERROR_SEC:
        raise HealthProblem(f"Telegram не может доставить сообщения: {info.last_error_message}")


CHECKS = {"sheet": _check_sheet, "webhook": _check_webhook}


async def _run(check) -> str:
    try:
        await asyncio.wait_for(check(), CHECK_TIMEOUT_SEC)
        return "ok"
    except asyncio.TimeoutError:
        return "нет ответа за 10 с"
    except Exception as exc:
        text = getattr(exc, "user_message", None) or str(exc) or type(exc).__name__
        return text[:300]


async def run_checks() -> dict[str, str]:
    """Результат по каждой проверке: "ok" или описание проблемы.

    Результат кэшируется на 30 с, чтобы частые запросы не тратили квоту Google.
    """
    global _cached
    now = time.monotonic()
    if _cached and now - _cached[0] < RESULT_CACHE_SEC:
        return _cached[1]
    names = list(CHECKS)
    results = await asyncio.gather(*(_run(CHECKS[n]) for n in names))
    checks = dict(zip(names, results))
    _cached = (now, checks)
    return checks
