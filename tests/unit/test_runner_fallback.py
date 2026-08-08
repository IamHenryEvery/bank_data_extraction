from datetime import UTC, date, datetime

import pytest

from bank_extractor.adapters.base import RawProduct, RawTransaction
from bank_extractor.config import AppConfig
from bank_extractor.consent import ConsentGrant
from bank_extractor.enums import Channel
from bank_extractor.errors import ChannelFailed, ChannelUnavailable
from bank_extractor.extraction.runner import run_extraction
from bank_extractor.normalization.dialects import RU
from bank_extractor.report import RunStatus

NOW = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)

CONFIG = AppConfig.model_validate(
    {
        "bank": "fake_bank",
        "base_url": "http://localhost:1",
        "period": {"from": "2026-01-01", "to": "2026-06-17"},
        "consent_file": "./consent.json",
        "retries": {"attempts": 1, "backoff_s": 0},
    }
)

GRANT = ConsentGrant.model_validate(
    {
        "consent_id": "cns_test",
        "client_ref": "client_x",
        "bank": "fake_bank",
        "scopes": ["products", "balances", "transactions", "requisites"],
        "period": {"from": "2026-01-01", "to": "2026-06-17"},
        "granted_at": "2026-08-06T09:00:00Z",
        "expires_at": "2036-01-01T00:00:00Z",
        "method": "explicit_ui_confirmation",
    }
)


class FakeSession:
    mode_resolved = "launch"

    def page(self):
        return object()


class FakeAdapter:
    name = "fake_bank"
    date_order = "dmy"
    dialect = RU
    product_channels = (Channel.API, Channel.DOM)
    transaction_channels = (Channel.API, Channel.EXPORT, Channel.DOM)

    def __init__(self, tx_behaviour: dict, product_behaviour: dict | None = None):
        self.tx_behaviour = tx_behaviour
        self.product_behaviour = product_behaviour or {}
        self.calls: list[tuple[str, str, Channel]] = []
        self.last_product_warnings: list[str] = []

    def login_url(self, base_url):
        return f"{base_url}/login"

    def dashboard_url(self, base_url):
        return f"{base_url}/accounts"

    def is_authenticated(self, page):
        return True

    def fetch_products(self, page, base_url, channel, *, with_balances, with_requisites):
        self.calls.append(("products", "-", channel))
        if (behaviour := self.product_behaviour.get(channel)) is not None:
            raise behaviour
        return [
            RawProduct(
                product_id="p1",
                type="card",
                name="Карта",
                currency="RUB",
                masked_number="**** 1111",
                balance="100.00" if with_balances else None,
            ),
            RawProduct(
                product_id="p2",
                type="account",
                name="Счёт",
                currency="RUB",
                masked_number="**** 2222",
                balance="200.00" if with_balances else None,
            ),
        ]

    def fetch_transactions(self, page, base_url, product, period, channel):
        self.calls.append(("transactions", product.product_id, channel))
        behaviour = self.tx_behaviour.get((product.product_id, channel))
        if isinstance(behaviour, Exception):
            raise behaviour
        return [
            RawTransaction(
                product_id=product.product_id,
                operation_date="2026-06-10",
                amount="-100.00",
                currency="RUB",
                description="Оплата",
                status="posted",
                external_id=f"{product.product_id}_tx1",
            )
        ]


def run(adapter, grant=GRANT):
    return run_extraction(
        cfg=CONFIG,
        grant=grant,
        adapter=adapter,
        session=FakeSession(),
        run_id="run_test",
        now=NOW,
    )


def test_first_channel_wins_and_others_are_not_tried():
    adapter = FakeAdapter({})
    outcome = run(adapter)

    assert outcome.report.status is RunStatus.OK
    assert outcome.report.channels_used == {"p1": Channel.API, "p2": Channel.API}
    assert Channel.EXPORT not in [call[2] for call in adapter.calls]


