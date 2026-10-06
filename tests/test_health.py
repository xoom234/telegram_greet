import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from bot import api, health


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    health._cached = None
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
    assert fresh and fresh[0][0] == "мониторинг"


def test_old_webhook_error_is_ignored(monkeypatch):
    old = datetime(2026, 1, 1, tzinfo=timezone.utc)
    monkeypatch.setattr(health, "check_sheet_access", ok)
    monkeypatch.setattr(health, "Bot", fake_bot(webhook_info(last_error_date=old, last_error_message="x")))
    assert asyncio.run(health.run_checks())["webhook"] == "ok"


def test_wrong_webhook_url(monkeypatch):
    monkeypatch.setattr(health, "check_sheet_access", ok)
    monkeypatch.setattr(health, "Bot", fake_bot(webhook_info(url="")))
    assert "не установлен" in asyncio.run(health.run_checks())["webhook"]


def test_results_are_cached(monkeypatch):
    calls = []

    async def counting():
        calls.append(1)

    monkeypatch.setattr(health, "check_sheet_access", counting)
    monkeypatch.setattr(health, "Bot", fake_bot(webhook_info()))
    asyncio.run(health.run_checks())
    asyncio.run(health.run_checks())
    assert len(calls) == 1
