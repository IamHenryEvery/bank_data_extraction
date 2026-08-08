from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from bank_extractor.adapters.base import RawProduct, RawTransaction
from bank_extractor.enums import Channel, ProductStatus, ProductType
from bank_extractor.models import Product, Requisites, Transaction, make_transaction_id
from bank_extractor.normalization import NormalizationError
from bank_extractor.normalization.amounts import parse_amount
from bank_extractor.normalization.categories import normalize_category
from bank_extractor.normalization.currency import normalize_currency
from bank_extractor.normalization.dates import parse_date
from bank_extractor.normalization.dialects import RU, DateOrder, Dialect
from bank_extractor.normalization.statuses import normalize_status, normalize_type

_CANONICAL_PRODUCT_TYPES = {kind.value: kind for kind in ProductType}
_CANONICAL_PRODUCT_STATUSES = {status.value: status for status in ProductStatus}


class NormalizationWarning(BaseModel):
    code: str
    field: str
    raw_value: str | None = None
    product_id: str | None = None
    transaction_id: str | None = None


class Rejected(BaseModel):
    kind: str
    product_id: str
    reason: str
    raw_value: str | None = None
    description: str | None = None


class NormalizationResult(BaseModel):
    products: list[Product] = Field(default_factory=list)
    transactions: list[Transaction] = Field(default_factory=list)
    rejected: list[Rejected] = Field(default_factory=list)
    warnings: list[NormalizationWarning] = Field(default_factory=list)
    fields_total: int = 0
    fields_normalized: int = 0


class _Counter:
    def __init__(self) -> None:
        self.total = 0
        self.ok = 0

    def hit(self, success: bool) -> None:
        self.total += 1
        self.ok += int(success)


def normalize(
    raw_products: Sequence[tuple[RawProduct, Channel]],
    raw_transactions: Sequence[tuple[RawTransaction, Channel]],
    *,
    today: date,
    order: DateOrder,
    dialect: Dialect = RU,
) -> NormalizationResult:
    result = NormalizationResult()
    counter = _Counter()
    currencies: dict[str, str] = {}

    for raw_product, channel in raw_products:
        product = _build_product(raw_product, result, counter, dialect)
        if product is not None:
            result.products.append(product)
            product.extraction.channel = channel
            currencies[product.product_id] = product.currency

    for raw_transaction, channel in raw_transactions:
        transaction = _build_transaction(
            raw_transaction, channel, currencies, today, order, dialect, result, counter
        )
        if transaction is not None:
            result.transactions.append(transaction)

    result.fields_total = counter.total
    result.fields_normalized = counter.ok
    return result


def _warn(result: NormalizationResult, **fields: Any) -> None:
    result.warnings.append(NormalizationWarning(**fields))


def _build_product(
    raw: RawProduct, result: NormalizationResult, counter: _Counter, dialect: Dialect
) -> Product | None:
    try:
        currency = normalize_currency(raw.currency, dialect)
        counter.hit(True)
    except NormalizationError as exc:
        counter.hit(False)
        result.rejected.append(
            Rejected(
                kind="product",
                product_id=raw.product_id,
                reason=str(exc),
                raw_value=raw.currency,
                description=raw.name,
            )
        )
        return None

    raw_type = (raw.type or "").strip().lower()
    product_type = _CANONICAL_PRODUCT_TYPES.get(raw_type) or dialect.product_types.get(raw_type)
    if raw_type:
        counter.hit(product_type is not None)
    if product_type is None:
        if raw_type:
            _warn(
                result,
                code="unknown_product_type",
                field="type",
                raw_value=raw.type,
                product_id=raw.product_id,
            )
        product_type = ProductType.ACCOUNT

    raw_status = (raw.status or "").strip().lower()
    status = (
        _CANONICAL_PRODUCT_STATUSES.get(raw_status)
        or dialect.product_statuses.get(raw_status)
        or ProductStatus.UNKNOWN
    )
    if raw_status:
        counter.hit(status is not ProductStatus.UNKNOWN)

    balance = _money(raw.balance, "balance", raw.product_id, result, counter)
    available = _money(raw.available_balance, "available_balance", raw.product_id, result, counter)
    limit = _money(raw.credit_limit, "credit_limit", raw.product_id, result, counter)

    requisites = None
    if raw.requisites:
        try:
            requisites = Requisites.model_validate(raw.requisites)
            counter.hit(True)
        except ValidationError:
            counter.hit(False)
            _warn(
                result,
                code="invalid_requisites",
                field="requisites",
                raw_value=str(raw.requisites),
                product_id=raw.product_id,
            )

    try:
        return Product(
            product_id=raw.product_id,
            type=product_type,
            name=raw.name or raw.product_id,
            masked_number=raw.masked_number,
            currency=currency,
            balance=balance,
            available_balance=available,
            credit_limit=limit,
            requisites=requisites,
            status=status,
        )
    except ValidationError as exc:
        result.rejected.append(
            Rejected(
                kind="product",
                product_id=raw.product_id,
                reason=f"продукт не прошёл валидацию: {exc}",
                description=raw.name,
            )
        )
        return None


