import csv
import io

import pytest
from fastapi.testclient import TestClient

from demo_bank.server import PAGE_SIZE, app

PERIOD = {"date_from": "2026-01-01", "date_to": "2026-06-17"}


@pytest.fixture
def client():
    with TestClient(app, follow_redirects=False) as test_client:
        yield test_client


@pytest.fixture
def logged_in(client):
    client.post("/login", data={"username": "demo", "password": "whatever"})
    return client


def test_accounts_requires_login(client):
    response = client.get("/accounts")
    assert response.status_code == 302
    assert response.headers["location"] == "/login"


def test_api_returns_401_for_anonymous(client):
    assert client.get("/api/products").status_code == 401


def test_login_page_renders_form(client):
    response = client.get("/login")
    assert response.status_code == 200
    assert 'data-testid="login-form"' in response.text


def test_login_does_not_store_password(logged_in):
    from demo_bank import server

    assert not hasattr(server, "SUBMITTED_PASSWORDS")
    assert "whatever" not in repr(server.SESSIONS)


def test_api_products_returns_five(logged_in):
    payload = logged_in.get("/api/products").json()
    assert len(payload["products"]) == 5
    assert {p["product_id"] for p in payload["products"]} == {
        "card_001",
        "acc_002",
        "sav_003",
        "dep_004",
        "cred_005",
    }


def test_api_transactions_paginates_with_cursor(logged_in):
    first = logged_in.get("/api/products/card_001/transactions", params=PERIOD).json()
    assert len(first["items"]) == PAGE_SIZE
    assert first["next_cursor"] is not None

    second = logged_in.get(
        "/api/products/card_001/transactions",
        params={**PERIOD, "cursor": first["next_cursor"]},
    ).json()
    assert second["next_cursor"] is None

    ids = {item["id"] for item in first["items"]} | {item["id"] for item in second["items"]}
    assert len(ids) == 34


def test_api_transactions_respects_period(logged_in):
    payload = logged_in.get(
        "/api/products/card_001/transactions",
        params={"date_from": "2026-06-01", "date_to": "2026-06-17"},
    ).json()
    assert payload["items"]
    assert all("2026-06-01" <= item["operation_date"] <= "2026-06-17" for item in payload["items"])


def test_export_csv_is_cp1251_with_semicolons(logged_in):
    response = logged_in.get(
        "/export/transactions.csv", params={"product_id": "card_001", **PERIOD}
    )
    assert response.status_code == 200
    assert "windows-1251" in response.headers["content-type"]

    text = response.content.decode("cp1251")
    rows = list(csv.reader(io.StringIO(text), delimiter=";"))
    assert rows[0] == [
        "Дата операции",
        "Дата обработки",
        "Сумма",
        "Валюта",
        "Описание",
        "Контрагент",
        "Категория",
        "Статус",
    ]
    assert len(rows) == 35
    assert "," in rows[1][2]


def test_product_page_renders_first_page_and_load_more(logged_in):
    response = logged_in.get("/accounts/card_001")
    assert response.status_code == 200
    assert response.text.count('data-testid="tx-row"') == PAGE_SIZE
    assert 'data-testid="load-more"' in response.text


def test_dashboard_lists_all_products_with_pending_balances(logged_in):
    response = logged_in.get("/accounts")
    assert response.text.count('data-testid="product-item"') == 5
    assert response.text.count('data-balance-pending="1"') == 5


def test_unknown_product_returns_404(logged_in):
    assert logged_in.get("/accounts/nope_999").status_code == 404
