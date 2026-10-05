#!/usr/bin/env python3
"""Build warehouse workbook with Google Sheets–compatible formulas."""
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

brands = [
    "Palitra", "Deus", "Musthave", "TNG",
    "Хулиган крепкий", "Хулиган классический",
    "Sebero", "Sapphire", "Trof", "Satyr", "Jent", "Darkside",
    "Сарма классик", "Сарма крепкая", "Сарма легкая",
    "Blackburn", "Overdose", "Afzal", "Starline", "Element",
    "База", "НАШ", "Bonche",
]

PACKS = ["25 г", "30 г", "40 г", "50 г", "100 г", "125 г", "200 г", "250 г"]
MAX_ROWS = 1000
DATA_LAST = 2000

wb = Workbook()

header_fill = PatternFill("solid", fgColor="1F4E79")
header_font = Font(bold=True, color="FFFFFF", name="Arial", size=11)
title_font = Font(bold=True, name="Arial", size=14, color="1F4E79")
hint_font = Font(italic=True, name="Arial", size=10, color="666666")
normal_font = Font(name="Arial", size=11)
thin = Border(
    left=Side(style="thin", color="B0B0B0"),
    right=Side(style="thin", color="B0B0B0"),
    top=Side(style="thin", color="B0B0B0"),
    bottom=Side(style="thin", color="B0B0B0"),
)
center = Alignment(horizontal="center", vertical="center", wrap_text=True)
example_fill = PatternFill("solid", fgColor="FFF2CC")
input_fill = PatternFill("solid", fgColor="E2EFDA")
link_fill = PatternFill("solid", fgColor="DDEBF7")
readonly_fill = PatternFill("solid", fgColor="F3F3F3")

# ========== Фасовки ==========
ws_pack = wb.active
ws_pack.title = "Фасовки"
ws_pack["A1"] = "Фасовки"
ws_pack["A1"].font = title_font
ws_pack["A2"] = "Список фасовок. Можно добавлять новые ниже."
ws_pack["A2"].font = hint_font
ws_pack["A3"] = "Фасовка"
ws_pack["A3"].fill = header_fill
ws_pack["A3"].font = header_font
ws_pack["A3"].border = thin
for i, p in enumerate(PACKS):
    cell = ws_pack.cell(4 + i, 1, p)
    cell.fill = input_fill
    cell.border = thin
for r in range(4 + len(PACKS), 24):
    ws_pack.cell(r, 1).fill = input_fill
    ws_pack.cell(r, 1).border = thin
ws_pack.column_dimensions["A"].width = 14

# ========== Бренды ==========
ws_br = wb.create_sheet("Бренды")
ws_br["A1"] = "Бренды"
ws_br["A1"].font = title_font
ws_br["A2"] = "Список для выбора в накладных."
ws_br["A2"].font = hint_font
ws_br["A3"] = "Бренд"
ws_br["A3"].fill = header_fill
ws_br["A3"].font = header_font
ws_br["A3"].border = thin
for i, b in enumerate(brands):
    cell = ws_br.cell(4 + i, 1, b)
    cell.fill = input_fill
    cell.border = thin
for r in range(4 + len(brands), 104):
    ws_br.cell(r, 1).fill = input_fill
    ws_br.cell(r, 1).border = thin
ws_br.column_dimensions["A"].width = 28

# ========== Накладные ==========
ws2 = wb.create_sheet("Накладные")
ws2["A1"] = "Накладные"
ws2["A1"].font = title_font
ws2.merge_cells("A1:I1")
ws2["A2"] = "Заполняйте зелёные ячейки. Все бренды+вкусы автоматически появятся на «Склад»."
ws2["A2"].font = hint_font
ws2.merge_cells("A2:I2")

headers2 = [
    "Дата", "№ накладной", "Бренд", "Вкус", "Вид фасовки",
    "Количество", "Операция", "Кто внёс", "Комментарий",
]
for col, h in enumerate(headers2, start=1):
    cell = ws2.cell(3, col, h)
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = center
    cell.border = thin

examples = [
    ["04.10.2026", "Н-001", "Darkside", "Cosmo Flower", "50 г", 10, "Приход", "Иван", "пример"],
    ["04.10.2026", "Н-002", "Darkside", "Supernova", "25 г", 5, "Приход", "Иван", "пример"],
    ["04.10.2026", "Н-003", "Musthave", "Pinkman", "100 г", 3, "Приход", "Иван", "пример"],
]
for ri, example in enumerate(examples):
    for col, val in enumerate(example, start=1):
        cell = ws2.cell(4 + ri, col, val)
        cell.fill = example_fill
        cell.border = thin

for r in range(4 + len(examples), DATA_LAST + 1):
    for c in range(1, 10):
        cell = ws2.cell(r, c)
        cell.fill = input_fill
        cell.border = thin

dv_brand = DataValidation(type="list", formula1="=Бренды!$A$4:$A$103", allow_blank=True)
ws2.add_data_validation(dv_brand)
dv_brand.add("C4:C%s" % DATA_LAST)

dv_pack = DataValidation(type="list", formula1="=Фасовки!$A$4:$A$23", allow_blank=True)
ws2.add_data_validation(dv_pack)
dv_pack.add("E4:E%s" % DATA_LAST)

dv_op = DataValidation(type="list", formula1='"Приход,Расход"', allow_blank=True)
ws2.add_data_validation(dv_op)
dv_op.add("G4:G%s" % DATA_LAST)

for i, w in enumerate([12, 14, 22, 24, 12, 12, 12, 12, 18], start=1):
    ws2.column_dimensions[get_column_letter(i)].width = w
ws2.freeze_panes = "A4"

