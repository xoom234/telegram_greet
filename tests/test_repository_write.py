from datetime import date

import pytest

from bot import repository
from bot.repository import Operation, _append_operation_sync, _cell_text


class FakeSheet:
    """Лист «Накладные»: строки с 4-й, вставка строк как в Google Sheets."""

    id = 42

    def __init__(self, rows):
        self.rows = [list(r) for r in rows]
        self.stale = None

    def worksheet(self, name):
        return self

    def get(self, rng, **kwargs):
        if self.stale is not None:
            snapshot, self.stale = self.stale, None
            return snapshot
        return [list(r) for r in self.rows]

    def update(self, values, rng, **kwargs):
        col = "ABCDEFGHI".index(rng[0])
        row = int(rng[1:].split(":")[0])
        while len(self.rows) < row - 3:
            self.rows.append([])
        target = self.rows[row - 4]
        target.extend([""] * (9 - len(target)))
        for i, v in enumerate(values[0]):
            target[col + i] = str(v).lstrip("'")

    def batch_update(self, body):
        insert, paste = body["requests"]
        idx = insert["insertDimension"]["range"]["startIndex"] - 3
        cells = [c.lstrip("'") for c in paste["pasteData"]["data"].split("\t")]
        self.rows.insert(idx, cells)


def row(doc, brand="Darkside", flavor="Red tea", qty="3", comment=""):
    return ["05.10.2026", doc, brand, flavor, "250 г", qty, "Приход", "Федор", comment]


def op(flavor="Bounty", qty=2, comment=""):
    return Operation(date(2026, 10, 6), "Darkside", flavor, "250 г", qty, "Федор", "Приход", comment)


@pytest.fixture
def sheet(monkeypatch):
    fake = FakeSheet([row("Н-001"), row("Н-002"), row("Н-003")])
    monkeypatch.setattr(repository, "open_spreadsheet", lambda: fake)
    return fake


def test_cell_text_blocks_formulas_and_tabs():
    assert _cell_text("=IMPORTXML(1)") == "'=IMPORTXML(1)"
    assert _cell_text("+7") == "'+7"
    assert _cell_text("Red\ttea\n") == "Red tea"
    assert _cell_text("Буратино") == "Буратино"


def test_append_inserts_at_first_free_row(sheet):
    sheet.rows.append([])
    sheet.rows.append(row("Н-004"))
    assert _append_operation_sync(op()) == (7, "Н-005", False)
    assert sheet.rows[3][3] == "Bounty"
    assert sheet.rows[5][1] == "Н-004"


def test_same_request_id_is_not_written_twice(sheet):
    first = _append_operation_sync(op(), request_id="req12345")
    second = _append_operation_sync(op(), request_id="req12345")
    assert first == (7, "Н-004", False)
    assert second == (7, "Н-004", True)
    assert len(sheet.rows) == 4
    assert sheet.rows[3][8].endswith("req=req12345")


def test_concurrent_writers_keep_both_rows_and_distinct_numbers(sheet):
    snapshot = [list(r) for r in sheet.rows]
    _append_operation_sync(op(flavor="Первый"))
    # второй писатель прочитал таблицу до записи первого
    sheet.stale = snapshot
    result = _append_operation_sync(op(flavor="Второй"))
    flavors = [r[3] for r in sheet.rows]
    assert "Первый" in flavors and "Второй" in flavors
    numbers = [r[1] for r in sheet.rows]
    assert len(numbers) == len(set(numbers))
    assert result == (7, "Н-005", False)
    assert sheet.rows[3][1] == "Н-005" and sheet.rows[4][1] == "Н-004"
