"""Команды /приход и /расход.

Подтверждения (похожий бренд, расход больше остатка) — кнопками под ответом.
Ответ бота отправляется reply на команду, поэтому по нажатию кнопки исходный
текст берётся из reply_to_message и разбирается заново: на Vercel между
запросами нет общей памяти. Каждая команда пишется с request_id
«tg<chat>-<message>», так что повторное нажатие не создаёт вторую строку.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from aiogram import Dispatcher, F
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.formatting import compute_balances, format_operation_ok
from bot.parsing import ParseErr, ParseOk, parse_movement_args, strip_command, with_brand
from bot.repository import Operation, append_operation_once, load_brands, load_packs, read_movements
from bot.services import canonical_flavor, position_known, stock_of, today

logger = logging.getLogger(__name__)

PRIHOD_RE = re.compile(r"^/(приход|prihod|in)(@\w+)?(\s|$)", re.I)
RASHOD_RE = re.compile(r"^/(расход|рассход|rashod|out)(@\w+)?(\s|$)", re.I)

CB_PREFIX = "mv"
ACTION_BRAND = "b"   # бренд подтверждён
ACTION_FORCE = "f"   # бренд подтверждён и расход в минус разрешён
ACTION_CANCEL = "x"

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


@dataclass
class Reply:
    text: str
    markup: InlineKeyboardMarkup | None = None


def _kind_of(text: str) -> str | None:
    if PRIHOD_RE.match(text):
        return "Приход"
    if RASHOD_RE.match(text):
        return "Расход"
    return None


def _tg_comment(message: Message) -> str:
    user = message.from_user
    if user is None:
        return "telegram"
    uname = f"@{user.username}" if user.username else user.full_name
    return f"{uname} id={user.id}"


def _cb(action: str, brand_idx: int = 0) -> str:
    return f"{CB_PREFIX}:{action}:{brand_idx}"


def _cancel_button() -> InlineKeyboardButton:
    return InlineKeyboardButton(text="Отмена", callback_data=_cb(ACTION_CANCEL))


def _ask_brand(ok: ParseOk, brands: list[str]) -> Reply:
    buttons = [
        [InlineKeyboardButton(text=f"✅ {b}", callback_data=_cb(ACTION_BRAND, brands.index(b)))]
        for b in ok.brand_candidates
        if b in brands
    ]
    buttons.append([_cancel_button()])
    return Reply(
        "Точного совпадения бренда нет. Какой бренд имелся в виду?",
        InlineKeyboardMarkup(inline_keyboard=buttons),
    )


def _ask_overdraw(ok: ParseOk, stock: int, known: bool, brand_idx: int) -> Reply:
    after = stock - ok.qty
    lines = [f"{ok.brand} / {ok.flavor} / {ok.pack}"]
    if not known:
        lines.append("Такой позиции ещё нет на складе.")
    lines.append(f"На складе {stock} шт., списывается {ok.qty}. Остаток станет {after}.")
    lines.append("Всё равно записать?")
    markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Всё равно списать", callback_data=_cb(ACTION_FORCE, brand_idx))],
        [_cancel_button()],
    ])
    return Reply("\n".join(lines), markup)


async def process_movement(
    command: Message,
    *,
    brand_idx: int | None = None,
    force: bool = False,
) -> Reply:
    """Разобрать команду, при необходимости спросить подтверждение, иначе записать."""
    text = command.text or ""
    kind = _kind_of(text)
    usage = USAGE_PRIHOD if kind == "Приход" else USAGE_RASHOD
    args = strip_command(text)
    if kind is None or not args:
        return Reply(usage)

    brands = await load_brands()
    packs = await load_packs()
    result = parse_movement_args(args, brands=brands, packs=packs, today=today())
    if isinstance(result, ParseOk) and brand_idx is not None:
        if not 0 <= brand_idx < len(brands):
            return Reply("Список брендов изменился. Отправьте команду заново.")
        result = with_brand(result, brands[brand_idx])
    if isinstance(result, ParseErr):
        return Reply(result.message + "\n\n" + usage)
    ok = result
    if not ok.brand_exact:
        return _ask_brand(ok, brands)

    movements = await read_movements()
    ok.flavor = canonical_flavor(movements, ok.brand, ok.flavor)
    stock = stock_of(compute_balances(movements), ok.brand, ok.flavor, ok.pack)
    if kind == "Расход" and not force and stock - ok.qty < 0:
        known = position_known(movements, ok.brand, ok.flavor, ok.pack)
        return _ask_overdraw(ok, stock, known, brands.index(ok.brand))

    op = Operation(
        date=ok.date,
        brand=ok.brand,
        flavor=ok.flavor,
        pack=ok.pack,
        qty=ok.qty,
        author=ok.author,
        kind=kind,  # type: ignore[arg-type]
        comment=_tg_comment(command),
    )
    row, doc_no, duplicate = await append_operation_once(
        op,
        tg_user_id=command.from_user.id if command.from_user else None,
        request_id=f"tg{command.chat.id}-{command.message_id}",
    )
    if duplicate:
        return Reply(f"Эта команда уже записана: накладная {doc_no} (строка {row}).")
    reply = format_operation_ok(op, doc_no=doc_no, row=row)
    if kind == "Расход":
        after = stock - ok.qty
        reply += f"\nОстаток: {after}" + (" (вкус сохранён в учёте)" if after <= 0 else "")
    return Reply(reply)


async def cmd_movement(message: Message) -> None:
    reply = await process_movement(message)
    await message.reply(reply.text, reply_markup=reply.markup)


async def on_movement_callback(callback: CallbackQuery) -> None:
    _, action, raw_idx = (callback.data or "").split(":", 2)
    prompt = callback.message
    command = prompt.reply_to_message if isinstance(prompt, Message) else None
    if command is None or not command.text:
        await callback.answer("Команда устарела — отправьте её заново", show_alert=True)
        return
    if callback.from_user and command.from_user and callback.from_user.id != command.from_user.id:
        await callback.answer("Подтвердить может только автор команды", show_alert=True)
        return

    await prompt.edit_reply_markup(reply_markup=None)
    if action == ACTION_CANCEL:
        await prompt.edit_text(f"{prompt.text}\n\nОтменено.")
        await callback.answer("Отменено")
        return

    reply = await process_movement(command, brand_idx=int(raw_idx), force=action == ACTION_FORCE)
    await command.reply(reply.text, reply_markup=reply.markup)
    await callback.answer()


def register_movement_handlers(dp: Dispatcher) -> None:
    dp.message.register(cmd_movement, F.text.regexp(PRIHOD_RE))
    dp.message.register(cmd_movement, F.text.regexp(RASHOD_RE))
    dp.callback_query.register(on_movement_callback, F.data.startswith(f"{CB_PREFIX}:"))
