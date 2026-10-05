"""Слой доступа к Google Таблице. Единственное место вызовов gspread."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal, TypeVar

from gspread.exceptions import APIError, SpreadsheetNotFound
from requests.exceptions import ConnectionError as RequestsConnectionError
from requests.exceptions import Timeout as RequestsTimeout

from bot.errors import (
    SheetAccessError,
    SheetBusyError,
    SheetNetworkError,
    sheet_access_message,
)
from sheets.client import open_spreadsheet, service_account_email

logger = logging.getLogger(__name__)

SHEET_MOVEMENTS = "Накладные"
SHEET_BRANDS = "Бренды"
SHEET_PACKS = "Фасовки"

BRANDS_RANGE = "A4:A103"
PACKS_RANGE = "A4:A23"
MOVEMENTS_RANGE = "A4:I2000"

DOC_NO_RE = re.compile(r"^Н-(\d+)$", re.IGNORECASE)

# Retry при 429: 1 с → 2 с → 4 с, затем «Таблица занята, повторите»
_RETRY_DELAYS_SEC = (1.0, 2.0, 4.0)

_write_lock = asyncio.Lock()

_cache_brands: tuple[float, list[str]] | None = None
_cache_packs: tuple[float, list[str]] | None = None
_cache_movements: tuple[float, list["MovementRow"]] | None = None

T = TypeVar("T")


@dataclass
class Operation:
    date: date
    brand: str
    flavor: str
    pack: str
    qty: int
    author: str
    kind: Literal["Приход", "Расход"]
    comment: str = ""


@dataclass
class MovementRow:
    row_number: int
    date: str
    doc_no: str
    brand: str
    flavor: str
    pack: str
    qty: int
    kind: str
    author: str
    comment: str


def _cache_ttl() -> int:
    raw = os.getenv("CACHE_TTL_SECONDS", "300").strip()
    try:
        return max(0, int(raw))
    except ValueError:
        return 300


def _norm(value: object) -> str:
    return str(value or "").strip()


def _cache_get(entry: tuple[float, list] | None) -> list | None:
    if entry is None:
        return None
    ts, data = entry
    if time.monotonic() - ts > _cache_ttl():
        return None
    return data


def _invalidate_movements_cache() -> None:
    global _cache_movements
    _cache_movements = None


def _invalidate_brands_cache() -> None:
    global _cache_brands
    _cache_brands = None


def _is_rate_limit(exc: APIError) -> bool:
    if exc.code == 429:
        return True
    if exc.code == 403:
        errors = exc.error.get("errors") or []
        if errors and errors[0].get("domain") == "usageLimits":
            return True
        message = str(exc.error.get("message", "")).lower()
        if "quota" in message or "rate" in message:
            return True
    return False


def _is_access_denied(exc: BaseException) -> bool:
    if isinstance(exc, SpreadsheetNotFound):
        return True
    if isinstance(exc, APIError):
        if exc.code in (401, 403) and not _is_rate_limit(exc):
            return True
        status = str(exc.error.get("status", "")).upper()
        if status in {"PERMISSION_DENIED", "UNAUTHENTICATED"}:
            return True
    text = str(exc).lower()
    return "permission" in text or ("access" in text and "denied" in text)


def _service_email_safe() -> str | None:
    try:
        return service_account_email()
    except Exception:
        return None


def _map_sheets_error(exc: BaseException) -> Exception:
    if isinstance(exc, APIError) and _is_rate_limit(exc):
        return SheetBusyError("Таблица занята, повторите")
    if _is_access_denied(exc):
        return SheetAccessError(sheet_access_message(_service_email_safe()))
    if isinstance(
        exc,
        (RequestsConnectionError, RequestsTimeout, ConnectionError, TimeoutError),
    ):
        return SheetNetworkError("Не могу подключиться к таблице")
    if isinstance(exc, OSError) and not isinstance(exc, FileNotFoundError):
        return SheetNetworkError("Не могу подключиться к таблице")
    return exc


def _run_sheets(fn: Callable[[], T]) -> T:
    """Вызов Google Sheets с retry на 429 и понятными ошибками."""
    attempt = 0
    while True:
        try:
            return fn()
        except APIError as exc:
            if _is_rate_limit(exc) and attempt < len(_RETRY_DELAYS_SEC):
                delay = _RETRY_DELAYS_SEC[attempt]
                logger.warning(
                    "Google API 429/лимит, повтор через %.0f с (попытка %s/%s)",
                    delay,
                    attempt + 1,
                    len(_RETRY_DELAYS_SEC),
                )
                time.sleep(delay)
                attempt += 1
                continue
            mapped = _map_sheets_error(exc)
            if isinstance(mapped, SheetBusyError):
                logger.error("Google API лимит исчерпан после retry: %s", exc)
            elif isinstance(mapped, SheetAccessError):
                logger.exception("Нет доступа к Google Таблице", exc_info=exc)
            else:
                logger.exception("Ошибка Google Sheets API", exc_info=exc)
            raise mapped from exc
        except SpreadsheetNotFound as exc:
            logger.exception("Таблица не найдена / нет доступа", exc_info=exc)
            raise SheetAccessError(sheet_access_message(_service_email_safe())) from exc
        except FileNotFoundError:
            raise
        except (RequestsConnectionError, RequestsTimeout, ConnectionError, TimeoutError) as exc:
            logger.exception("Нет сети при обращении к Google Sheets", exc_info=exc)
            raise SheetNetworkError("Не могу подключиться к таблице") from exc
        except OSError as exc:
            logger.exception("Нет сети при обращении к Google Sheets", exc_info=exc)
            raise SheetNetworkError("Не могу подключиться к таблице") from exc


def _worksheet(title: str):
    return _run_sheets(lambda: open_spreadsheet().worksheet(title))


def next_free_row(ws) -> int:
    brands_col = ws.col_values(3)  # колонка C
    # первые 3 строки — заголовки
    for idx in range(3, len(brands_col)):
        if not brands_col[idx].strip():
            return idx + 1
    return len(brands_col) + 1


def next_doc_no(ws=None) -> str:
    def _compute(sheet) -> str:
        numbers: list[int] = []
        for raw in sheet.col_values(2)[3:]:  # колонка B, без заголовков
            match = DOC_NO_RE.match(_norm(raw))
            if match:
                numbers.append(int(match.group(1)))
        nxt = max(numbers, default=0) + 1
        return f"Н-{nxt:03d}"

    if ws is not None:
        return _compute(ws)
    return _run_sheets(
        lambda: _compute(open_spreadsheet().worksheet(SHEET_MOVEMENTS))
    )


def _parse_qty(raw: str) -> int:
    text = _norm(raw)
    if not text:
        return 0
    try:
        return int(float(text.replace(",", ".")))
    except ValueError:
        return 0


def _load_brands_sync() -> list[str]:
    global _cache_brands
    cached = _cache_get(_cache_brands)
    if cached is not None:
        return list(cached)

    def _do() -> list[str]:
        ws = open_spreadsheet().worksheet(SHEET_BRANDS)
        values = ws.get(BRANDS_RANGE) or []
        return [_norm(row[0]) for row in values if row and _norm(row[0])]

    brands = _run_sheets(_do)
    _cache_brands = (time.monotonic(), brands)
    return list(brands)


def _load_packs_sync() -> list[str]:
    global _cache_packs
    cached = _cache_get(_cache_packs)
    if cached is not None:
        return list(cached)

    def _do() -> list[str]:
        ws = open_spreadsheet().worksheet(SHEET_PACKS)
        values = ws.get(PACKS_RANGE) or []
        return [_norm(row[0]) for row in values if row and _norm(row[0])]

    packs = _run_sheets(_do)
    _cache_packs = (time.monotonic(), packs)
    return list(packs)


def _read_movements_sync() -> list[MovementRow]:
    global _cache_movements
    cached = _cache_get(_cache_movements)
    if cached is not None:
        return list(cached)

    def _do() -> list[list]:
        ws = open_spreadsheet().worksheet(SHEET_MOVEMENTS)
        return ws.get(MOVEMENTS_RANGE) or []

    values = _run_sheets(_do)
    rows: list[MovementRow] = []
    for offset, raw in enumerate(values):
        cells = list(raw) + [""] * (9 - len(raw))
        brand = _norm(cells[2])
        if not brand:
            continue
        row_number = 4 + offset
        rows.append(
            MovementRow(
                row_number=row_number,
                date=_norm(cells[0]),
                doc_no=_norm(cells[1]),
                brand=brand,
                flavor=_norm(cells[3]),
                pack=_norm(cells[4]),
                qty=_parse_qty(cells[5]),
                kind=_norm(cells[6]),
                author=_norm(cells[7]),
                comment=_norm(cells[8]),
            )
        )
    _cache_movements = (time.monotonic(), rows)
    return list(rows)


def _append_operation_sync(op: Operation) -> tuple[int, str]:
    def _do() -> tuple[int, str]:
        ws = open_spreadsheet().worksheet(SHEET_MOVEMENTS)
        row = next_free_row(ws)
        doc_no = next_doc_no(ws)
        values = [[
            op.date.strftime("%d.%m.%Y"),
            doc_no,
            _norm(op.brand),
            _norm(op.flavor),
            _norm(op.pack),
            int(op.qty),
            _norm(op.kind),
            _norm(op.author),
            _norm(op.comment),
        ]]
        # gspread 6.x: values первым аргументом, range — вторым
        ws.update(
            values,
            f"A{row}:I{row}",
            value_input_option="USER_ENTERED",
        )
        return row, doc_no

    row, doc_no = _run_sheets(_do)
    _invalidate_movements_cache()
    return row, doc_no


def _add_brand_sync(name: str) -> int:
    cleaned = _norm(name)
    if not cleaned:
        raise ValueError("Пустое имя бренда")

    def _do() -> int:
        ws = open_spreadsheet().worksheet(SHEET_BRANDS)
        col = ws.col_values(1)
        existing = {_norm(v).casefold() for v in col[3:]}
        if cleaned.casefold() in existing:
            for idx in range(3, len(col)):
                if _norm(col[idx]).casefold() == cleaned.casefold():
                    return idx + 1
            return len(col)

        # A4:A103 — ищем первую пустую ячейку
        for idx in range(3, max(len(col), 103)):
            current = _norm(col[idx]) if idx < len(col) else ""
            if not current:
                row = idx + 1
                ws.update([[cleaned]], f"A{row}", value_input_option="USER_ENTERED")
                return row

        raise RuntimeError("Справочник брендов заполнен (A4:A103)")

    row = _run_sheets(_do)
    _invalidate_brands_cache()
    return row


async def load_brands() -> list[str]:
    return await asyncio.to_thread(_load_brands_sync)


async def load_packs() -> list[str]:
    return await asyncio.to_thread(_load_packs_sync)


async def read_movements() -> list[MovementRow]:
    return await asyncio.to_thread(_read_movements_sync)


async def append_operation(
    op: Operation,
    *,
    tg_user_id: int | None = None,
) -> tuple[int, str]:
    async with _write_lock:
        row, doc_no = await asyncio.to_thread(_append_operation_sync, op)
    tg = tg_user_id if tg_user_id is not None else "-"
    logger.info(
        "APPEND row=%s %s %s/%s/%s qty=%s by=%s tg=%s",
        row,
        _norm(op.kind),
        _norm(op.brand),
        _norm(op.flavor),
        _norm(op.pack),
        int(op.qty),
        _norm(op.author),
        tg,
    )
    return row, doc_no


async def add_brand(name: str) -> int:
    async with _write_lock:
        return await asyncio.to_thread(_add_brand_sync, name)


async def _smoke_test() -> None:
    """Критерий этапа 2: тестовая строка в первой пустой строке."""
    brands = await load_brands()
    packs = await load_packs()
    before = await read_movements()
    print(f"Брендов: {len(brands)}, фасовок: {len(packs)}, движений: {len(before)}")

    op = Operation(
        date=date(2026, 10, 4),
        brand="Сарма классик",
        flavor="Буратино",
        pack="200 г",
        qty=1,
        author="Федор",
        kind="Приход",
        comment="bot-repo-smoke-test",
    )
    row, doc_no = await append_operation(op)
    print(f"Записано: строка {row}, накладная {doc_no}")

    after = await read_movements()
    written = next((r for r in after if r.row_number == row), None)
    if written is None:
        raise RuntimeError(f"Строка {row} не прочиталась обратно")
    print(
        f"Проверка: {written.date} {written.doc_no} {written.brand}/"
        f"{written.flavor}/{written.pack} qty={written.qty} {written.kind}"
    )

    ws = await asyncio.to_thread(_worksheet, SHEET_MOVEMENTS)
    kn = await asyncio.to_thread(ws.get, f"K{row}:N{row}")
    print(f"Формулы K–N: {kn}")


if __name__ == "__main__":
    asyncio.run(_smoke_test())
