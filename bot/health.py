"""Глубокая проверка для внешнего мониторинга (UptimeRobot): таблица и webhook бота."""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from aiogram import Bot

from bot.alerts import is_temporary
from bot.config import load_settings
from bot.errors import TemporaryError
from bot.repository import check_sheet_access

CHECK_TIMEOUT_SEC = 10
RETRY_DELAY_SEC = 2
RECENT_ERROR_SEC = 15 * 60
MAX_PENDING_UPDATES = 20
RESULT_CACHE_SEC = 30


class HealthProblem(Exception):
    pass


@dataclass
class HealthReport:
    checks: dict[str, str]
    serious: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(result == "ok" for result in self.checks.values())


_cached: tuple[float, HealthReport] | None = None


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
        # Telegram повторяет доставку сам; застрявшие сообщения ловит проверка очереди выше.
        raise TemporaryError(f"Telegram не может доставить сообщения: {info.last_error_message}")


CHECKS = {"sheet": _check_sheet, "webhook": _check_webhook}


async def _attempt(check) -> tuple[str, bool]:
    """Результат проверки и признак разового сбоя."""
    try:
        await asyncio.wait_for(check(), CHECK_TIMEOUT_SEC)
        return "ok", False
    except asyncio.TimeoutError:
        return f"нет ответа за {CHECK_TIMEOUT_SEC} с", True
    except Exception as exc:
        text = getattr(exc, "user_message", None) or str(exc) or type(exc).__name__
        return text[:300], is_temporary(exc)


async def _run(check) -> tuple[str, bool]:
    result, temporary = await _attempt(check)
    if result != "ok" and temporary:
        await asyncio.sleep(RETRY_DELAY_SEC)
        result, temporary = await _attempt(check)
    return result, temporary


async def run_checks() -> HealthReport:
    """Результат по каждой проверке: "ok" или описание проблемы.

    Разовый сбой перепроверяется один раз. Если он повторился, проверка не "ok"
    (UptimeRobot увидит 503), но в serious не попадает — оповещать не о чем.
    Результат кэшируется на 30 с, чтобы частые запросы не тратили квоту Google.
    """
    global _cached
    now = time.monotonic()
    if _cached and now - _cached[0] < RESULT_CACHE_SEC:
        return _cached[1]
    names = list(CHECKS)
    results = await asyncio.gather(*(_run(CHECKS[n]) for n in names))
    report = HealthReport(
        checks={name: result for name, (result, _) in zip(names, results)},
        serious={
            name: result
            for name, (result, temporary) in zip(names, results)
            if result != "ok" and not temporary
        },
    )
    _cached = (now, report)
    return report
