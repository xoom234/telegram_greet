"""HTTP API для Telegram Mini App поверх того же слоя, что и бот (bot/repository.py)."""
from __future__ import annotations

import logging
import re
from datetime import timedelta

from aiogram import Bot
from aiogram.utils.web_app import WebAppUser
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from bot.alerts import notify_admin
from bot.config import load_settings
from bot.errors import UserFacingError
from bot.formatting import compute_balances, format_operation_ok
from bot.health import HealthProblem, run_checks
from bot.repository import (
    MovementRow,
    Operation,
    append_operation_once,
    load_brands,
    load_packs,
    read_movements,
)
from bot.services import normalize_pack, parse_day, resolve_brand, stock_of, today
from bot.webapp_auth import AuthError, authenticate

logger = logging.getLogger(__name__)

MAX_QTY = 10_000
MAX_TEXT = 100
REQUEST_ID_RE = re.compile(r"[A-Za-z0-9-]{8,64}")
KINDS = {
    "in": "Приход",
    "приход": "Приход",
    "out": "Расход",
    "расход": "Расход",
}


class ValidationError(Exception):
    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__("validation error")
        self.fields = fields


def _user(request: Request) -> WebAppUser:
    settings = load_settings()
    user = authenticate(
        request.headers.get("authorization"),
        bot_token=settings.bot_token,
        allowed_user_ids=settings.allowed_user_ids,
    )
    request.scope["tg_user"] = user
    return user


def _movement_json(row: MovementRow) -> dict:
    return {
        "row": row.row_number,
        "date": row.date,
        "doc_no": row.doc_no,
        "brand": row.brand,
        "flavor": row.flavor,
        "pack": row.pack,
        "qty": row.qty,
        "kind": row.kind,
        "author": row.author,
    }


def _flavors_by_brand(rows: list[MovementRow]) -> dict[str, list[str]]:
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        if row.flavor:
            result.setdefault(row.brand, {}).setdefault(row.flavor.casefold(), row.flavor)
    return {
        brand: sorted(flavors.values(), key=str.casefold)
        for brand, flavors in result.items()
    }


