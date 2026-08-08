import pytest
from fastapi.testclient import TestClient

from demo_bank.scenarios import BROKEN_PRODUCT, EMPTY_PRODUCT, FAILING_PRODUCT
from demo_bank.server import app

PERIOD = {"date_from": "2026-01-01", "date_to": "2026-06-17"}


def login(scenario: str) -> TestClient:
    client = TestClient(app, follow_redirects=False)
    client.get("/login", params={"scenario": scenario})
    client.post("/login", data={"username": "demo", "password": "x"})
    return client


def test_default_scenario_returns_data():
    client = login("default")
    payload = client.get(f"/api/products/{BROKEN_PRODUCT}/transactions", params=PERIOD).json()
    assert payload["items"]


def test_empty_history_returns_empty_list_not_error():
    client = login("empty_history")
    response = client.get(f"/api/products/{EMPTY_PRODUCT}/transactions", params=PERIOD)
    assert response.status_code == 200
    assert response.json()["items"] == []
    assert response.json()["next_cursor"] is None


def test_empty_history_page_shows_empty_marker():
    client = login("empty_history")
    page = client.get(f"/accounts/{EMPTY_PRODUCT}", params=PERIOD)
    assert 'data-testid="empty-history"' in page.text
    assert 'data-testid="tx-row"' not in page.text


def test_empty_history_affects_only_one_product():
    client = login("empty_history")
    payload = client.get(f"/api/products/{BROKEN_PRODUCT}/transactions", params=PERIOD).json()
    assert payload["items"]


def test_broken_formats_changes_dates_and_amounts():
    client = login("broken_formats")
    payload = client.get(f"/api/products/{BROKEN_PRODUCT}/transactions", params=PERIOD).json()
    items = payload["items"]
    dates = {item["operation_date"] for item in items}
    assert any("." in value for value in dates)
    assert any("июн" in value for value in dates)
    assert any(" " in item["amount"] for item in items)
    assert any(item["amount"].startswith("(") for item in items)


def test_api_down_returns_503_for_transactions():
    client = login("api_down")
    response = client.get(f"/api/products/{BROKEN_PRODUCT}/transactions", params=PERIOD)
    assert response.status_code == 503


def test_api_down_keeps_export_and_pages_working():
    client = login("api_down")
    export = client.get("/export/transactions.csv", params={"product_id": BROKEN_PRODUCT, **PERIOD})
    assert export.status_code == 200
    assert client.get(f"/accounts/{BROKEN_PRODUCT}").status_code == 200


def test_export_down_kills_api_and_export_but_not_pages():
    client = login("export_down")
    api = client.get(f"/api/products/{BROKEN_PRODUCT}/transactions", params=PERIOD)
    export = client.get("/export/transactions.csv", params={"product_id": BROKEN_PRODUCT, **PERIOD})
    assert api.status_code == 503
    assert export.status_code == 500
    assert client.get(f"/accounts/{BROKEN_PRODUCT}").status_code == 200


def test_slow_load_fails_first_attempt_then_succeeds():
    client = login("slow_load")
    first = client.get(f"/api/products/{BROKEN_PRODUCT}/transactions", params=PERIOD)
    second = client.get(f"/api/products/{BROKEN_PRODUCT}/transactions", params=PERIOD)
    assert first.status_code == 504
    assert second.status_code == 200


def test_partial_failure_kills_one_product_everywhere():
    client = login("partial_failure")
    api = client.get(f"/api/products/{FAILING_PRODUCT}/transactions", params=PERIOD)
    export_params = {"product_id": FAILING_PRODUCT, **PERIOD}
    export = client.get("/export/transactions.csv", params=export_params)
    assert api.status_code == 500
    assert export.status_code == 500
    assert client.get(f"/accounts/{FAILING_PRODUCT}").status_code == 500

    alive = client.get(f"/api/products/{BROKEN_PRODUCT}/transactions", params=PERIOD)
    assert alive.status_code == 200


def test_session_expired_drops_session_after_three_requests():
    client = login("session_expired")
    codes = [
        client.get(f"/api/products/{BROKEN_PRODUCT}/transactions", params=PERIOD).status_code
        for _ in range(5)
    ]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 401


def test_duplicate_page_overlaps_second_page_by_one_row():
    client = login("duplicate_page")
    url = f"/api/products/{BROKEN_PRODUCT}/transactions"
    first = client.get(url, params={**PERIOD, "cursor": "0"}).json()
    second = client.get(url, params={**PERIOD, "cursor": first["next_cursor"]}).json()

    first_ids = [item["id"] for item in first["items"]]
    second_ids = [item["id"] for item in second["items"]]
    assert second_ids[0] == first_ids[-1]
    assert len(set(first_ids) & set(second_ids)) == 1


def test_stuck_cursor_serves_the_same_page_again():
    client = login("stuck_cursor")
    url = f"/api/products/{BROKEN_PRODUCT}/transactions"
    first = client.get(url, params={**PERIOD, "cursor": "0"}).json()
    second = client.get(url, params={**PERIOD, "cursor": first["next_cursor"]}).json()

    assert [item["id"] for item in second["items"]] == [item["id"] for item in first["items"]]


@pytest.mark.parametrize("scenario", ["default", "empty_history", "broken_formats"])
def test_products_endpoint_survives_data_scenarios(scenario):
    client = login(scenario)
    assert len(client.get("/api/products").json()["products"]) == 5