# ========== Склад ==========
ws1 = wb.create_sheet("Склад", 0)
ws1["A1"] = "Склад — автоиз накладных"
ws1["A1"].font = title_font
ws1.merge_cells("A1:K1")
ws1["A2"] = (
    "Столбцы A–B считаются формулой из «Накладные». "
    "Если видите ошибку формулы: Файл → Настройки → регион «Россия»."
)
ws1["A2"].font = hint_font
ws1.merge_cells("A2:K2")

ws1["A3"] = "Бренд"
ws1["B3"] = "Вкус"
for i, p in enumerate(PACKS):
    ws1.cell(3, 3 + i, p)
ws1.cell(3, 3 + len(PACKS), "Итого")

for col in range(1, 3 + len(PACKS) + 1):
    cell = ws1.cell(3, col)
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = center
    cell.border = thin
ws1.row_dimensions[3].height = 28

# Google Sheets (локаль Россия, разделитель ;):
# FILTER по соседним столбцам C:D — БЕЗ конструкции {A\B}, из‑за неё была синтаксическая ошибка
a4_formula = (
    '=IFERROR(SORT(UNIQUE(FILTER(Накладные!C4:D%s;'
    'Накладные!C4:C%s<>"";'
    'Накладные!D4:D%s<>""));'
    '1;TRUE;2;TRUE);"")'
) % (DATA_LAST, DATA_LAST, DATA_LAST)

ws1["A4"] = a4_formula
ws1["A4"].fill = readonly_fill
ws1["A4"].border = thin

first_pack_col = 3
for r in range(4, 4 + MAX_ROWS):
    for c in (1, 2):
        cell = ws1.cell(r, c)
        cell.border = thin
        cell.fill = readonly_fill

    for pi in range(len(PACKS)):
        col = first_pack_col + pi
        pack_header = "$%s$3" % get_column_letter(col)
        # Приход минус Расход — без вспомогательных столбцов
        formula = (
            '=IF(OR($A%(r)s="";$B%(r)s="");"";'
            'SUMIFS(Накладные!$F$4:$F$%(n)s;Накладные!$C$4:$C$%(n)s;$A%(r)s;'
            'Накладные!$D$4:$D$%(n)s;$B%(r)s;Накладные!$E$4:$E$%(n)s;%(pack)s;'
            'Накладные!$G$4:$G$%(n)s;"Приход")'
            '-'
            'SUMIFS(Накладные!$F$4:$F$%(n)s;Накладные!$C$4:$C$%(n)s;$A%(r)s;'
            'Накладные!$D$4:$D$%(n)s;$B%(r)s;Накладные!$E$4:$E$%(n)s;%(pack)s;'
            'Накладные!$G$4:$G$%(n)s;"Расход"))'
        ) % {"r": r, "n": DATA_LAST, "pack": pack_header}
        cell = ws1.cell(r, col, formula)
        cell.fill = link_fill
        cell.border = thin
        cell.alignment = center

    total_col = first_pack_col + len(PACKS)
    start_c = get_column_letter(first_pack_col)
    end_c = get_column_letter(first_pack_col + len(PACKS) - 1)
    tcell = ws1.cell(
        r,
        total_col,
        '=IF($A%s="";"";SUM(%s%s:%s%s))' % (r, start_c, r, end_c, r),
    )
    tcell.fill = link_fill
    tcell.border = thin
    tcell.alignment = center

ws1.column_dimensions["A"].width = 22
ws1.column_dimensions["B"].width = 24
for i in range(first_pack_col, first_pack_col + len(PACKS) + 1):
    ws1.column_dimensions[get_column_letter(i)].width = 9
ws1.freeze_panes = "C4"

# ========== Инструкция ==========
ws0 = wb.create_sheet("Инструкция")
ws0["A1"] = "Если была синтаксическая ошибка"
ws0["A1"].font = title_font
lines = [
    "",
    "Причина ошибки: старая формула использовала конструкцию {A\\B} — Google Таблицы её часто не принимают.",
    "Сейчас используется QUERY — это родная формула Google Таблиц.",
    "",
    "Обязательно:",
    "1. Загрузите НОВЫЙ файл: Файл → Импорт → Загрузка → заменить таблицу.",
    "2. Настройки таблицы → Общие → Регион: Россия (чтобы ; в формулах работали).",
    "3. Не копируйте ячейки из старого файла — только новый импорт.",
    "",
    "Проверка: на «Склад» должны появиться Darkside/Cosmo Flower, Darkside/Supernova, Musthave/Pinkman.",
]
for i, t in enumerate(lines, start=2):
    ws0["A%s" % i] = t
    ws0["A%s" % i].font = normal_font
ws0.column_dimensions["A"].width = 110

# Also store English-comma versions on a helper sheet for US locale users
ws_alt = wb.create_sheet("_формула_EN")
ws_alt["A1"] = "Если регион США/Англия — вставьте эту формулу в Склад!A4:"
ws_alt["A2"] = (
    '=IFERROR(SORT(UNIQUE(FILTER(Накладные!C4:D%s,'
    'Накладные!C4:C%s<>"",'
    'Накладные!D4:D%s<>"")),'
    '1,TRUE,2,TRUE),"")'
) % (DATA_LAST, DATA_LAST, DATA_LAST)
ws_alt["A3"] = "Если регион не Россия — вставьте формулу выше в Склад!A4 и в остатках замените ; на ,"
ws_alt.column_dimensions["A"].width = 120
ws_alt.sheet_state = "hidden"

wb._sheets = [ws1, ws2, ws_br, ws_pack, ws0, ws_alt]

path = "/Users/xoomger/telegram_greet/sklad_tabak.xlsx"
wb.save(path)
print("A4=", ws1["A4"].value)
print("C4=", ws1["C4"].value)
print("saved", path)
