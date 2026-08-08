from datetime import date
from decimal import Decimal

from bank_extractor.adapters.base import RawProduct, RawTransaction
from bank_extractor.enums import Channel, ProductType, TransactionStatus
from bank_extractor.normalization.normalizer import normalize

TODAY = date(2026, 6, 17)


def raw_product(**overrides) -> RawProduct:
    defaults = dict(
        product_id="card_001",
        type="card",
        name="Дебетовая карта",
        currency="RUB",
        masked_number="**** 1234",
        balance="125000.50",
    )
    return RawProduct(**{**defaults, **overrides})


def raw_tx(**overrides) -> RawTransaction:
    defaults = dict(
        product_id="card_001",
        operation_date="10.06.2026",
        amount="-1 450,50",
        currency="₽",
        description="Оплата покупки",
        status="Проведена",
        counterparty="STORE",
        category="shopping",
    )
    return RawTransaction(**{**defaults, **overrides})


def run(products, transactions):
    return normalize(products, transactions, today=TODAY, order="dmy")


def test_builds_product_and_transaction():
    result = run([(raw_product(), Channel.API)], [(raw_tx(), Channel.API)])

    assert len(result.products) == 1
    product = result.products[0]
    assert product.type is ProductType.CARD
    assert product.balance == Decimal("125000.50")

    assert len(result.transactions) == 1
    tx = result.transactions[0]
    assert tx.operation_date == date(2026, 6, 10)
    assert tx.amount == Decimal("-1450.50")
    assert tx.currency == "RUB"
    assert tx.status is TransactionStatus.POSTED
    assert tx.source_channel is Channel.API


def test_generates_stable_id_when_bank_gives_none():
    first = run([(raw_product(), Channel.EXPORT)], [(raw_tx(), Channel.EXPORT)])
    second = run([(raw_product(), Channel.EXPORT)], [(raw_tx(), Channel.EXPORT)])
    assert first.transactions[0].transaction_id == second.transactions[0].transaction_id
    assert first.transactions[0].transaction_id.startswith("tx_")


def test_keeps_external_id_when_bank_gives_one():
    result = run(
        [(raw_product(), Channel.API)], [(raw_tx(external_id="card_001_tx_007"), Channel.API)]
    )
    assert result.transactions[0].transaction_id == "card_001_tx_007"


def test_transaction_without_parseable_date_is_rejected_not_dropped_silently():
    result = run(
        [(raw_product(), Channel.DOM)], [(raw_tx(operation_date="кракозябра"), Channel.DOM)]
    )
    assert result.transactions == []
    assert len(result.rejected) == 1
    assert result.rejected[0].reason.startswith("не удалось разобрать дату")
    assert result.rejected[0].raw_value == "кракозябра"


def test_unparseable_posting_date_leaves_null_and_warns():
    result = run([(raw_product(), Channel.DOM)], [(raw_tx(posting_date="никогда"), Channel.DOM)])
    assert result.transactions[0].posting_date is None
    assert any(w.code == "unparsed_posting_date" for w in result.warnings)


def test_unknown_currency_falls_back_to_product_currency_with_warning():
    result = run([(raw_product(), Channel.DOM)], [(raw_tx(currency="¤"), Channel.DOM)])
    assert result.transactions[0].currency == "RUB"
    assert any(w.code == "unknown_currency" for w in result.warnings)


def test_product_without_currency_is_rejected():
    result = run([(raw_product(currency="¤"), Channel.API)], [])
    assert result.products == []
    assert result.rejected[0].kind == "product"


def test_unknown_status_produces_warning_but_keeps_transaction():
    result = run([(raw_product(), Channel.API)], [(raw_tx(status="Новый статус"), Channel.API)])
    assert len(result.transactions) == 1
    assert any(w.code == "unknown_status" for w in result.warnings)


def test_relative_dates_use_today():
    result = run([(raw_product(), Channel.DOM)], [(raw_tx(operation_date="Вчера"), Channel.DOM)])
    assert result.transactions[0].operation_date == date(2026, 6, 16)


def test_russian_product_type_is_recognised():
    result = run([(raw_product(type="Вклад"), Channel.API)], [])
    assert result.products[0].type is ProductType.DEPOSIT


def test_counts_normalized_fields_for_the_report():
    result = run([(raw_product(), Channel.API)], [(raw_tx(), Channel.API)])
    assert result.fields_total > 0
    assert result.fields_normalized == result.fields_total


def test_dirty_data_lowers_normalized_field_count():
    result = run(
        [(raw_product(), Channel.DOM)],
        [(raw_tx(currency="¤", status="Новый статус"), Channel.DOM)],
    )
    assert result.fields_normalized < result.fields_total
