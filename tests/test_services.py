from datetime import date

from bot.services import normalize_pack, parse_day, stock_of

PACKS = ["25 г", "200 г", "250 г"]


def test_parse_day_formats():
    base = date(2026, 10, 5)
    assert parse_day("", base) == base
    assert parse_day("вчера", base) == date(2026, 10, 4)
    assert parse_day("04.10.2026", base) == date(2026, 10, 4)
    assert parse_day("2026-10-04", base) == date(2026, 10, 4)
    assert parse_day("31.02.2026", base) is None


def test_normalize_pack():
    assert normalize_pack("200", PACKS) == "200 г"
    assert normalize_pack("200г", PACKS) == "200 г"
    assert normalize_pack("250 г", PACKS) == "250 г"
    assert normalize_pack("20", PACKS) is None
    assert normalize_pack("abc", PACKS) is None


def test_stock_of_case_insensitive():
    balances = {("Darkside", "Red tea", "250 г"): 3}
    assert stock_of(balances, "darkside", "RED TEA", "250 г") == 3
    assert stock_of(balances, "Darkside", "Bounty", "250 г") == 0
