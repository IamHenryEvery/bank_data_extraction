from datetime import UTC, datetime

import pytest

from bank_extractor.adapters.registry import get_adapter
from bank_extractor.config import AppConfig
from bank_extractor.consent import ConsentGrant
from bank_extractor.enums import Channel
from bank_extractor.extraction.runner import run_extraction
from bank_extractor.report import RunStatus

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)

GRANT = ConsentGrant.model_validate(
    {
        "consent_id": "cns_test",
        "client_ref": "client_x",
        "bank": "demo_bank",
        "scopes": ["products", "balances", "transactions", "requisites"],
        "period": {"from": "2026-01-01", "to": "2026-06-17"},
        "granted_at": "2026-08-06T09:00:00Z",
        "expires_at": "2036-01-01T00:00:00Z",
        "method": "explicit_ui_confirmation",
    }
)


class PageSession:
    mode_resolved = "launch"

    def __init__(self, page):
        self._page = page

    def page(self):
        return self._page


def config_for(base_url: str) -> AppConfig:
    return AppConfig.model_validate(
        {
            "bank": "demo_bank",
            "base_url": base_url,
            "period": {"from": "2026-01-01", "to": "2026-06-17"},
            "consent_file": "./consent.json",
            "retries": {"attempts": 2, "backoff_s": 0},
        }
    )


def run_for(page, base_url):
    return run_extraction(
        cfg=config_for(base_url),
        grant=GRANT,
        adapter=get_adapter("demo_bank"),
        session=PageSession(page),
        run_id="run_test",
        now=NOW,
    )


def test_multiple_products_and_pages(authenticated_page, demo_server):
    outcome = run_for(authenticated_page, demo_server)

    assert outcome.report.status is RunStatus.OK
    assert outcome.report.products.total == 5
    assert outcome.report.transactions.total == 64
    assert outcome.report.transactions.by_product["card_001"] == 34
    assert set(outcome.report.channels_used.values()) == {Channel.API}


@pytest.mark.scenario("empty_history")
def test_empty_history_is_reported_not_failed(scenario_page, demo_server):
    outcome = run_for(scenario_page, demo_server)

    assert outcome.report.products.total == 5
    assert outcome.report.transactions.by_product.get("acc_002", 0) == 0
    assert outcome.report.products.failed == []
    assert any(w.code == "product_without_transactions" for w in outcome.report.validation)


@pytest.mark.scenario("api_down")
def test_dead_api_falls_back_to_export(scenario_page, demo_server):
    outcome = run_for(scenario_page, demo_server)

    assert outcome.report.transactions.total == 64
    assert set(outcome.report.channels_used.values()) == {Channel.EXPORT}


@pytest.mark.scenario("export_down")
def test_dead_api_and_export_fall_back_to_dom(scenario_page, demo_server):
    outcome = run_for(scenario_page, demo_server)

    assert set(outcome.report.channels_used.values()) == {Channel.DOM}
    assert outcome.report.transactions.by_product == {
        "acc_002": 12,
        "sav_003": 6,
        "dep_004": 4,
        "cred_005": 8,
    }


@pytest.mark.scenario("export_down")
def test_dom_refuses_to_truncate_when_load_more_is_dead(scenario_page, demo_server):
    outcome = run_for(scenario_page, demo_server)

    assert outcome.report.status is RunStatus.PARTIAL
    assert [f.product_id for f in outcome.report.products.failed] == ["card_001"]
    assert outcome.report.transactions.by_product.get("card_001", 0) == 0


@pytest.mark.scenario("slow_load")
def test_slow_channel_succeeds_on_retry(scenario_page, demo_server):
    outcome = run_for(scenario_page, demo_server)
    assert outcome.report.transactions.total == 64


@pytest.mark.scenario("partial_failure")
def test_one_dead_product_does_not_kill_the_run(scenario_page, demo_server):
    outcome = run_for(scenario_page, demo_server)

    assert outcome.report.status is RunStatus.PARTIAL
    assert [f.product_id for f in outcome.report.products.failed] == ["sav_003"]
    assert outcome.report.products.failed[0].channels_tried == [
        Channel.API,
        Channel.EXPORT,
        Channel.DOM,
    ]
    assert outcome.report.transactions.total == 58
    assert len(outcome.statement.products) == 5


@pytest.mark.scenario("broken_formats")
def test_broken_formats_are_normalized(scenario_page, demo_server):
    outcome = run_for(scenario_page, demo_server)

    assert outcome.report.transactions.by_product["card_001"] == 34
    card_txs = [tx for tx in outcome.statement.transactions if tx.product_id == "card_001"]
    assert all(tx.operation_date.year == 2026 for tx in card_txs)
    assert outcome.report.transactions.rejected == 0
