"""Тесты парсера команд склада."""
from __future__ import annotations

from datetime import date

from bot.parsing import ParseErr, ParseOk, parse_movement_args

BRANDS = [
    "Palitra",
    "Musthave",
    "Darkside",
    "Сарма классик",
    "Сарма крепкая",
    "Хулиган классический",
    "Afzal",
]
PACKS = ["25 г", "30 г", "40 г", "50 г", "100 г", "125 г", "200 г", "250 г"]
TODAY = date(2026, 10, 5)


def _parse(text: str):
    return parse_movement_args(
        text,
        brands=BRANDS,
        packs=PACKS,
        today=TODAY,
        default_author="Федор",
    )


def test_basic():
    r = _parse("04.10.2026 Сарма классик Буратино 200 г 10 Федя")
    assert isinstance(r, ParseOk)
    assert r.brand == "Сарма классик"
    assert r.flavor == "Буратино"
    assert r.pack == "200 г"
    assert r.qty == 10
    assert r.author == "Федя"
    assert r.date == date(2026, 10, 4)


def test_no_date():
    r = _parse("Сарма классик Буратино 200 г 10 Федя")
    assert isinstance(r, ParseOk)
    assert r.date == TODAY


def test_pack_no_space():
    r = _parse("04.10.2026 Darkside Cosmo Flower 50г 3 Федя")
    assert isinstance(r, ParseOk)
    assert r.brand == "Darkside"
    assert r.flavor == "Cosmo Flower"
    assert r.pack == "50 г"
    assert r.qty == 3


def test_no_author():
    r = _parse("04.10.2026 Хулиган классический Мята 100 г 1")
    assert isinstance(r, ParseOk)
    assert r.author == "Федор"
    assert r.brand == "Хулиган классический"
    assert r.flavor == "Мята"


def test_quoted():
    r = _parse('04.10.2026 "Сарма классик" "Буратино" 200 г 10')
    assert isinstance(r, ParseOk)
    assert r.brand == "Сарма классик"
    assert r.flavor == "Буратино"


def test_today_word():
    r = _parse("сегодня Afzal Limon-Lime 40 г 20 Федя")
    assert isinstance(r, ParseOk)
    assert r.date == TODAY
    assert r.brand == "Afzal"
    assert r.flavor == "Limon-Lime"


def test_missing_pack():
    r = _parse("Сарма классик Буратино 10 Федя")
    assert isinstance(r, ParseErr)


def test_zero_qty():
    r = _parse("Сарма классик Буратино 200 г 0 Федя")
    assert isinstance(r, ParseErr)
