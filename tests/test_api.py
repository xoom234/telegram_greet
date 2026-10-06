from __future__ import annotations

import hashlib
import hmac
import json
import time
from datetime import date
from urllib.parse import urlencode

import pytest
from starlette.testclient import TestClient

import bot.api as api
import bot.services as services
from bot.config import Settings
from bot.repository import MovementRow

TOKEN = "123456:TEST-TOKEN"
BRANDS = ["Сарма классик", "Darkside", "Palitra"]
PACKS = ["25 г", "40 г", "200 г", "250 г"]


def sign_init_data(user: dict, *, token: str = TOKEN, auth_date: int | None = None) -> str:
    fields = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAH",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    check = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


USER = {"id": 1453663021, "first_name": "Федор", "username": "xoomger"}


def auth(user: dict = USER, **kw) -> dict:
    return {"Authorization": f"tma {sign_init_data(user, **kw)}"}


def mv(row, brand, flavor, pack, qty, kind, day="05.10.2026", author="Федор"):
    return MovementRow(row, day, f"Н-{row:03d}", brand, flavor, pack, qty, kind, author, "")


@pytest.fixture
def repo(monkeypatch):
    state = {
        "rows": [
            mv(4, "Сарма классик", "Буратино", "200 г", 10, "Приход"),
            mv(5, "Сарма классик", "Буратино", "200 г", 4, "Расход"),
            mv(6, "Darkside", "Red tea", "250 г", 3, "Приход", day="04.10.2026"),
            mv(7, "Palitra", "Pear Date", "200 г", 1, "Приход", day=""),
        ],
        "appended": [],
        "allowed": frozenset(),
    }

    async def load_brands():
        return list(BRANDS)

    async def load_packs():
        return list(PACKS)

    async def read_movements():
        return list(state["rows"])

    async def append_operation(op, *, tg_user_id=None):
        state["appended"].append((op, tg_user_id))
        return 99, "Н-099"

    monkeypatch.setattr(api, "load_brands", load_brands)
    monkeypatch.setattr(services, "load_brands", load_brands)
    monkeypatch.setattr(api, "load_packs", load_packs)
    monkeypatch.setattr(api, "read_movements", read_movements)
    monkeypatch.setattr(api, "append_operation", append_operation)

    class FakeBot:
        def __init__(self, token):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def send_message(self, chat_id, text):
            state["sent"].append((chat_id, text))

    state["sent"] = []
    monkeypatch.setattr(api, "Bot", FakeBot)
    monkeypatch.setattr(api, "today", lambda: date(2026, 10, 5))
    monkeypatch.setattr(
        api,
        "load_settings",
        lambda: Settings(TOKEN, state["allowed"], "Федор", 300),
    )
    return state


@pytest.fixture
def client(repo):
    return TestClient(api.app)


def test_health_without_auth(client):
    assert client.get("/api/v1/health").json() == {"ok": True}


def test_requires_telegram_auth(client):
    r = client.get("/api/v1/meta")
    assert r.status_code == 401


def test_rejects_forged_signature(client):
    r = client.get("/api/v1/meta", headers=auth(token="999:OTHER"))
    assert r.status_code == 401


def test_rejects_stale_init_data(client):
    r = client.get("/api/v1/meta", headers=auth(auth_date=int(time.time()) - 2 * 86400))
    assert r.status_code == 401


def test_whitelist_blocks_other_users(client, repo):
    repo["allowed"] = frozenset({1})
    r = client.get("/api/v1/meta", headers=auth())
    assert r.status_code == 403
    assert "1453663021" in r.json()["error"]


def test_meta(client):
    data = client.get("/api/v1/meta", headers=auth()).json()
    assert data["brands"] == BRANDS
    assert data["packs"] == PACKS
    assert data["flavors"]["Сарма классик"] == ["Буратино"]
    assert data["today"] == "05.10.2026"


def test_stock_all(client):
    data = client.get("/api/v1/stock", headers=auth()).json()
    items = {(i["brand"], i["flavor"], i["pack"]): i["qty"] for i in data["items"]}
    assert items[("Сарма классик", "Буратино", "200 г")] == 6
    assert data["total_positions"] == 3
    assert data["total_units"] == 10