def _money(
    raw_value: str | None,
    field: str,
    product_id: str,
    result: NormalizationResult,
    counter: _Counter,
) -> Decimal | None:
    if raw_value is None:
        return None
    try:
        value = parse_amount(raw_value)
        counter.hit(True)
        return value
    except NormalizationError:
        counter.hit(False)
        _warn(
            result,
            code="unparsed_amount",
            field=field,
            raw_value=raw_value,
            product_id=product_id,
        )
        return None


def _build_transaction(
    raw: RawTransaction,
    channel: Channel,
    currencies: dict[str, str],
    today: date,
    order: DateOrder,
    dialect: Dialect,
    result: NormalizationResult,
    counter: _Counter,
) -> Transaction | None:
    try:
        operation_date = parse_date(raw.operation_date, today=today, order=order, dialect=dialect)
        counter.hit(True)
    except NormalizationError as exc:
        counter.hit(False)
        result.rejected.append(
            Rejected(
                kind="transaction",
                product_id=raw.product_id,
                reason=f"не удалось разобрать дату операции: {exc}",
                raw_value=raw.operation_date,
                description=raw.description,
            )
        )
        return None

    try:
        amount = parse_amount(raw.amount)
        counter.hit(True)
    except NormalizationError as exc:
        counter.hit(False)
        result.rejected.append(
            Rejected(
                kind="transaction",
                product_id=raw.product_id,
                reason=f"не удалось разобрать сумму: {exc}",
                raw_value=raw.amount,
                description=raw.description,
            )
        )
        return None

    posting_date = None
    if raw.posting_date:
        try:
            posting_date = parse_date(raw.posting_date, today=today, order=order, dialect=dialect)
            counter.hit(True)
        except NormalizationError:
            counter.hit(False)
            _warn(
                result,
                code="unparsed_posting_date",
                field="posting_date",
                raw_value=raw.posting_date,
                product_id=raw.product_id,
            )

    try:
        currency = normalize_currency(raw.currency, dialect)
        counter.hit(True)
    except NormalizationError:
        counter.hit(False)
        currency = currencies.get(raw.product_id, "RUB")
        _warn(
            result,
            code="unknown_currency",
            field="currency",
            raw_value=raw.currency,
            product_id=raw.product_id,
        )

    status, status_known = normalize_status(raw.status, dialect)
    if raw.status and raw.status.strip():
        counter.hit(status_known)
        if not status_known:
            _warn(
                result,
                code="unknown_status",
                field="status",
                raw_value=raw.status,
                product_id=raw.product_id,
            )

    kind, type_known = normalize_type(raw.type, raw.description or "", dialect)
    if raw.type and raw.type.strip():
        counter.hit(type_known)
        if not type_known:
            _warn(
                result,
                code="unknown_type",
                field="type",
                raw_value=raw.type,
                product_id=raw.product_id,
            )
    elif type_known:
        counter.hit(True)

    category, category_known = normalize_category(raw.category, dialect)
    counter.hit(category_known)
    if not category_known:
        _warn(
            result,
            code="unknown_category",
            field="category",
            raw_value=raw.category,
            product_id=raw.product_id,
        )

    transaction_id = raw.external_id or make_transaction_id(
        raw.product_id, operation_date, amount, raw.description or ""
    )

    return Transaction(
        transaction_id=transaction_id,
        product_id=raw.product_id,
        operation_date=operation_date,
        posting_date=posting_date,
        amount=amount,
        currency=currency,
        type=kind,
        description=raw.description or "",
        counterparty=raw.counterparty,
        category=category,
        status=status,
        mcc=raw.mcc,
        source_channel=channel,
    )
