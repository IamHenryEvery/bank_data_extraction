import pytest

from bank_extractor.adapters.demo_bank import dom
from bank_extractor.models import Period

pytestmark = pytest.mark.integration

PERIOD = Period.model_validate({"from": "2026-01-01", "to": "2026-06-17"})


def test_finds_all_products_on_dashboard(authenticated_page, demo_server):
    products, warnings = dom.fetch_products(
        authenticated_page, demo_server, with_balances=True, with_requisites=False
    )
    assert len(products) == 5
    assert warnings == []


def test_waits_for_balances_to_load(authenticated_page, demo_server):
    products, _ = dom.fetch_products(
        authenticated_page, demo_server, with_balances=True, with_requisites=False
    )
    assert all(product.balance not in (None, "", "—") for product in products)


@pytest.mark.scenario("api_down")
def test_missing_balances_are_reported_not_faked(scenario_page, demo_server):
    products, warnings = dom.fetch_products(
        scenario_page, demo_server, with_balances=True, with_requisites=False, balance_timeout_s=3
    )
    assert len(products) == 5
    assert any("остатк" in warning for warning in warnings)
    assert all(product.balance is None for product in products)


def test_reads_requisites_when_scope_allows(authenticated_page, demo_server):
    products, _ = dom.fetch_products(
        authenticated_page, demo_server, with_balances=False, with_requisites=True
    )
    with_req = [p for p in products if p.requisites]
    assert len(with_req) == 1
    assert with_req[0].product_id == "acc_002"
    assert with_req[0].requisites["bic"] == "044525225"


def test_requisites_pages_not_opened_without_scope(authenticated_page, demo_server):
    products, _ = dom.fetch_products(
        authenticated_page, demo_server, with_balances=False, with_requisites=False
    )
    assert all(product.requisites is None for product in products)


def test_pagination_collects_every_row_without_duplicates(authenticated_page, demo_server):
    rows = dom.fetch_transactions(authenticated_page, demo_server, "card_001", PERIOD)
    assert len(rows) == 34
    keys = {(r.operation_date, r.amount, r.description) for r in rows}
    assert len(keys) == 34


@pytest.mark.scenario("empty_history")
def test_empty_history_marker_yields_no_rows(scenario_page, demo_server):
    rows = dom.fetch_transactions(scenario_page, demo_server, "acc_002", PERIOD)
    assert rows == []


@pytest.mark.scenario("broken_formats")
def test_broken_formats_are_passed_through_untouched(scenario_page, demo_server):
    rows = dom.fetch_transactions(scenario_page, demo_server, "card_001", PERIOD)
    assert len(rows) == 34
    assert any("." in row.operation_date for row in rows)
    assert any("июн" in row.operation_date for row in rows)
