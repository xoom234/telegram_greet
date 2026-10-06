"""Общая логика бота и Mini App API поверх bot/repository.py."""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from bot.repository import load_brands

DEFAULT_TIMEZONE = "Europe/Samara"


def today() -> date:
    """Сегодня по часовому поясу склада: на хостинге системное время — UTC."""
    tz_name = os.getenv("APP_TIMEZONE", DEFAULT_TIMEZONE).strip() or DEFAULT_TIMEZONE
    return datetime.now(ZoneInfo(tz_name)).date()


def parse_day(raw: str | None, base: date | None = None) -> date | None:
    """dd.mm.yyyy, yyyy-mm-dd, «сегодня», «вчера»; пусто — сегодня."""
    base = base or today()
    text = (raw or "").strip()
    if not text:
        return base
    low = text.casefold()
    if low in {"сегодня", "today"}:
        return base
    if low in {"вчера", "yesterday"}:
        return base - timedelta(days=1)
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


async def resolve_brand(query: str) -> str | None:
    """Каноническое имя бренда из справочника: точное, по вхождению или по префиксу."""
    brands = await load_brands()
    q = query.strip()
    if not q:
        return None
    for b in brands:
        if b.casefold() == q.casefold():
            return b
    hits = [b for b in brands if q.casefold() in b.casefold()]
    if len(hits) == 1:
        return hits[0]
    for b in sorted(brands, key=len, reverse=True):
        if q.casefold().startswith(b.casefold()) or b.casefold().startswith(q.casefold()):
            return b
    return None


def normalize_pack(raw: str, packs: list[str]) -> str | None:
    """«200», «200г», «200 г» → «200 г» из справочника фасовок."""
    m = re.fullmatch(r"\s*(\d+)\s*(г|гр)?\.?\s*", raw or "", re.IGNORECASE)
    if not m:
        return None
    grams = m.group(1)
    for p in packs:
        pm = re.match(r"\s*(\d+)", p)
        if pm and pm.group(1) == grams:
            return p
    return None


def stock_of(
    balances: dict[tuple[str, str, str], int],
    brand: str,
    flavor: str,
    pack: str,
) -> int:
    """Остаток позиции без учёта регистра; нет позиции — 0."""
    exact = balances.get((brand, flavor, pack))
    if exact is not None:
        return exact
    key = (brand.casefold(), flavor.casefold(), pack.casefold())
    for (b, f, p), qty in balances.items():
        if (b.casefold(), f.casefold(), p.casefold()) == key:
            return qty
    return 0