def test_falls_back_to_export_when_api_fails():
    adapter = FakeAdapter({("p1", Channel.API): ChannelFailed("API ответил 503")})
    outcome = run(adapter)

    assert outcome.report.channels_used["p1"] is Channel.EXPORT
    assert outcome.report.channels_used["p2"] is Channel.API
    assert outcome.report.status is RunStatus.OK


def test_falls_back_to_dom_when_api_and_export_fail():
    adapter = FakeAdapter(
        {
            ("p1", Channel.API): ChannelFailed("503"),
            ("p1", Channel.EXPORT): ChannelFailed("500"),
        }
    )
    assert run(adapter).report.channels_used["p1"] is Channel.DOM


def test_unavailable_channel_is_skipped_without_error():
    adapter = FakeAdapter({("p1", Channel.API): ChannelUnavailable("нет API")})
    outcome = run(adapter)
    assert outcome.report.channels_used["p1"] is Channel.EXPORT
    assert outcome.report.errors == []


def test_exhausted_chain_marks_product_failed_but_keeps_the_rest():
    adapter = FakeAdapter(
        {
            ("p1", Channel.API): ChannelFailed("503"),
            ("p1", Channel.EXPORT): ChannelFailed("500"),
            ("p1", Channel.DOM): ChannelFailed("нет строк"),
        }
    )
    outcome = run(adapter)

    assert outcome.report.status is RunStatus.PARTIAL
    assert [failure.product_id for failure in outcome.report.products.failed] == ["p1"]
    assert outcome.report.products.failed[0].channels_tried == [
        Channel.API,
        Channel.EXPORT,
        Channel.DOM,
    ]
    assert outcome.report.transactions.by_product == {"p2": 1}
    assert len(outcome.statement.products) == 2


def test_product_discovery_falls_back_to_dom():
    adapter = FakeAdapter({}, {Channel.API: ChannelFailed("503")})
    outcome = run(adapter)
    assert outcome.report.status is RunStatus.OK
    assert ("products", "-", Channel.DOM) in adapter.calls


def test_total_product_discovery_failure_is_fatal():
    adapter = FakeAdapter(
        {}, {Channel.API: ChannelFailed("503"), Channel.DOM: ChannelFailed("пусто")}
    )
    with pytest.raises(ChannelFailed):
        run(adapter)


def test_scope_without_transactions_skips_them_entirely():
    grant = GRANT.model_copy(update={"scopes": ["products", "balances"]})
    adapter = FakeAdapter({})
    outcome = run(adapter, grant=grant)

    assert outcome.statement.transactions == []
    assert not [call for call in adapter.calls if call[0] == "transactions"]
    assert any("transactions" in note for note in outcome.report.scope_restrictions)


def test_scope_without_balances_leaves_balances_empty():
    grant = GRANT.model_copy(update={"scopes": ["products", "transactions"]})
    outcome = run(FakeAdapter({}), grant=grant)
    assert all(product.balance is None for product in outcome.statement.products)


def test_expired_session_stops_early_with_partial_result():
    adapter = FakeAdapter(
        {
            ("p2", Channel.API): ChannelFailed("API ответил 401 на /api/..."),
            ("p2", Channel.EXPORT): ChannelFailed("401"),
            ("p2", Channel.DOM): ChannelFailed("401"),
        }
    )
    outcome = run(adapter)

    assert outcome.report.status is RunStatus.PARTIAL
    assert any(error.code == "session_expired" for error in outcome.report.errors)


def test_report_counts_and_period_are_filled():
    outcome = run(FakeAdapter({}))
    report = outcome.report

    assert report.run_id == "run_test"
    assert report.products.total == 2
    assert report.products.by_type == {"card": 1, "account": 1}
    assert report.transactions.total == 2
    assert report.period.from_ == date(2026, 1, 1)
    assert report.session.mode_resolved == "launch"
    assert report.consent.consent_id == "cns_test"
    assert report.duration_s >= 0
