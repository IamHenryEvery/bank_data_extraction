from collections import Counter
from collections.abc import Sequence

from pydantic import BaseModel

from bank_extractor.models import Period, Product, Transaction


class ValidationWarning(BaseModel):
    code: str
    message: str
    product_id: str | None = None
    transaction_id: str | None = None


def run_checks(
    products: Sequence[Product], transactions: Sequence[Transaction], period: Period
) -> list[ValidationWarning]:
    warnings: list[ValidationWarning] = []
    known = {product.product_id: product for product in products}

    duplicates = [
        tx_id
        for tx_id, count in Counter(tx.transaction_id for tx in transactions).items()
        if count > 1
    ]
    warnings.extend(
        ValidationWarning(
            code="duplicate_transaction_id",
            message=f"идентификатор операции встречается несколько раз: {tx_id}",
            transaction_id=tx_id,
        )
        for tx_id in duplicates
    )

    seen_products: set[str] = set()

    for tx in transactions:
        seen_products.add(tx.product_id)
        product = known.get(tx.product_id)

        if product is None:
            warnings.append(
                ValidationWarning(
                    code="orphan_transaction",
                    message=f"операция ссылается на неизвестный продукт {tx.product_id}",
                    product_id=tx.product_id,
                    transaction_id=tx.transaction_id,
                )
            )
            continue

        if tx.currency != product.currency:
            warnings.append(
                ValidationWarning(
                    code="currency_mismatch",
                    message=(
                        f"валюта операции {tx.currency} не совпадает с валютой "
                        f"продукта {product.currency}"
                    ),
                    product_id=tx.product_id,
                    transaction_id=tx.transaction_id,
                )
            )

        if not period.covers(tx.operation_date):
            warnings.append(
                ValidationWarning(
                    code="date_outside_period",
                    message=f"дата операции {tx.operation_date} вне запрошенного периода",
                    product_id=tx.product_id,
                    transaction_id=tx.transaction_id,
                )
            )

        if tx.posting_date is not None and tx.posting_date < tx.operation_date:
            warnings.append(
                ValidationWarning(
                    code="posting_before_operation",
                    message="дата обработки раньше даты операции",
                    product_id=tx.product_id,
                    transaction_id=tx.transaction_id,
                )
            )

    warnings.extend(
        ValidationWarning(
            code="product_without_transactions",
            message="за период не найдено ни одной операции по продукту",
            product_id=product_id,
        )
        for product_id in known
        if product_id not in seen_products and transactions
    )

    return warnings
