from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from bank_extractor.errors import ExportError
from bank_extractor.models import Transaction

_CENTS = Decimal("0.01")

SCHEMA = pa.schema(
    [
        ("transaction_id", pa.string()),
        ("product_id", pa.string()),
        ("operation_date", pa.date32()),
        ("posting_date", pa.date32()),
        ("amount", pa.decimal128(18, 2)),
        ("currency", pa.string()),
        ("type", pa.string()),
        ("description", pa.string()),
        ("counterparty", pa.string()),
        ("category", pa.string()),
        ("status", pa.string()),
        ("mcc", pa.string()),
        ("source_channel", pa.string()),
    ]
)


def write_transactions(transactions: Sequence[Transaction], path: Path) -> Path:
    columns: dict[str, list[Any]] = {
        "transaction_id": [tx.transaction_id for tx in transactions],
        "product_id": [tx.product_id for tx in transactions],
        "operation_date": [tx.operation_date for tx in transactions],
        "posting_date": [tx.posting_date for tx in transactions],
        "amount": [tx.amount.quantize(_CENTS) for tx in transactions],
        "currency": [tx.currency for tx in transactions],
        "type": [str(tx.type) for tx in transactions],
        "description": [tx.description for tx in transactions],
        "counterparty": [tx.counterparty for tx in transactions],
        "category": [tx.category for tx in transactions],
        "status": [str(tx.status) for tx in transactions],
        "mcc": [tx.mcc for tx in transactions],
        "source_channel": [str(tx.source_channel) for tx in transactions],
    }

    try:
        pq.write_table(pa.table(columns, schema=SCHEMA), path)
    except (OSError, pa.ArrowInvalid) as exc:
        raise ExportError(f"не удалось записать {path}: {exc}") from exc
    return path
