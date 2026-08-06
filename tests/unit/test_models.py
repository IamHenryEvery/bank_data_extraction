import json
from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from bank_extractor.enums import Channel, ProductType, TransactionStatus, TransactionType
from bank_extractor.models import Period, Product, Statement, Transaction, make_transaction_id


def test_period_uses_from_alias():
    period = Period.model_validate({"from": "2026-01-01", "to": "2026-06-17"})
    assert period.from_ == date(2026, 1, 1)
    assert json.loads(period.model_dump_json())["from"] == "2026-01-01"


def test_period_rejects_reversed_range():
    with pytest.raises(ValidationError):
        Period.model_validate({"from": "2026-06-17", "to": "2026-01-01"})


def test_period_contains():
    outer = Period.model_validate({"from": "2026-01-01", "to": "2026-12-31"})
    inner = Period.model_validate({"from": "2026-02-01", "to": "2026-03-01"})
    assert outer.contains(inner)
    assert not inner.contains(outer)


def test_product_rejects_unmasked_number():
    with pytest.raises(ValidationError):
        Product(
            product_id="card_001",
            type=ProductType.CARD,
            name="Дебетовая карта",
            masked_number="4276123456781234",
            currency="RUB",
        )


def test_product_accepts_masked_number():
    product = Product(
        product_id="card_001",
        type=ProductType.CARD,
        name="Дебетовая карта",
        masked_number="**** 1234",
        currency="RUB",
        balance=Decimal("125000.50"),
    )
    assert product.balance == Decimal("125000.50")


def test_amount_serializes_with_two_decimals_not_float():
    tx = Transaction(
        transaction_id="tx_001",
        product_id="card_001",
        operation_date=date(2026, 6, 10),
        amount=Decimal("-1450.5"),
        currency="RUB",
        type=TransactionType.PURCHASE,
        description="Оплата покупки",
        status=TransactionStatus.POSTED,
        source_channel=Channel.API,
    )
    payload = json.loads(tx.model_dump_json())
    assert payload["amount"] == "-1450.50"


def test_currency_must_be_iso_uppercase():
    with pytest.raises(ValidationError):
        Transaction(
            transaction_id="tx_002",
            product_id="card_001",
            operation_date=date(2026, 6, 10),
            amount=Decimal("1"),
            currency="руб",
            type=TransactionType.OTHER,
            description="x",
            status=TransactionStatus.POSTED,
            source_channel=Channel.API,
        )


def test_transaction_id_is_stable_across_runs():
    args = ("card_001", date(2026, 6, 10), Decimal("-1450.00"), "Оплата покупки")
    assert make_transaction_id(*args) == make_transaction_id(*args)
    assert make_transaction_id(*args) != make_transaction_id(
        "card_002", date(2026, 6, 10), Decimal("-1450.00"), "Оплата покупки"
    )


def test_statement_matches_tz_example_shape():
    payload = {
        "bank": "demo_bank",
        "extracted_at": "2026-06-17T12:00:00Z",
        "period": {"from": "2026-01-01", "to": "2026-06-17"},
        "products": [
            {
                "product_id": "card_001",
                "type": "card",
                "name": "Дебетовая карта",
                "masked_number": "**** 1234",
                "currency": "RUB",
                "balance": "125000.50",
            }
        ],
        "transactions": [
            {
                "transaction_id": "tx_001",
                "product_id": "card_001",
                "operation_date": "2026-06-10",
                "posting_date": "2026-06-11",
                "amount": "-1450.00",
                "currency": "RUB",
                "description": "Оплата покупки",
                "counterparty": "STORE NAME",
                "category": "shopping",
                "status": "posted",
                "type": "purchase",
                "source_channel": "api",
            }
        ],
    }
    statement = Statement.model_validate(payload)
    assert statement.products[0].balance == Decimal("125000.50")
    assert statement.transactions[0].amount == Decimal("-1450.00")
