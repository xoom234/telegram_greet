"""Тексты ответов бота."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from bot.repository import MovementRow, Operation


def format_operation_ok(
    op: Operation,
    *,
    doc_no: str,
    row: int,
) -> str:
    sign = "+" if op.kind == "Приход" else "−"
    return (
        f"{op.kind} записан\n"
        f"Бренд: {op.brand}\n"
        f"Вкус: {op.flavor}\n"
        f"Фасовка: {op.pack}\n"
        f"Количество: {sign}{op.qty}\n"
        f"Дата: {op.date.strftime('%d.%m.%Y')}\n"
        f"Внёс: {op.author}\n"
        f"Накладная: {doc_no} (строка {row})"
    )


def format_overdraft_warning(
    brand: str,
    flavor: str,
    pack: str,
    stock: int,
    qty: int,
) -> str:
    return (
        f"Внимание: остаток {brand} / {flavor} / {pack} = {stock} шт,\n"
        f"вы списываете {qty} шт. Остаток станет {stock - qty}.\n"
        "Подтвердите списание."
    )


def compute_balances(
    rows: list[MovementRow],
) -> dict[tuple[str, str, str], int]:
    balances: dict[tuple[str, str, str], int] = defaultdict(int)
    for row in rows:
        key = (row.brand, row.flavor, row.pack)
        if row.kind == "Приход":
            balances[key] += row.qty
        elif row.kind == "Расход":
            balances[key] -= row.qty
        else:
            # неизвестная операция — не учитываем
            continue
    return dict(balances)


def format_stock_report(
    balances: dict[tuple[str, str, str], int],
    *,
    brand_filter: str | None = None,
    hide_zero: bool = False,
) -> str:
    """По умолчанию показываем и нулевые/отрицательные остатки — вкус не пропадает."""
    items = [
        (b, f, p, q)
        for (b, f, p), q in balances.items()
        if (brand_filter is None or b.casefold() == brand_filter.casefold())
        and (not hide_zero or q != 0)
    ]
    if brand_filter and not items:
        return f"По бренду «{brand_filter}» позиций нет."

    if not items:
        return "Склад пуст (нет позиций в накладных)."

    items.sort(key=lambda x: (x[0].casefold(), x[1].casefold(), x[2]))

    if brand_filter:
        lines = [brand_filter, ""]
        total = 0
        by_flavor: dict[str, list[tuple[str, int]]] = defaultdict(list)
        for _, flavor, pack, qty in items:
            by_flavor[flavor].append((pack, qty))
            total += qty
        for flavor in sorted(by_flavor, key=str.casefold):
            lines.append(flavor)
            for pack, qty in by_flavor[flavor]:
                lines.append(f"  {pack} — {qty}")
        lines.append(f"Итого по бренду: {total} единиц")
        return "\n".join(lines)

    lines = ["Остатки на складе", ""]
    current_brand = None
    total_qty = 0
    positions = 0
    for brand, flavor, pack, qty in items:
        if brand != current_brand:
            if current_brand is not None:
                lines.append("")
            lines.append(brand)
            current_brand = brand
        lines.append(f"  {flavor}: {pack} — {qty}")
        total_qty += qty
        positions += 1
    lines.append("")
    lines.append(f"Всего позиций: {positions} | Всего единиц: {total_qty}")
    return "\n".join(lines)


def format_info_report(
    rows: list[MovementRow],
    *,
    day: date,
) -> str:
    day_s = day.strftime("%d.%m.%Y")
    matched = [r for r in rows if r.date == day_s]
    undated = [r for r in rows if not r.date]

    if not matched:
        text = f"{day_s}\n\nОпераций за этот день нет."
        if undated:
            text += f"\n\nБез даты: {len(undated)} записей (внесены вручную)."
        return text

    by_author: dict[str, list[MovementRow]] = defaultdict(list)
    for row in matched:
        by_author[row.author or "Без имени"].append(row)

    lines = [day_s, ""]
    total_in = total_out = 0
    for author in sorted(by_author, key=str.casefold):
        ops = by_author[author]
        lines.append(f"{author} — {len(ops)} операций")
        for op in ops:
            sign = "+" if op.kind == "Приход" else "−"
            if op.kind == "Приход":
                total_in += op.qty
            elif op.kind == "Расход":
                total_out += op.qty
            lines.append(
                f"  {sign} {op.brand} / {op.flavor} / {op.pack} — {op.qty}"
            )
        lines.append("")
    lines.append(f"Итого: приход {total_in}, расход {total_out}")
    if undated:
        lines.append(f"Без даты в таблице: {len(undated)} записей")
    return "\n".join(lines).rstrip()


def split_telegram_messages(text: str, limit: int = 3900) -> list[str]:
    """Резать длинный отчёт по пустым строкам / по брендам."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    current = ""
    for block in text.split("\n\n"):
        candidate = block if not current else current + "\n\n" + block
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        if len(block) <= limit:
            current = block
        else:
            # жёсткая нарезка длинного блока
            for i in range(0, len(block), limit):
                chunks.append(block[i : i + limit])
            current = ""
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]
