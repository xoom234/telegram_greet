import pytest

from bot import alerts
from bot.config import Settings

pytestmark = pytest.mark.asyncio


class FakeBot:
    sent: list = []

    def __init__(self, token):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def send_message(self, chat_id, text):
        FakeBot.sent.append((chat_id, text))


@pytest.fixture
def setup(monkeypatch):
    FakeBot.sent = []
    alerts._last_sent.clear()
    settings = {"admin": 1453663021}
    monkeypatch.setattr(alerts, "Bot", FakeBot)
    monkeypatch.setattr(
        alerts,
        "load_settings",
        lambda: Settings("t", frozenset(), "Федор", 300, admin_chat_id=settings["admin"]),
    )
    return settings


def boom(message="таблица недоступна"):
    try:
        raise RuntimeError(message)
    except RuntimeError as exc:
        return exc


async def test_sends_error_with_context(setup):
    await alerts.notify_admin("приложение", boom(), "POST /api/v1/operations")
    chat_id, text = FakeBot.sent[0]
    assert chat_id == 1453663021
    assert "Ошибка: приложение" in text
    assert "POST /api/v1/operations" in text
    assert "RuntimeError: таблица недоступна" in text
    assert "test_alerts.py" in text


async def test_same_error_is_not_repeated(setup):
    await alerts.notify_admin("бот", boom())
    await alerts.notify_admin("бот", boom())
    await alerts.notify_admin("бот", boom("другая"))
    assert len(FakeBot.sent) == 2


async def test_temporary_failures_are_not_sent(setup):
    import asyncio

    from aiogram.exceptions import TelegramNetworkError

    from bot.errors import SheetAccessError, SheetBusyError, SheetNetworkError

    for exc in (
        SheetBusyError("Таблица занята, повторите"),
        SheetNetworkError("Не могу подключиться к таблице"),
        TelegramNetworkError(method=None, message="timeout"),
        asyncio.TimeoutError(),
    ):
        await alerts.notify_admin("бот", exc)
    assert FakeBot.sent == []

    await alerts.notify_admin("бот", SheetAccessError("Нет доступа к таблице"))
    assert len(FakeBot.sent) == 1


async def test_disabled_without_admin(setup):
    setup["admin"] = None
    await alerts.notify_admin("бот", boom())
    assert FakeBot.sent == []


async def test_telegram_failure_is_swallowed(setup, monkeypatch):
    class Broken(FakeBot):
        async def send_message(self, chat_id, text):
            raise RuntimeError("telegram down")

    monkeypatch.setattr(alerts, "Bot", Broken)
    await alerts.notify_admin("бот", boom())
