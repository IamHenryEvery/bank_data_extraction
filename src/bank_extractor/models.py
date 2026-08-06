import hashlib
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    StringConstraints,
    model_validator,
)

from bank_extractor.enums import (
    Channel,
    ExtractionStatus,
    ProductStatus,
    ProductType,
    Scope,
    TransactionStatus,
    TransactionType,
)

_CENTS = Decimal("0.01")


def _money_to_str(value: Decimal) -> str:
    return str(value.quantize(_CENTS))


# Деньги сериализуются строкой: float теряет точность, а числовой литерал
# в JSON теряет незначащий ноль (-1450.5 вместо -1450.50).
Money = Annotated[
    Decimal,
    PlainSerializer(_money_to_str, return_type=str, when_used="json"),
]
Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
MaskedNumber = Annotated[str, StringConstraints(pattern=r"^\*{4} \d{4}$")]


class Period(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    from_: date = Field(alias="from")
    to: date

    @model_validator(mode="after")
    def check_order(self) -> Self:
        if self.from_ > self.to:
            raise ValueError("начало периода позже конца")
        return self

    def contains(self, other: "Period") -> bool:
        return self.from_ <= other.from_ and other.to <= self.to

    def covers(self, day: date) -> bool:
        return self.from_ <= day <= self.to


class Requisites(BaseModel):
    masked_account: MaskedNumber | None = None
    bic: str | None = None
    corr_account: MaskedNumber | None = None
    bank_name: str | None = None


class ProductExtractionMeta(BaseModel):
    status: ExtractionStatus = ExtractionStatus.OK
    channel: Channel | None = None
    channels_tried: list[Channel] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class Product(BaseModel):
    product_id: str
    type: ProductType
    name: str
    masked_number: MaskedNumber | None = None
    currency: Currency
    balance: Money | None = None
    available_balance: Money | None = None
    credit_limit: Money | None = None
    requisites: Requisites | None = None
    status: ProductStatus = ProductStatus.UNKNOWN
    extraction: ProductExtractionMeta = Field(default_factory=ProductExtractionMeta)


class Transaction(BaseModel):
    transaction_id: str
    product_id: str
    operation_date: date
    posting_date: date | None = None
    amount: Money
    currency: Currency
    type: TransactionType = TransactionType.OTHER
    description: str
    counterparty: str | None = None
    category: str | None = None
    status: TransactionStatus = TransactionStatus.POSTED
    mcc: str | None = None
    source_channel: Channel


class ConsentSummary(BaseModel):
    consent_id: str
    scopes: list[Scope]
    expires_at: datetime


class Statement(BaseModel):
    bank: str
    extracted_at: datetime
    period: Period
    consent: ConsentSummary | None = None
    products: list[Product] = Field(default_factory=list)
    transactions: list[Transaction] = Field(default_factory=list)


def make_transaction_id(
    product_id: str, operation_date: date, amount: Decimal, description: str
) -> str:
    raw = f"{product_id}|{operation_date.isoformat()}|{amount.quantize(_CENTS)}|{description}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"tx_{digest}"
