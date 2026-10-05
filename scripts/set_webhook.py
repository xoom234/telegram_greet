#!/usr/bin/env python3
"""Включить webhook на Vercel или вернуть бота в режим polling.

  python scripts/set_webhook.py https://<проект>.vercel.app/api/webhook
  python scripts/set_webhook.py --info
  python scripts/set_webhook.py --delete
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiogram import Bot  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from bot.main import build_dispatcher  # noqa: E402


async def main(arg: str) -> None:
    load_dotenv(override=True)
    token = os.getenv("BOT_TOKEN", "").strip()
    async with Bot(token=token) as bot:
        if arg == "--delete":
            await bot.delete_webhook(drop_pending_updates=False)
            print("Webhook удалён, можно запускать polling (python -m bot.main).")
        elif arg != "--info":
            secret = os.getenv("WEBHOOK_SECRET", "").strip()
            if not secret:
                sys.exit("Задайте WEBHOOK_SECRET в .env (то же значение, что на Vercel).")
            await bot.set_webhook(
                url=arg,
                secret_token=secret,
                # По одному апдейту за раз: запись в «Накладные» без гонок между инстансами.
                max_connections=1,
                allowed_updates=build_dispatcher().resolve_used_update_types(),
            )
            print(f"Webhook установлен: {arg}")
        info = await bot.get_webhook_info()
        print(
            f"url={info.url or '-'} pending={info.pending_update_count} "
            f"last_error={info.last_error_message or '-'}"
        )


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    asyncio.run(main(sys.argv[1]))
