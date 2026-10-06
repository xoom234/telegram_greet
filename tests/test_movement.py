"""Команды /приход и /расход через настоящий Dispatcher, Telegram и таблица подменены."""
from __future__ import annotations

import asyncio
import itertools
from datetime import date, datetime

import pytest
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, EditMessageText, GetMe, SendMessage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

import bot.handlers.movement as mv
from bot.main import build_dispatcher
from bot.repository import MovementRow

BRANDS = ["Palitra", "Darkside", "Сарма классик", "Сарма крепкая"]
PACKS = ["25 г", "200 г", "250 г"]
USER = User(id=1453663021, is_bot=False, first_name="Федор", username="xoomger")
BOT_USER = User(id=1, is_bot=True, first_name="Склад", username="sklad_tabak_bot")
CHAT = Chat(id=1453663021, type="private")
ids = itertools.count(100)


class Capture(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent: list[SendMessage] = []
        self.alerts: list[str] = []
        self.edits: list[str] = []

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, SendMessage):
            self.sent.append(method)
            return Message(message_id=next(ids), date=datetime.now(), chat=CHAT, text=method.text)
        if isinstance(method, AnswerCallbackQuery) and method.text:
            self.alerts.append(method.text)
        if isinstance(method, EditMessageText):
            self.edits.append(method.text)
        return True

    async def close(self):
        pass

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        yield b""


def row(n, flavor, qty, kind, brand="Darkside", pack="250 г"):
    return MovementRow(n, "05.10.2026", f"Н-{n:03d}", brand, flavor, pack, qty, kind, "Федор", "")


@pytest.fixture
def env(monkeypatch):
    state = {
        "rows": [row(4, "Red tea", 9, "Приход")],
        "written": [],
        "requests": set(),
    }

    async def load_brands():
        return list(BRANDS)

    async def load_packs():
        return list(PACKS)

    async def read_movements():
        return list(state["rows"])

    async def append_once(op, *, tg_user_id=None, request_id=None):
        if request_id in state["requests"]:
            return 99, "Н-099", True
        state["requests"].add(request_id)
        state["written"].append(op)
        return 99, "Н-099", False

    monkeypatch.setattr(mv, "load_brands", load_brands)
    monkeypatch.setattr(mv, "load_packs", load_packs)
    monkeypatch.setattr(mv, "read_movements", read_movements)
    monkeypatch.setattr(mv, "append_operation_once", append_once)
    monkeypatch.setattr(mv, "today", lambda: date(2026, 10, 6))
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    session = Capture()
    state["loop"] = loop
    state["bot"] = Bot("123:abc", session=session)
    state["session"] = session
    state["dp"] = build_dispatcher()
    yield state
    loop.close()
    asyncio.set_event_loop(None)


def command(text, user=USER):
    return Message(message_id=next(ids), date=datetime.now(), chat=CHAT, from_user=user, text=text)


def send(env, msg):
    env["loop"].run_until_complete(
        env["dp"].feed_update(env["bot"], Update(update_id=next(ids), message=msg))
    )
    return env["session"].sent[-1]


def press(env, prompt: SendMessage, data, cmd, user=USER):
    bot_msg = Message(
        message_id=next(ids), date=datetime.now(), chat=CHAT, from_user=BOT_USER,
        text=prompt.text, reply_to_message=cmd,
    )
    cb = CallbackQuery(id=str(next(ids)), from_user=user, chat_instance="x", data=data, message=bot_msg)
    env["loop"].run_until_complete(
        env["dp"].feed_update(env["bot"], Update(update_id=next(ids), callback_query=cb))
    )


def buttons(reply: SendMessage) -> dict[str, str]:
    markup = reply.reply_markup
    return {b.text: b.callback_data for line in markup.inline_keyboard for b in line} if markup else {}


def test_exact_prihod_writes_once_and_replies_to_command(env):
    cmd = command("/приход 06.10.2026 Darkside Red tea 250 г 2 Федор")
    reply = send(env, cmd)
    assert reply.text.startswith("Приход записан")
    assert reply.reply_parameters.message_id == cmd.message_id
    assert len(env["written"]) == 1


def test_negative_qty_is_not_written(env):
    reply = send(env, command("/приход Darkside Red tea 250 г -5"))
    assert "отрицательным" in reply.text
    assert env["written"] == []


def test_flavor_case_matches_existing(env):
    send(env, command("/приход Darkside red tea 250 г 1"))
    assert env["written"][0].flavor == "Red tea"


def test_fuzzy_brand_asks_then_writes_on_confirm(env):
    cmd = command("/приход Darksid Red tea 250 г 2")
    prompt = send(env, cmd)
    assert env["written"] == []
    btn = buttons(prompt)
    assert "✅ Darkside" in btn and "Отмена" in btn
    press(env, prompt, btn["✅ Darkside"], cmd)
    assert [(o.brand, o.flavor) for o in env["written"]] == [("Darkside", "Red tea")]
    assert env["session"].sent[-1].text.startswith("Приход записан")


def test_double_confirm_does_not_duplicate(env):
    cmd = command("/приход Darksid Red tea 250 г 2")
    prompt = send(env, cmd)
    data = buttons(prompt)["✅ Darkside"]
    press(env, prompt, data, cmd)
    press(env, prompt, data, cmd)
    assert len(env["written"]) == 1
    assert "уже записана" in env["session"].sent[-1].text


def test_overdraw_asks_and_cancel_writes_nothing(env):
    cmd = command("/расход Darkside Red tea 250 г 50")
    prompt = send(env, cmd)
    assert "Остаток станет -41" in prompt.text
    assert env["written"] == []
    press(env, prompt, buttons(prompt)["Отмена"], cmd)
    assert env["written"] == []
    assert env["session"].edits[-1].endswith("Отменено.")


def test_overdraw_force_writes(env):
    cmd = command("/расход Darkside Red tea 250 г 50")
    prompt = send(env, cmd)
    press(env, prompt, buttons(prompt)["Всё равно списать"], cmd)
    assert env["written"][0].qty == 50
    assert "Остаток: -41" in env["session"].sent[-1].text


def test_unknown_flavor_rashod_warns(env):
    prompt = send(env, command("/расход Darkside Новый 250 г 1"))
    assert "ещё нет на складе" in prompt.text
    assert env["written"] == []


def test_fuzzy_brand_then_overdraw_keeps_brand(env):
    cmd = command("/расход Darksid Red tea 250 г 50")
    prompt = send(env, cmd)
    press(env, prompt, buttons(prompt)["✅ Darkside"], cmd)
    overdraw = env["session"].sent[-1]
    assert "Остаток станет -41" in overdraw.text
    press(env, overdraw, buttons(overdraw)["Всё равно списать"], cmd)
    assert [(o.brand, o.qty) for o in env["written"]] == [("Darkside", 50)]


def test_only_author_can_confirm(env):
    cmd = command("/приход Darksid Red tea 250 г 2")
    prompt = send(env, cmd)
    stranger = User(id=5, is_bot=False, first_name="Чужой")
    press(env, prompt, buttons(prompt)["✅ Darkside"], cmd, user=stranger)
    assert env["written"] == []
    assert "только автор" in env["session"].alerts[-1]


def test_enough_stock_rashod_writes_without_asking(env):
    reply = send(env, command("/расход Darkside Red tea 250 г 9"))
    assert reply.text.startswith("Расход записан")
    assert "Остаток: 0" in reply.text
