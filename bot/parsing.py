"""Разбор текста команд /приход и /расход."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Optional, Union

from bot.config import load_settings

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover
    fuzz = None
    process = None

DATE_RE = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\b")
QUOTED_RE = re.compile(r'"([^"]+)"')
INT_RE = re.compile(r"\d+")

FUZZY_ASK = 85
FUZZY_ACCEPT = 95


@dataclass
class ParseOk:
    date: date
    brand: str
    flavor: str
    pack: str
    qty: int
    author: str
    brand_exact: bool = True
    brand_candidates: tuple = ()


@dataclass
class ParseErr:
    message: str


ParseResult = Union[ParseOk, ParseErr]


def _norm_space(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _parse_date_token(token: str, today: date) -> date | None:
    low = token.casefold()
    if low in {"сегодня", "today"}:
        return today
    if low in {"вчера", "yesterday"}:
        return today - timedelta(days=1)
    try:
        return datetime.strptime(token, "%d.%m.%Y").date()
    except ValueError:
        return None


def _pack_pattern(packs: list[str]) -> re.Pattern[str] | None:
    grams: list[str] = []
    for pack in packs:
        m = re.search(r"(\d+)\s*г", pack, re.I)
        if m:
            grams.append(m.group(1))
    if not grams:
        return None
    grams = sorted(set(grams), key=lambda x: int(x), reverse=True)
    return re.compile(rf"(?P<g>{'|'.join(grams)})\s*г", re.I)


def _match_brand(
    fragment: str,
    brands: list[str],
) -> tuple[str | None, bool, tuple[str, ...]]:
    """Вернуть (brand, exact, candidates)."""
    text = _norm_space(fragment)
    if not text:
        return None, False, ()

    ordered = sorted(brands, key=len, reverse=True)
    lower = text.casefold()
    for brand in ordered:
        b = brand.strip()
        if not b:
            continue
        bl = b.casefold()
        if lower == bl or lower.startswith(bl + " "):
            return b, True, ()

    # fuzzy по префиксу / полному фрагменту
    if process is None or fuzz is None:
        return None, False, ()

    # кандидаты: бренд, если fragment начинается похоже на него
    choices = {b: b.casefold() for b in ordered if b.strip()}
    # score against start of fragment with same word count
    scored: list[tuple[str, float]] = []
    for brand, bl in choices.items():
        words = len(brand.split())
        prefix = " ".join(text.split()[:words])
        if not prefix:
            continue
        score = fuzz.ratio(prefix.casefold(), bl)
        scored.append((brand, float(score)))
    scored.sort(key=lambda x: x[1], reverse=True)
    if not scored:
        return None, False, ()

    best_brand, best_score = scored[0]
    if best_score >= FUZZY_ACCEPT:
        return best_brand, True, ()
    if best_score >= FUZZY_ASK:
        cands = tuple(b for b, s in scored if s >= FUZZY_ASK)[:3]
        return best_brand, False, cands
    return None, False, tuple(b for b, s in scored[:3])


def parse_movement_args(
    raw: str,
    *,
    brands: list[str],
    packs: list[str],
    today: date | None = None,
    default_author: str | None = None,
) -> ParseResult:
    """
    Разбор: [дата] бренд вкус фасовка количество [кто]
    Пример: 04.10.2026 Сарма классик Буратино 200 г 10 Федя
    """
    settings = load_settings()
    author_default = default_author or settings.default_author
    today = today or date.today()
    text = _norm_space(raw)
    if not text:
        return ParseErr(
            "Пример: /приход 04.10.2026 Сарма классик Буратино 200 г 10 Федя"
        )

    # 1) Дата
    op_date = today
    rest = text
    m_date = DATE_RE.match(text)
    if m_date:
        parsed = _parse_date_token(m_date.group(1), today)
        if parsed is None:
            return ParseErr("Непонятная дата. Формат: ДД.ММ.ГГГГ")
        op_date = parsed
        rest = text[m_date.end():].strip()
    else:
        first, _, tail = text.partition(" ")
        maybe = _parse_date_token(first, today)
        if maybe is not None and tail:
            op_date = maybe
            rest = tail.strip()

    if not rest:
        return ParseErr(
            "Не хватает данных. Пример: /приход 04.10.2026 Сарма классик Буратино 200 г 10 Федя"
        )

    # 2) Кавычки: "бренд" "вкус"
    quoted = QUOTED_RE.findall(rest)
    if len(quoted) >= 2:
        brand = _norm_space(quoted[0])
        flavor = _norm_space(quoted[1])
        # убрать кавычки из строки для дальнейшего разбора
        rest_wo = QUOTED_RE.sub(" ", rest)
        rest_wo = _norm_space(rest_wo)
        pack_re = _pack_pattern(packs)
        if pack_re is None:
            return ParseErr("Справочник фасовок пуст")
        matches = list(pack_re.finditer(rest_wo))
        if not matches:
            return ParseErr(
                "Не понял фасовку. Доступные: " + ", ".join(packs)
            )
        pack_m = matches[-1]
        pack = f"{pack_m.group('g')} г"
        after = rest_wo[pack_m.end():].strip()
        nums = INT_RE.findall(after)
        if not nums:
            return ParseErr(
                "Не вижу количество. Пример: /приход 04.10.2026 Сарма классик Буратино 200 г 10 Федя"
            )
        qty = int(nums[0])
        if qty <= 0:
            return ParseErr("Количество должно быть больше нуля")
        after_qty = after[after.find(nums[0]) + len(nums[0]):].strip()
        author = after_qty or author_default
        return ParseOk(
            date=op_date,
            brand=brand,
            flavor=flavor,
            pack=pack,
            qty=qty,
            author=author,
            brand_exact=True,
        )

    # 3) Фасовка — последнее совпадение из справочника
    pack_re = _pack_pattern(packs)
    if pack_re is None:
        return ParseErr("Справочник фасовок пуст")
    matches = list(pack_re.finditer(rest))
    if not matches:
        return ParseErr("Не понял фасовку. Доступные: " + ", ".join(packs))
    pack_m = matches[-1]
    pack = f"{pack_m.group('g')} г"
    before = rest[: pack_m.start()].strip()
    after = rest[pack_m.end():].strip()

    # 4) Количество после фасовки
    nums = INT_RE.findall(after)
    if not nums:
        return ParseErr(
            "Не вижу количество. Пример: /приход 04.10.2026 Сарма классик Буратино 200 г 10 Федя"
        )
    qty = int(nums[0])
    if qty <= 0:
        return ParseErr("Количество должно быть больше нуля")
    after_qty = after[after.find(nums[0]) + len(nums[0]):].strip()
    author = after_qty or author_default

    if not before:
        return ParseErr("Не указаны бренд и вкус")

    # 5) Бренд + вкус
    brand, exact, cands = _match_brand(before, brands)
    if brand is None:
        hint = ""
        if cands:
            hint = "\nПохожие: " + ", ".join(cands)
        return ParseErr(
            f"Бренд не найден в «{before}». "
            "Добавьте его в лист Бренды или укажите в кавычках: "
            '"Сарма классик" "Буратино"'
            f"{hint}"
        )

    words = len(brand.split())
    flavor = " ".join(before.split()[words:]).strip()
    if not flavor:
        return ParseErr("Не указан вкус после бренда")

    return ParseOk(
        date=op_date,
        brand=brand,
        flavor=flavor,
        pack=pack,
        qty=qty,
        author=author,
        brand_exact=exact,
        brand_candidates=cands,
    )


def strip_command(text: str) -> str:
    """Убрать первую /команду из сообщения."""
    text = (text or "").strip()
    if not text.startswith("/"):
        return text
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


CommandKind = Literal["Приход", "Расход"]
