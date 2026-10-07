import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from bot import api, health


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    health._cached = None
    monkeypatch.setattr(health, "RETRY_DELAY_SEC", 0)
    sent = []

    async def notify_admin(source, exc, context=""):
        sent.append((source, str(exc)))

    monkeypatch.setattr(api, "notify_admin", notify_admin)
    return sent


def fake_bot(info):
    class FakeBot:
        def __init__(self, token):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get_webhook_info(self):
            return info

    return FakeBot


def webhook_info(**kw):
    base = dict(url="https://x.vercel.app/api/webhook", pending_update_count=0,
                last_error_date=None, last_error_message=None)
    base.update(kw)
    return SimpleNamespace(**base)


async def ok():
    return None


def test_status_ok(monkeypatch, fresh):
    monkeypatch.setattr(health, "check_sheet_access", ok)
    monkeypatch.setattr(health, "Bot", fake_bot(webhook_info()))
    r = TestClient(api.app).get("/api/v1/status")
    assert r.status_code == 200
    assert r.json() == {"ok": True, "checks": {"sheet": "ok", "webhook": "ok"}}
    assert fresh == []


def test_status_reports_problems_and_alerts(monkeypatch, fresh):
    from bot.errors import SheetAccessError

    async def denied():
        raise SheetAccessError("Нет доступа к таблице")

    recent = datetime.now(timezone.utc)
    monkeypatch.setattr(health, "check_sheet_access", denied)
    monkeypatch.setattr(
        health, "Bot",
        fake_bot(webhook_info(last_error_date=recent, last_error_message="Wrong response")),
    )
    r = TestClient(api.app).get("/api/v1/status")
    assert r.status_code == 503
    checks = r.json()["checks"]
    assert checks["sheet"] == "Нет доступа к таблице"
    assert "Wrong response" in checks["webhook"]
    assert fresh == [("мониторинг", "sheet: Нет доступа к таблице")]


def test_old_webhook_error_is_ignored(monkeypatch):
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(health, "check_sheet_access", ok)
    monkeypatch.setattr(health, "Bot", fake_bot(webhook_info(last_error_date=old, last_error_message="x")))
    assert asyncio.run(health.run_checks()).checks["webhook"] == "ok"


def test_wrong_webhook_url(monkeypatch):
    monkeypatch.setattr(health, "check_sheet_access", ok)
    monkeypatch.setattr(health, "Bot", fake_bot(webhook_info(url="")))
    report = asyncio.run(health.run_checks())
    assert "не установлен" in report.checks["webhook"]
    assert "webhook" in report.serious


def test_one_slow_answer_is_rechecked(monkeypatch, fresh):
    calls = []

    async def slow_once():
        calls.append(1)
        if len(calls) == 1:
            raise asyncio.TimeoutError

    monkeypatch.setattr(health, "check_sheet_access", slow_once)
    monkeypatch.setattr(health, "Bot", fake_bot(webhook_info()))
    r = TestClient(api.app).get("/api/v1/status")
    assert r.status_code == 200
    assert len(calls) == 2
    assert fresh == []


def test_repeated_timeout_is_down_but_not_alerted(monkeypatch, fresh):
    async def slow():
        raise asyncio.TimeoutError

    monkeypatch.setattr(health, "check_sheet_access", slow)
    monkeypatch.setattr(health, "Bot", fake_bot(webhook_info()))
    r = TestClient(api.app).get("/api/v1/status")
    assert r.status_code == 503
    assert r.json()["checks"]["sheet"] == "нет ответа за 10 с"
    assert fresh == []


def test_google_hiccup_is_not_alerted(monkeypatch, fresh):
    from bot.errors import SheetNetworkError

    async def down():
        raise SheetNetworkError("Не могу подключиться к таблице")

    monkeypatch.setattr(health, "check_sheet_access", down)
    monkeypatch.setattr(health, "Bot", fake_bot(webhook_info()))
    assert TestClient(api.app).get("/api/v1/status").status_code == 503
    assert fresh == []


def test_recent_delivery_error_alone_is_not_alerted(monkeypatch, fresh):
    recent = datetime.now(timezone.utc)
    monkeypatch.setattr(health, "check_sheet_access", ok)
    monkeypatch.setattr(
        health, "Bot",
        fake_bot(webhook_info(last_error_date=recent, last_error_message="Read timeout expired")),
    )
    r = TestClient(api.app).get("/api/v1/status")
    assert r.status_code == 503
    assert fresh == []


def test_stuck_queue_is_alerted(monkeypatch, fresh):
    monkeypatch.setattr(health, "check_sheet_access", ok)
    monkeypatch.setattr(health, "Bot", fake_bot(webhook_info(pending_update_count=50)))
    assert TestClient(api.app).get("/api/v1/status").status_code == 503
    assert fresh and "50 необработанных" in fresh[0][1]


def test_results_are_cached(monkeypatch):
    calls = []

    async def counting():
        calls.append(1)

    monkeypatch.setattr(health, "check_sheet_access", counting)
    monkeypatch.setattr(health, "Bot", fake_bot(webhook_info()))
    asyncio.run(health.run_checks())
    asyncio.run(health.run_checks())
    assert len(calls) == 1
