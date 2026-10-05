"""Vercel-функция: Telegram присылает сюда апдейты (webhook)."""
from __future__ import annotations

import hmac
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram import Bot  # noqa: E402
from aiogram.types import Update  # noqa: E402

from bot.config import load_settings  # noqa: E402
from bot.logging_setup import setup_logging  # noqa: E402
from bot.main import build_dispatcher  # noqa: E402

setup_logging()
logger = logging.getLogger("bot.webhook")

_dp = build_dispatcher()


def _secret_ok(headers: list[tuple[bytes, bytes]]) -> bool:
    expected = os.getenv("WEBHOOK_SECRET", "")
    if not expected:
        logger.error("WEBHOOK_SECRET не задан — апдейты отклоняются")
        return False
    got = dict(headers).get(b"x-telegram-bot-api-secret-token", b"").decode()
    return hmac.compare_digest(got, expected)


async def _read_body(receive) -> bytes:
    body = b""
    while True:
        message = await receive()
        body += message.get("body", b"")
        if not message.get("more_body"):
            return body


async def _respond(send, status: int, text: str = "ok") -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": text.encode()})


async def _lifespan(receive, send) -> None:
    while True:
        message = await receive()
        if message["type"] == "lifespan.startup":
            await send({"type": "lifespan.startup.complete"})
        elif message["type"] == "lifespan.shutdown":
            await send({"type": "lifespan.shutdown.complete"})
            return


async def app(scope, receive, send) -> None:
    if scope["type"] == "lifespan":
        await _lifespan(receive, send)
        return
    if scope["type"] != "http":
        return

    if scope["method"] != "POST":
        await _respond(send, 200, "sklad bot webhook")
        return
    if not _secret_ok(scope.get("headers", [])):
        await _respond(send, 403, "forbidden")
        return

    body = await _read_body(receive)
    # Telegram повторяет доставку при не-200, поэтому ошибки только логируем.
    try:
        async with Bot(token=load_settings().bot_token) as bot:
            update = Update.model_validate(json.loads(body), context={"bot": bot})
            await _dp.feed_update(bot, update)
    except Exception:
        logger.exception("Ошибка обработки апдейта")
    await _respond(send, 200)