def test_stock_by_brand_prefix(client):
    data = client.get("/api/v1/stock", params={"brand": "сарма"}, headers=auth()).json()
    assert data["brand"] == "Сарма классик"
    assert [i["flavor"] for i in data["items"]] == ["Буратино"]


def test_stock_unknown_brand(client):
    r = client.get("/api/v1/stock", params={"brand": "Нет такого"}, headers=auth())
    assert r.status_code == 404


def test_operations_by_date(client):
    data = client.get("/api/v1/operations", params={"date": "2026-10-04"}, headers=auth()).json()
    assert data["date"] == "04.10.2026"
    assert [i["flavor"] for i in data["items"]] == ["Red tea"]
    assert data["total_in"] == 3
    assert data["undated"] == 1


def test_operations_default_today(client):
    data = client.get("/api/v1/operations", headers=auth()).json()
    assert data["date"] == "05.10.2026"
    assert data["total_in"] == 10 and data["total_out"] == 4


def test_operations_bad_date(client):
    r = client.get("/api/v1/operations", params={"date": "31.02.2026"}, headers=auth())
    assert r.status_code == 400


def test_create_rashod_keeps_flavor_case_and_reports_stock(client, repo):
    r = client.post(
        "/api/v1/operations",
        headers=auth(),
        json={"kind": "out", "brand": "Сарма классик", "flavor": "буратино", "pack": "200", "qty": 10},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["doc_no"] == "Н-099"
    assert body["stock_after"] == -4
    op, tg_id = repo["appended"][0]
    assert (op.kind, op.flavor, op.pack, op.author) == ("Расход", "Буратино", "200 г", "Федор")
    assert op.date == date(2026, 10, 5)
    assert op.comment == "@xoomger id=1453663021 (mini app)"
    assert tg_id == 1453663021


def test_create_prihod_new_flavor(client, repo):
    r = client.post(
        "/api/v1/operations",
        headers=auth(),
        json={
            "kind": "in",
            "date": "04.10.2026",
            "brand": "Darkside",
            "flavor": "Bounty",
            "pack": "250 г",
            "qty": "5",
            "author": "Федя",
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["stock_after"] == 5
    op, _ = repo["appended"][0]
    assert (op.kind, op.flavor, op.author, op.date) == ("Приход", "Bounty", "Федя", date(2026, 10, 4))


def test_create_validation_errors(client, repo):
    r = client.post(
        "/api/v1/operations",
        headers=auth(),
        json={"kind": "move", "brand": "Нет", "flavor": "", "pack": "33", "qty": 0, "date": "2027-01-01"},
    )
    assert r.status_code == 422
    assert set(r.json()["fields"]) == {"kind", "brand", "flavor", "pack", "qty", "date"}
    assert repo["appended"] == []


def test_create_sends_chat_confirmation(client, repo):
    client.post(
        "/api/v1/operations",
        headers=auth(),
        json={"kind": "out", "brand": "Сарма классик", "flavor": "Буратино", "pack": "200 г", "qty": 10},
    )
    chat_id, text = repo["sent"][0]
    assert chat_id == 1453663021
    assert text.startswith("Записано через приложение")
    assert "Накладная: Н-099" in text
    assert "Остаток после списания: -4" in text


def test_validation_error_sends_nothing(client, repo):
    client.post("/api/v1/operations", headers=auth(), json={"kind": "in"})
    assert repo["sent"] == []


def test_chat_failure_does_not_break_write(client, repo, monkeypatch):
    class BrokenBot:
        def __init__(self, token):
            pass

        async def __aenter__(self):
            raise RuntimeError("telegram down")

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(api, "Bot", BrokenBot)
    r = client.post(
        "/api/v1/operations",
        headers=auth(),
        json={"kind": "in", "brand": "Darkside", "flavor": "Bounty", "pack": "250 г", "qty": 1},
    )
    assert r.status_code == 201
    assert len(repo["appended"]) == 1


def test_create_requires_auth(client, repo):
    r = client.post("/api/v1/operations", json={"kind": "in"})
    assert r.status_code == 401
    assert repo["appended"] == []
