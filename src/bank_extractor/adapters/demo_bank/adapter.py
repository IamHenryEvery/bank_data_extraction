import tempfile
from pathlib import Path

from playwright.sync_api import Page

from bank_extractor.adapters.base import RawProduct, RawTransaction
from bank_extractor.adapters.demo_bank import api, dom, export
from bank_extractor.adapters.demo_bank import selectors as sel
from bank_extractor.enums import Channel
from bank_extractor.errors import ChannelUnavailable
from bank_extractor.models import Period


class DemoBankAdapter:
    name = "demo_bank"
    product_channels: tuple[Channel, ...] = (Channel.API, Channel.DOM)
    transaction_channels: tuple[Channel, ...] = (Channel.API, Channel.EXPORT, Channel.DOM)

    def __init__(self) -> None:
        self.last_product_warnings: list[str] = []

    def login_url(self, base_url: str) -> str:
        return f"{base_url}{sel.PATH_LOGIN}"

    def dashboard_url(self, base_url: str) -> str:
        return f"{base_url}{sel.PATH_DASHBOARD}"

    def is_authenticated(self, page: Page) -> bool:
        return page.locator(sel.DASHBOARD_TITLE).count() > 0

    def fetch_products(
        self,
        page: Page,
        base_url: str,
        channel: Channel,
        *,
        with_balances: bool,
        with_requisites: bool,
    ) -> list[RawProduct]:
        if channel is Channel.API:
            return api.fetch_products(
                page, base_url, with_balances=with_balances, with_requisites=with_requisites
            )
        if channel is Channel.DOM:
            products, warnings = dom.fetch_products(
                page, base_url, with_balances=with_balances, with_requisites=with_requisites
            )
            self.last_product_warnings = warnings
            return products
        raise ChannelUnavailable(f"продукты через канал {channel} не отдаются")

    def fetch_transactions(
        self,
        page: Page,
        base_url: str,
        product: RawProduct,
        period: Period,
        channel: Channel,
    ) -> list[RawTransaction]:
        if channel is Channel.API:
            return api.fetch_transactions(page, base_url, product.product_id, period)
        if channel is Channel.EXPORT:
            with tempfile.TemporaryDirectory(prefix="bank-export-") as tmp:
                return export.fetch_transactions(
                    page, base_url, product.product_id, period, download_dir=Path(tmp)
                )
        if channel is Channel.DOM:
            return dom.fetch_transactions(page, base_url, product.product_id, period)
        raise ChannelUnavailable(f"неизвестный канал {channel}")
