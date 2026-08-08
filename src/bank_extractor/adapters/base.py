from dataclasses import dataclass
from typing import Protocol

from playwright.sync_api import Page

from bank_extractor.enums import Channel
from bank_extractor.models import Period
from bank_extractor.normalization.dialects import DateOrder, Dialect


@dataclass(slots=True)
class RawProduct:
    product_id: str
    type: str
    name: str
    currency: str
    masked_number: str | None = None
    balance: str | None = None
    available_balance: str | None = None
    credit_limit: str | None = None
    requisites: dict[str, str] | None = None
    status: str | None = None


@dataclass(slots=True)
class RawTransaction:
    product_id: str
    operation_date: str
    amount: str
    currency: str
    description: str
    external_id: str | None = None
    posting_date: str | None = None
    type: str | None = None
    counterparty: str | None = None
    category: str | None = None
    status: str | None = None
    mcc: str | None = None


@dataclass(slots=True)
class ChannelResult:
    channel: Channel
    succeeded: bool
    items: int = 0
    error: str | None = None


class BankAdapter(Protocol):
    name: str
    date_order: DateOrder
    dialect: Dialect
    product_channels: tuple[Channel, ...]
    transaction_channels: tuple[Channel, ...]

    def login_url(self, base_url: str) -> str: ...

    def dashboard_url(self, base_url: str) -> str: ...

    def is_authenticated(self, page: Page) -> bool: ...

    def fetch_products(
        self,
        page: Page,
        base_url: str,
        channel: Channel,
        *,
        with_balances: bool,
        with_requisites: bool,
    ) -> list[RawProduct]: ...

    def fetch_transactions(
        self,
        page: Page,
        base_url: str,
        product: RawProduct,
        period: Period,
        channel: Channel,
    ) -> list[RawTransaction]: ...
