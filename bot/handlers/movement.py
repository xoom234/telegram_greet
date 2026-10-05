"""Команды /приход и /расход."""
from __future__ import annotations

import logging
import re
from datetime import date

from aiogram import Dispatcher, F
from aiogram.types import CallbackQuery, Message

from bot.formatting import compute_balances, format_operation_ok
from bot.parsing import ParseErr, ParseOk, parse_movement_args, strip_command
from bot.repository import Operation, append_operation, load_brands, load_packs, read_movements

logger = logging.getLogger(__name__)

PRIHOD_RE = re.compile(r"^/(приход|prihod|in)(@\w+)?(\s|$)", re.I)
RASHOD_RE = re.compile(r"^/(расход|рассход|rashod|out)(@\w+)?(\s|$)", re.I)

# временное хранилище ожидающих подтверждения расходов: user_id -> payload
_pending_rashod: dict[int, dict] = {}

USAGE_PRIHOD = (
    "Пример:\n"
    "/приход 04.10.2026 Сарма классик Буратино 200 г 10 Федя\n\n"
    "Или в кавычках:\n"
    '/приход 04.10.2026 "Сарма классик" "Буратино" 200 г 10 Федя'
)
USAGE_RASHOD = (
    "Пример:\n"
    "/расход 04.10.2026 Сарма классик Буратино 200 г 10 Федя"
)


def _tg_comment(message: Message) -> str:
    user = message.from_user
    if user is None:
        return "telegram"
    uname = f"@{user.username}" if user.username else user.full_name
    return f"{uname} id={user.id}"


def _op_from_ok(ok: ParseOk, kind: str, comment: str) -> Operation:
    return Operation(
        date=ok.date,
        brand=ok.brand,
        flavor=ok.flavor,
        pack=ok.pack,
        qty=ok.qty,
        author=ok.author,
        kind=kind,  # type: ignore[arg-type]
        comment=comment,
    )


async def _parse_or_reply(message: Message, usage: str) -> ParseOk | None:
    args = strip_command(message.text or "")
    if not args:
        await message.answer(usage)
        return None
    brands = await load_brands()
    packs = await load_packs()
    result = parse_movement_args(args, brands=brands, packs=packs)
    if isinstance(result, ParseErr):
        await message.answer(result.message + "\n\n" + usage)
        return None
    if not result.brand_exact and result.brand_candidates:
        # просим подтвердить бренд — для простоты берём лучший и пишем предупреждение
        await message.answer(
            f"Бренд распознан как «{result.brand}» "
            f"(похожие: {', '.join(result.brand_candidates)}).\n"
            "Если неверно — повторите команду с кавычками."
        )
    return result


async def cmd_prihod(message: Message) -> None:
    ok = await _parse_or_reply(message, USAGE_PRIHOD)
    if ok is None:
        return
    op = _op_from_ok(ok, "Приход", _tg_comment(message))
    row, doc_no = await append_operation(
        op,
        tg_user_id=message.from_user.id if message.from_user else None,
    )
    await message.answer(format_operation_ok(op, doc_no=doc_no, row=row))


async def cmd_rashod(message: Message) -> None:
    ok = await _parse_or_reply(message, USAGE_RASHOD)
    if ok is None:
        return

    # Расход всегда пишем: вкус остаётся в учёте даже при остатке 0 или минусе.
    movements = await read_movements()
    balances = compute_balances(movements)
    key = (ok.brand, ok.flavor, ok.pack)
    # case-insensitive lookup for stock hint
    stock = balances.get(key)
    if stock is None:
        for (b, f, p), q in balances.items():
            if (
                b.casefold() == ok.brand.casefold()
                and f.casefold() == ok.flavor.casefold()
                and p.casefold() == ok.pack.casefold()
            ):
                stock = q
                break
        else:
            stock = 0

    op = _op_from_ok(ok, "Расход", _tg_comment(message))
    row, doc_no = await append_operation(
        op,
        tg_user_id=message.from_user.id if message.from_user else None,
    )
    text = format_operation_ok(op, doc_no=doc_no, row=row)
    new_stock = stock - ok.qty
    if new_stock <= 0:
        text += f"\nОстаток после списания: {new_stock} (вкус сохранён в учёте)"
    await message.answer(text)

async def on_rashod_confirm(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    data = _pending_rashod.pop(user_id, None)
    if not data:
        await callback.answer("Нечего подтверждать", show_alert=True)
        return
    op = Operation(
        date=date.fromisoformat(data["date"]),
        brand=data["brand"],
        flavor=data["flavor"],
        pack=data["pack"],
        qty=int(data["qty"]),
        author=data["author"],
        kind="Расход",
        comment=data["comment"],
    )
    row, doc_no = await append_operation(op, tg_user_id=user_id)
    text = format_operation_ok(op, doc_no=doc_no, row=row)
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer(text)
    await callback.answer("Списано")


async def on_rashod_cancel(callback: CallbackQuery) -> None:
    user_id = callback.from_user.id if callback.from_user else 0
    _pending_rashod.pop(user_id, None)
    if callback.message:
        await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.answer("Списание отменено.")
    await callback.answer()


def register_movement_handlers(dp: Dispatcher) -> None:
    dp.message.register(cmd_prihod, F.text.regexp(PRIHOD_RE))
    dp.message.register(cmd_rashod, F.text.regexp(RASHOD_RE))
    dp.callback_query.register(on_rashod_confirm, F.data == "rashod:confirm")
    dp.callback_query.register(on_rashod_cancel, F.data == "rashod:cancel")
