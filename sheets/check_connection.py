#!/usr/bin/env python3
"""Проверка доступа к Google Таблице."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sheets.client import (  # noqa: E402
    credentials_path,
    get_client,
    open_spreadsheet,
    service_account_email,
    sheet_url_or_id,
)


def main() -> int:
    print("=== Проверка Google Sheets ===")
    print(f"Ключ: {credentials_path()}")
    try:
        email = service_account_email()
        print(f"Сервисный аккаунт: {email}")
    except Exception as exc:  # noqa: BLE001
        print(f"ОШИБКА ключа: {exc}")
        return 1

    try:
        target = sheet_url_or_id()
        print(f"Таблица: {target}")
    except Exception as exc:  # noqa: BLE001
        print(f"ОШИБКА .env: {exc}")
        print("Добавь в .env строку: SHEET_URL=https://docs.google.com/spreadsheets/d/....")
        return 1

    try:
        get_client()
        ss = open_spreadsheet()
        print(f"OK: открыта «{ss.title}»")
        print("Листы:", ", ".join(ws.title for ws in ss.worksheets()))
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ОШИБКА доступа: {exc}")
        print()
        print("Частая причина: таблице не выдан доступ Редактор на email сервисного аккаунта.")
        print(f"Открой доступ для: {email}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
