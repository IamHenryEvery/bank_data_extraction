import pytest

from bank_extractor.adapters.demo_bank import api
from bank_extractor.errors import ChannelFailed
from bank_extractor.models import Period

pytestmark = pytest.mark.integration

PERIOD = Period.model_validate({"from": "2026-01-01", "to": "2026-06-17"})


def test_fetch_products_returns_all_five(authenticated_page, demo_server):
    products = api.fetch_products(
        authenticated_page, demo_server, with_balances=True, with_requisites=True
    )
    assert len(products) == 5
    assert {p.product_id for p in products} == {
        "card_001",
        "acc_002",
        "sav_003",
        "dep_004",
        "cred_005",
    }


def test_fetch_products_keeps_numbers_masked(authenticated_page, demo_server):
    products = api.fetch_products(
        authenticated_page, demo_server, with_balances=True, with_requisites=True
    )
    for product in products:
        assert product.masked_number is None or product.masked_number.startswith("**** ")


def test_balances_omitted_without_scope(authenticated_page, demo_server):
    products = api.fetch_products(
        authenticated_page, demo_server, with_balances=False, with_requisites=True
    )
    assert all(p.balance is None and p.available_balance is None for p in products)


def test_requisites_omitted_without_scope(authenticated_page, demo_server):
    products = api.fetch_products(
        authenticated_page, demo_server, with_balances=True, with_requisites=False
    )
    assert all(p.requisites is None for p in products)


def test_fetch_transactions_walks_all_pages(authenticated_page, demo_server):
    rows = api.fetch_transactions(authenticated_page, demo_server, "card_001", PERIOD)
    assert len(rows) == 34
    assert len({row.external_id for row in rows}) == 34


def test_fetch_transactions_respects_period(authenticated_page, demo_server):
    narrow = Period.model_validate({"from": "2026-06-01", "to": "2026-06-17"})
    rows = api.fetch_transactions(authenticated_page, demo_server, "card_001", narrow)
    assert all("2026-06-01" <= row.operation_date <= "2026-06-17" for row in rows)
    assert len(rows) < 34


@pytest.mark.scenario("empty_history")
def test_empty_history_is_not_an_error(scenario_page, demo_server):
    rows = api.fetch_transactions(scenario_page, demo_server, "acc_002", PERIOD)
    assert rows == []


@pytest.mark.scenario("api_down")
def test_dead_api_raises_channel_failed(scenario_page, demo_server):
    with pytest.raises(ChannelFailed, match="503"):
        api.fetch_transactions(scenario_page, demo_server, "card_001", PERIOD)