async def health(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def status(request: Request) -> JSONResponse:
    """Для UptimeRobot: 200 если таблица и webhook в порядке, иначе 503."""
    checks = await run_checks()
    problems = {name: result for name, result in checks.items() if result != "ok"}
    if problems:
        details = "\n".join(f"{name}: {result}" for name, result in problems.items())
        await notify_admin("мониторинг", HealthProblem(details))
    return JSONResponse(
        {"ok": not problems, "checks": checks},
        status_code=503 if problems else 200,
    )


async def meta(request: Request) -> JSONResponse:
    _user(request)
    brands = await load_brands()
    packs = await load_packs()
    movements = await read_movements()
    return JSONResponse(
        {
            "brands": brands,
            "packs": packs,
            "flavors": _flavors_by_brand(movements),
            "today": today().strftime("%d.%m.%Y"),
        }
    )


async def stock(request: Request) -> JSONResponse:
    _user(request)
    query = request.query_params.get("brand", "").strip()
    hide_zero = request.query_params.get("hide_zero", "").lower() in {"1", "true", "yes"}

    brand_filter = None
    if query:
        brand_filter = await resolve_brand(query)
        if brand_filter is None:
            return JSONResponse({"error": f"Бренд «{query}» не найден"}, status_code=404)

    balances = compute_balances(await read_movements())
    items = [
        {"brand": b, "flavor": f, "pack": p, "qty": q}
        for (b, f, p), q in balances.items()
        if (brand_filter is None or b.casefold() == brand_filter.casefold())
        and (not hide_zero or q != 0)
    ]
    items.sort(key=lambda i: (i["brand"].casefold(), i["flavor"].casefold(), i["pack"]))
    return JSONResponse(
        {
            "brand": brand_filter,
            "items": items,
            "total_positions": len(items),
            "total_units": sum(i["qty"] for i in items),
        }
    )


async def list_operations(request: Request) -> JSONResponse:
    _user(request)
    raw = request.query_params.get("date", "")
    day = parse_day(raw, today())
    if day is None:
        return JSONResponse(
            {"error": "Непонятная дата. Формат: 04.10.2026 или 2026-10-04"},
            status_code=400,
        )
    day_s = day.strftime("%d.%m.%Y")
    rows = await read_movements()
    matched = [r for r in rows if r.date == day_s]
    return JSONResponse(
        {
            "date": day_s,
            "items": [_movement_json(r) for r in matched],
            "total_in": sum(r.qty for r in matched if r.kind == "Приход"),
            "total_out": sum(r.qty for r in matched if r.kind == "Расход"),
            "undated": sum(1 for r in rows if not r.date),
        }
    )


def _text(payload: dict, key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else ""


async def _validate_operation(payload: dict, user: WebAppUser) -> Operation:
    errors: dict[str, str] = {}

    kind = KINDS.get(_text(payload, "kind").casefold())
    if kind is None:
        errors["kind"] = "Укажите операцию: in (приход) или out (расход)"

    base = today()
    op_date = parse_day(_text(payload, "date"), base)
    if op_date is None:
        errors["date"] = "Непонятная дата. Формат: 04.10.2026 или 2026-10-04"
    elif op_date > base + timedelta(days=1):
        errors["date"] = "Дата в будущем"

    brand_raw = _text(payload, "brand")
    brand = await resolve_brand(brand_raw) if brand_raw else None
    if brand is None:
        errors["brand"] = f"Бренд «{brand_raw}» не найден" if brand_raw else "Укажите бренд"

    pack_raw = payload.get("pack")
    pack = normalize_pack(str(pack_raw), await load_packs()) if pack_raw is not None else None
    if pack is None:
        errors["pack"] = "Неизвестная фасовка"

    flavor = _text(payload, "flavor")
    if not flavor:
        errors["flavor"] = "Укажите вкус"
    elif len(flavor) > MAX_TEXT:
        errors["flavor"] = "Слишком длинное название вкуса"

    qty = payload.get("qty")
    if isinstance(qty, str) and qty.strip().isdigit():
        qty = int(qty.strip())
    if isinstance(qty, bool) or not isinstance(qty, int) or not 0 < qty <= MAX_QTY:
        errors["qty"] = f"Количество — целое число от 1 до {MAX_QTY}"

    author = _text(payload, "author") or user.first_name or load_settings().default_author
    if len(author) > MAX_TEXT:
        errors["author"] = "Слишком длинное имя"

    if errors:
        raise ValidationError(errors)

    # Тот же вкус в другом регистре не должен давать отдельную позицию на складе.
    for row in await read_movements():
        if row.brand == brand and row.flavor.casefold() == flavor.casefold():
            flavor = row.flavor
            break

    uname = f"@{user.username}" if user.username else user.first_name
    return Operation(
        date=op_date,
        brand=brand,
        flavor=flavor,
        pack=pack,
        qty=qty,
        author=author,
        kind=kind,  # type: ignore[arg-type]
        comment=f"{uname} id={user.id} (mini app)",
    )


async def _notify_chat(
    chat_id: int,
    op: Operation,
    *,
    doc_no: str,
    row: int,
    stock_after: int,
) -> None:
    """Подтверждение в чат с ботом, чтобы история записей из приложения осталась в Telegram."""
    text = "Записано через приложение\n\n" + format_operation_ok(op, doc_no=doc_no, row=row)
    if op.kind == "Расход" and stock_after <= 0:
        text += f"\nОстаток после списания: {stock_after} (вкус сохранён в учёте)"
    else:
        text += f"\nОстаток: {stock_after}"
    try:
        async with Bot(token=load_settings().bot_token) as bot:
            await bot.send_message(chat_id, text)
    except Exception:
        logger.warning("Не удалось отправить подтверждение в чат %s", chat_id, exc_info=True)


async def create_operation(request: Request) -> JSONResponse:
    user = _user(request)
    try:
        payload = await request.json()
    except ValueError:
        return JSONResponse({"error": "Тело запроса должно быть JSON"}, status_code=400)
    if not isinstance(payload, dict):
        return JSONResponse({"error": "Тело запроса должно быть JSON-объектом"}, status_code=400)

    request_id = _text(payload, "request_id") or None
    if request_id is not None and not REQUEST_ID_RE.fullmatch(request_id):
        raise ValidationError({"request_id": "Некорректный request_id"})

    op = await _validate_operation(payload, user)
    before = stock_of(compute_balances(await read_movements()), op.brand, op.flavor, op.pack)
    row, doc_no, duplicate = await append_operation_once(
        op, tg_user_id=user.id, request_id=request_id
    )
    if duplicate:
        after = stock_of(compute_balances(await read_movements()), op.brand, op.flavor, op.pack)
    else:
        after = before + op.qty if op.kind == "Приход" else before - op.qty
        await _notify_chat(user.id, op, doc_no=doc_no, row=row, stock_after=after)
    return JSONResponse(
        {
            "row": row,
            "doc_no": doc_no,
            "operation": {
                "date": op.date.strftime("%d.%m.%Y"),
                "brand": op.brand,
                "flavor": op.flavor,
                "pack": op.pack,
                "qty": op.qty,
                "kind": op.kind,
                "author": op.author,
            },
            "stock_after": after,
            "duplicate": duplicate,
        },
        status_code=200 if duplicate else 201,
    )


async def _auth_error(request: Request, exc: AuthError) -> JSONResponse:
    return JSONResponse({"error": exc.message}, status_code=exc.status)


async def _validation_error(request: Request, exc: ValidationError) -> JSONResponse:
    return JSONResponse({"error": "Проверьте поля", "fields": exc.fields}, status_code=422)


def _request_context(request: Request) -> str:
    context = f"{request.method} {request.url.path}"
    user = request.scope.get("tg_user")
    if user is not None:
        name = f"@{user.username}" if user.username else user.first_name
        context += f"\nПользователь: {name} (id {user.id})"
    return context


async def _user_facing_error(request: Request, exc: UserFacingError) -> JSONResponse:
    await notify_admin("приложение", exc, _request_context(request))
    return JSONResponse({"error": exc.user_message}, status_code=503)


async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("API error %s %s", request.method, request.url.path)
    await notify_admin("приложение", exc, _request_context(request))
    return JSONResponse({"error": "Внутренняя ошибка сервера"}, status_code=500)


routes = [
    Route("/api/v1/health", health),
    Route("/api/v1/status", status),
    Route("/api/v1/meta", meta),
    Route("/api/v1/stock", stock),
    Route("/api/v1/operations", list_operations, methods=["GET"]),
    Route("/api/v1/operations", create_operation, methods=["POST"]),
]

app = Starlette(
    routes=routes,
    exception_handlers={
        AuthError: _auth_error,
        ValidationError: _validation_error,
        UserFacingError: _user_facing_error,
        Exception: _unexpected_error,
    },
)
