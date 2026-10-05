"""Этап 9: маппинг ошибок Sheets, retry 429, логи APPEND."""
from __future__ import annotations

import logging
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from gspread.exceptions import APIError

from bot.errors import SheetAccessError, SheetBusyError, SheetNetworkError
from bot.logging_setup import setup_logging
from bot.repository import Operation, _run_sheets, append_operation


def _api_error(code: int, message: str = "error", status: str = "RESOURCE_EXHAUSTED") -> APIError:
    response = MagicMock()
    response.json.return_value = {
        "error": {"code": code, "message": message, "status": status}
    }
    response.text = message
    return APIError(response)


def test_run_sheets_retries_429_then_busy():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        raise _api_error(429, "Rate limit")

    with patch("bot.repository.time.sleep") as sleep_mock:
        with pytest.raises(SheetBusyError, match="Таблица занята, повторите"):
            _run_sheets(flaky)

    assert calls["n"] == 4  # 1 + 3 retry
    assert [c.args[0] for c in sleep_mock.call_args_list] == [1.0, 2.0, 4.0]


def test_run_sheets_network_message():
    from requests.exceptions import ConnectionError as RequestsConnectionError

    with pytest.raises(SheetNetworkError, match="Не могу подключиться к таблице"):
        _run_sheets(lambda: (_ for _ in ()).throw(RequestsConnectionError("down")))


def test_run_sheets_access_message():
    with pytest.raises(SheetAccessError, match="Нет доступа к таблице"):
        _run_sheets(lambda: (_ for _ in ()).throw(_api_error(403, "The caller does not have permission")))


@pytest.mark.asyncio
async def test_append_logs_line(caplog):
    op = Operation(
        date=date(2026, 10, 4),
        brand="Сарма классик",
        flavor="Буратино",
        pack="200 г",
        qty=10,
        author="Федя",
        kind="Приход",
        comment="@x id=123456789",
    )

    with patch("bot.repository._append_operation_sync", return_value=(9, "Н-004")):
        with caplog.at_level(logging.INFO, logger="bot.repository"):
            row, doc = await append_operation(op, tg_user_id=123456789)

    assert row == 9 and doc == "Н-004"
    assert any(
        "APPEND row=9 Приход Сарма классик/Буратино/200 г qty=10 by=Федя tg=123456789" in r.message
        for r in caplog.records
    )


def test_setup_logging_writes_file(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_file = log_dir / "bot.log"
    monkeypatch.setattr("bot.logging_setup.LOG_DIR", log_dir)
    monkeypatch.setattr("bot.logging_setup.LOG_FILE", log_file)

    # Сбрасываем root handlers, чтобы тест был изолированным.
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)

    setup_logging()
    logging.getLogger("test_stage9").info("stage9-ok")
    for h in root.handlers:
        h.flush()

    assert log_file.exists()
    assert "stage9-ok" in log_file.read_text(encoding="utf-8")
