#!/usr/bin/env python3
"""Исправляет формулы на листе Склад в подключённой Google Таблице."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sheets.client import open_spreadsheet  # noqa: E402

DATA_LAST = 2000
MAX_ROWS = 1000
PACKS = ["25 г", "30 г", "40 г", "50 г", "100 г", "125 г", "200 г", "250 г"]

# Формулы с ; — для региона «Россия»
A4_FORMULA_RU = (
    f'=IFERROR(SORT(UNIQUE(FILTER(Накладные!C4:D{DATA_LAST};'
    f'Накладные!C4:C{DATA_LAST}<>"";Накладные!D4:D{DATA_LAST}<>""));'
    f'1;TRUE;2;TRUE);"")'
)

# Формулы с , — для региона США/UK
A4_FORMULA_EN = (
    f'=IFERROR(SORT(UNIQUE(FILTER(Накладные!C4:D{DATA_LAST},'
    f'Накладные!C4:C{DATA_LAST}<>"",Накладные!D4:D{DATA_LAST}<>"")),'
    f'1,TRUE,2,TRUE),"")'
)


def pack_formula(row: int, pack_col_letter: str, sep: str = ";") -> str:
    """sep: ';' for RU locale, ',' for EN locale."""
    s = sep
    return (
        f'=IF(OR($A{row}=""{s}$B{row}="");""{s}'
        f'SUMIFS(Накладные!$F$4:$F${DATA_LAST}{s}Накладные!$C$4:$C${DATA_LAST}{s}$A{row}{s}'
        f'Накладные!$D$4:$D${DATA_LAST}{s}$B{row}{s}Накладные!$E$4:$E${DATA_LAST}{s}${pack_col_letter}$3{s}'
        f'Накладные!$G$4:$G${DATA_LAST}{s}"Приход")'
        f'-'
        f'SUMIFS(Накладные!$F$4:$F${DATA_LAST}{s}Накладные!$C$4:$C${DATA_LAST}{s}$A{row}{s}'
        f'Накладные!$D$4:$D${DATA_LAST}{s}$B{row}{s}Накладные!$E$4:$E${DATA_LAST}{s}${pack_col_letter}$3{s}'
        f'Накладные!$G$4:$G${DATA_LAST}{s}"Расход"))'
    )


def total_formula(row: int, start_col: str, end_col: str, sep: str = ";") -> str:
    return f'=IF($A{row}="";"";SUM({start_col}{row}:{end_col}{row}))'.replace(";", sep)


def col_letter(idx: int) -> str:
    """1-based column index to letter."""
    result = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        result = chr(65 + rem) + result
    return result


def ensure_headers(ws, locale: str) -> None:
    headers = ["Бренд", "Вкус", *PACKS, "Итого"]
    ws.update("A3", [headers], value_input_option="USER_ENTERED")
    ws.update("A1", [["Склад — автоиз накладных"]], value_input_option="USER_ENTERED")
    ws.update(
        "A2",
        [[
            "A–B заполняются из «Накладные» автоматически. "
            f"Локаль формул: {locale}."
        ]],
        value_input_option="USER_ENTERED",
    )


def apply_formulas(locale: str = "RU") -> None:
    sep = ";" if locale.upper() == "RU" else ","
    a4 = A4_FORMULA_RU if locale.upper() == "RU" else A4_FORMULA_EN

    ss = open_spreadsheet()
    try:
        ws = ss.worksheet("Склад")
    except Exception:
        ws = ss.add_worksheet(title="Склад", rows=MAX_ROWS + 10, cols=20)

    print(f"Таблица: {ss.title}")
    print(f"Лист: {ws.title}")
    print(f"Локаль формул: {locale} (разделитель {sep!r})")

    ensure_headers(ws, locale)
    ws.update("A4", [[a4]], value_input_option="USER_ENTERED")
    print("Записана формула списка вкусов в A4")

    # Pack columns: C=3 ... J=10 (8 packs), K=total
    first_pack = 3
    updates = []
    for r in range(4, 4 + MAX_ROWS):
        row_vals = []
        for pi in range(len(PACKS)):
            letter = col_letter(first_pack + pi)
            row_vals.append(pack_formula(r, letter, sep=sep))
        start_c = col_letter(first_pack)
        end_c = col_letter(first_pack + len(PACKS) - 1)
        row_vals.append(total_formula(r, start_c, end_c, sep=sep))
        updates.append(row_vals)

    # Batch update C4:K1003
    end_letter = col_letter(first_pack + len(PACKS))
    range_name = f"C4:{end_letter}{3 + MAX_ROWS}"
    ws.update(range_name, updates, value_input_option="USER_ENTERED")
    print(f"Записаны формулы остатков в {range_name}")
    print("Готово. Открой лист «Склад» и проверь, что вкусы подтянулись.")


def main() -> int:
    locale = "RU"
    if len(sys.argv) > 1:
        locale = sys.argv[1].upper()
    try:
        apply_formulas(locale=locale)
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"ОШИБКА: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
