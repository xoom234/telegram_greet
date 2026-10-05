"""Connect to Google Sheets via service account."""
from __future__ import annotations

import os
import re
from pathlib import Path

import gspread
from dotenv import load_dotenv
from google.oauth2.service_account import Credentials

ROOT = Path(__file__).resolve().parents[1]
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _load_env() -> None:
    load_dotenv(ROOT / ".env")
    load_dotenv(ROOT / "env")


def credentials_path() -> Path:
    _load_env()
    raw = os.getenv("GOOGLE_CREDENTIALS", "credentials/credentials.json")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def sheet_url_or_id() -> str:
    _load_env()
    value = (os.getenv("SHEET_URL") or os.getenv("SHEET_ID") or "").strip()
    if not value:
        raise RuntimeError(
            "Не задан SHEET_URL или SHEET_ID в файле .env"
        )
    return value


def extract_spreadsheet_id(url_or_id: str) -> str:
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url_or_id)
    if match:
        return match.group(1)
    if re.fullmatch(r"[a-zA-Z0-9-_]+", url_or_id):
        return url_or_id
    raise RuntimeError(f"Не удалось извлечь ID таблицы из: {url_or_id}")


def get_client() -> gspread.Client:
    path = credentials_path()
    if not path.exists():
        raise FileNotFoundError(
            f"Нет файла ключей: {path}\n"
            "Скачай JSON сервисного аккаунта и положи как credentials/credentials.json"
        )
    creds = Credentials.from_service_account_file(str(path), scopes=SCOPES)
    return gspread.authorize(creds)


def open_spreadsheet(url_or_id: str | None = None) -> gspread.Spreadsheet:
    client = get_client()
    target = url_or_id or sheet_url_or_id()
    if "docs.google.com" in target:
        return client.open_by_url(target)
    return client.open_by_key(extract_spreadsheet_id(target))


def service_account_email() -> str:
    import json

    path = credentials_path()
    data = json.loads(path.read_text(encoding="utf-8"))
    return data["client_email"]
