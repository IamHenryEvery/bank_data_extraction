from datetime import date
from decimal import Decimal

from bank_extractor.enums import Channel, ProductType, TransactionStatus, TransactionType
from bank_extractor.models import Period, Product, Transaction
from bank_extractor.validation.checks import run_checks

PERIOD = Period.model_validate({"from": "2026-01-01", "to": "2026-06-17"})


def product(product_id="card_001", currency="RUB", balance="1000.00") -> Product:
    return Product(
        product_id=product_id,
        type=ProductType.CARD,
        name="Карта",
        currency=currency,
        balance=Decimal(balance),
        masked_number="**** 1234",
    )


def tx(
    transaction_id="tx_1",
    product_id="card_001",
    day=date(2026, 6, 10),
    amount="-100.00",
    currency="RUB",
) -> Transaction:
    return Transaction(
        transaction_id=transaction_id,
        product_id=product_id,
        operation_date=day,
        amount=Decimal(amount),
        currency=currency,
        type=TransactionType.PURCHASE,
        description="Оплата",
        status=TransactionStatus.POSTED,
        source_channel=Channel.API,
    )


def test_clean_data_produces_no_warnings():
    assert run_checks([product()], [tx()], PERIOD) == []


def test_detects_duplicate_transaction_ids():
    warnings = run_checks([product()], [tx(), tx()], PERIOD)
    assert any(w.code == "duplicate_transaction_id" for w in warnings)


def test_detects_orphan_transaction():
    warnings = run_checks([product()], [tx(product_id="ghost_999")], PERIOD)
    assert any(w.code == "orphan_transaction" for w in warnings)


def test_detects_date_outside_period():
    warnings = run_checks([product()], [tx(day=date(2025, 12, 31))], PERIOD)
    assert any(w.code == "date_outside_period" for w in warnings)


def test_detects_posting_before_operation():
    late = tx()
    late.posting_date = date(2026, 6, 9)
    warnings = run_checks([product()], [late], PERIOD)
    assert any(w.code == "posting_before_operation" for w in warnings)


def test_detects_currency_mismatch():
    warnings = run_checks([product(currency="RUB")], [tx(currency="USD")], PERIOD)
    assert any(w.code == "currency_mismatch" for w in warnings)


def test_detects_product_without_transactions():
    warnings = run_checks([product(), product(product_id="acc_002")], [tx()], PERIOD)
    assert any(
        w.code == "product_without_transactions" and w.product_id == "acc_002" for w in warnings
    )


def test_checks_never_raise_on_empty_input():
    assert run_checks([], [], PERIOD) == []
