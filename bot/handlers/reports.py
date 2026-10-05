"""Команды /остатки и /инфо."""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from aiogram import Dispatcher, F
from aiogram.types import Message

from bot.formatting import (
    compute_balances,
    format_info_report,
    format_stock_report,
    split_telegram_messages,
)
from bot.parsing import strip_command
from bot.repository import load_brands, read_movements

logger = logging.getLogger(__name__)

OSTATKI_RE = re.compile(r"^/(остатки|ostatki|stock)(@\w+)?(\s|$)", re.I)
INFO_RE = re.compile(r"^/(инфо|info)(@\w+)?(\s|$)", re.I)


def _parse_day(raw: str, today: date | None = None) -> date | None:
    today = today or date.today()
    text = (raw or "").strip()
    if not text:
        return today
    low = text.casefold()
    if low in {"сегодня", "today"}:
        return today
    if low in {"вчера", "yesterday"}:
        from datetime import timedelta

        return today - timedelta(days=1)
    try:
        return datetime.strptime(text, "%d.%m.%Y").date()
    except ValueError:
        return None


async def _resolve_brand(query: str) -> str | None:
    brands = await load_brands()
    q = query.strip()
    if not q:
        return None
    for b in brands:
        if b.casefold() == q.casefold():
            return b
    # prefix / contains
    hits = [b for b in brands if q.casefold() in b.casefold()]
    if len(hits) == 1:
        return hits[0]
    # longest prefix match
    ordered = sorted(brands, key=len, reverse=True)
    for b in ordered:
        if q.casefold().startswith(b.casefold()) or b.casefold().startswith(
            q.casefold()
        ):
            return b
    return None


async def cmd_ostatki(message: Message) -> None:
    args = strip_command(message.text or "")
    movements = await read_movements()
    balances = compute_balances(movements)

    brand_filter = None
    if args:
        brand_filter = await _resolve_brand(args)
        if brand_filter is None:
            brands = await load_brands()
            hints = ", ".join(brands[:8])
            await message.answer(
                f"Бренд «{args}» не найден.\nПримеры: {hints}"
            )
            return

    text = format_stock_report(balances, brand_filter=brand_filter)
    for chunk in split_telegram_messages(text):
        await message.answer(chunk)


async def cmd_info(message: Message) -> None:
    args = strip_command(message.text or "")
    day = _parse_day(args)
    if day is None:
        await message.answer(
            "Непонятная дата. Пример: /инфо 04.10.2026\n"
            "Без аргумента — сегодняшний день."
        )
        return
    movements = await read_movements()
    text = format_info_report(movements, day=day)
    for chunk in split_telegram_messages(text):
        await message.answer(chunk)


def register_report_handlers(dp: Dispatcher) -> None:
    dp.message.register(cmd_ostatki, F.text.regexp(OSTATKI_RE))
    dp.message.register(cmd_info, F.text.regexp(INFO_RE))
