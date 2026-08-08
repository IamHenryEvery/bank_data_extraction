import csv
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

from bank_extractor.errors import ExportError
from bank_extractor.models import Product, Transaction

ENCODING = "utf-8-sig"
_CENTS = Decimal("0.01")

PRODUCT_COLUMNS = (
    "product_id",
    "type",
    "name",
    "masked_number",
    "currency",
    "balance",
    "available_balance",
    "credit_limit",
    "status",
    "extraction_status",
    "extraction_channel",
)

TRANSACTION_COLUMNS = (
    "transaction_id",
    "product_id",
    "operation_date",
    "posting_date",
    "amount",
    "currency",
    "type",
    "description",
    "counterparty",
    "category",
    "status",
    "mcc",
    "source_channel",
)


def _write(path: Path, columns: Sequence[str], rows: list[dict[str, Any]]) -> Path:
    try:
        with path.open("w", encoding=ENCODING, newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(columns))
            writer.writeheader()
            writer.writerows(rows)
    except OSError as exc:
        raise ExportError(f"не удалось записать {path}: {exc}") from exc
    return path


def _money(value: Decimal | None) -> str:
    if value is None:
        return ""
    return str(value.quantize(_CENTS))


def write_products(products: Sequence[Product], path: Path) -> Path:
    rows: list[dict[str, Any]] = [
        {
            "product_id": product.product_id,
            "type": product.type,
            "name": product.name,
            "masked_number": product.masked_number or "",
            "currency": product.currency,
            "balance": _money(product.balance),
            "available_balance": _money(product.available_balance),
            "credit_limit": _money(product.credit_limit),
            "status": product.status,
            "extraction_status": product.extraction.status,
            "extraction_channel": product.extraction.channel or "",
        }
        for product in products
    ]
    return _write(path, PRODUCT_COLUMNS, rows)


def write_transactions(transactions: Sequence[Transaction], path: Path) -> Path:
    rows: list[dict[str, Any]] = [
        {
            "transaction_id": tx.transaction_id,
            "product_id": tx.product_id,
            "operation_date": tx.operation_date.isoformat(),
            "posting_date": tx.posting_date.isoformat() if tx.posting_date else "",
            "amount": _money(tx.amount),
            "currency": tx.currency,
            "type": tx.type,
            "description": tx.description,
            "counterparty": tx.counterparty or "",
            "category": tx.category or "",
            "status": tx.status,
            "mcc": tx.mcc or "",
            "source_channel": tx.source_channel,
        }
        for tx in transactions
    ]
    return _write(path, TRANSACTION_COLUMNS, rows)
