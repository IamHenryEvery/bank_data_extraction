from loguru import logger
from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from bank_extractor.adapters.base import RawProduct, RawTransaction
from bank_extractor.adapters.demo_bank import selectors as sel
from bank_extractor.errors import ChannelFailed
from bank_extractor.models import Period

RENDER_TIMEOUT_MS = 10_000


def _goto(page: Page, url: str) -> None:
    response = page.goto(url)
    if response is not None and response.status >= 400:
        raise ChannelFailed(f"страница ответила {response.status}: {url}")


def _text(scope: Locator, selector: str) -> str | None:
    node = scope.locator(selector)
    if node.count() == 0:
        return None
    value = node.first.inner_text().strip()
    return value or None


def fetch_products(
    page: Page,
    base_url: str,
    *,
    with_balances: bool,
    with_requisites: bool,
    balance_timeout_s: int = 10,
) -> tuple[list[RawProduct], list[str]]:
    warnings: list[str] = []
    _goto(page, f"{base_url}{sel.PATH_DASHBOARD}")

    try:
        page.wait_for_selector(sel.PRODUCT_ITEM, timeout=RENDER_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise ChannelFailed("на дашборде не отрисовался ни один продукт") from exc

    balances_ready = True
    if with_balances:
        try:
            page.wait_for_function(
                f"document.querySelectorAll('{sel.BALANCE_PENDING}').length === 0",
                timeout=balance_timeout_s * 1000,
            )
        except PlaywrightTimeoutError:
            balances_ready = False
            warnings.append("остатки не загрузились за отведённое время — продукты без балансов")
            logger.bind(channel="dom").warning("остатки не догрузились")

    read_balances = with_balances and balances_ready
    products: list[RawProduct] = []
    items = page.locator(sel.PRODUCT_ITEM)

    for index in range(items.count()):
        item = items.nth(index)
        products.append(
            RawProduct(
                product_id=item.get_attribute("data-product-id") or "",
                type=_text(item, sel.PRODUCT_TYPE) or "",
                name=_text(item, sel.PRODUCT_LINK) or "",
                currency=_text(item, sel.PRODUCT_CURRENCY) or "",
                masked_number=_text(item, sel.PRODUCT_NUMBER),
                balance=_text(item, sel.PRODUCT_BALANCE) if read_balances else None,
                available_balance=_text(item, sel.PRODUCT_AVAILABLE) if read_balances else None,
            )
        )

    if with_requisites:
        for product in products:
            try:
                product.requisites = _read_requisites(page, base_url, product.product_id)
            except ChannelFailed as exc:
                warnings.append(f"реквизиты {product.product_id} не прочитаны: {exc}")

    logger.bind(channel="dom").debug("канал dom отдал {} продуктов", len(products))
    return products, warnings


def _read_requisites(page: Page, base_url: str, product_id: str) -> dict[str, str] | None:
    _goto(page, f"{base_url}{sel.PATH_PRODUCT.format(product_id=product_id)}")
    body = page.locator("body")
    if body.locator(sel.REQUISITES).count() == 0:
        return None
    return {
        "masked_account": _text(body, sel.REQ_ACCOUNT) or "",
        "bic": _text(body, sel.REQ_BIC) or "",
        "corr_account": _text(body, sel.REQ_CORR) or "",
        "bank_name": _text(body, sel.REQ_BANK) or "",
    }


def _row_keys(page: Page) -> list[str]:
    keys: list[str] = page.eval_on_selector_all(
        sel.TX_ROW, "rows => rows.map(row => row.dataset.txId || row.innerText)"
    )
    return keys


def fetch_transactions(
    page: Page, base_url: str, product_id: str, period: Period
) -> list[RawTransaction]:
    url = (
        f"{base_url}{sel.PATH_PRODUCT.format(product_id=product_id)}"
        f"?date_from={period.from_.isoformat()}&date_to={period.to.isoformat()}"
    )
    _goto(page, url)

    if page.locator(sel.EMPTY_HISTORY).count() > 0:
        logger.bind(channel="dom", product_id=product_id).info("история пуста")
        return []

    _exhaust_pagination(page)

    rows: list[RawTransaction] = []
    seen: set[str] = set()
    locator = page.locator(sel.TX_ROW)
    keys = _row_keys(page)

    for index in range(locator.count()):
        if keys[index] in seen:
            continue
        seen.add(keys[index])
        row = locator.nth(index)
        rows.append(
            RawTransaction(
                external_id=row.get_attribute("data-tx-id"),
                product_id=product_id,
                operation_date=_text(row, sel.TX_OPERATION_DATE) or "",
                posting_date=_text(row, sel.TX_POSTING_DATE),
                amount=_text(row, sel.TX_AMOUNT) or "",
                currency=_text(row, sel.TX_CURRENCY) or "",
                description=_text(row, sel.TX_DESCRIPTION) or "",
                counterparty=_text(row, sel.TX_COUNTERPARTY),
                category=_text(row, sel.TX_CATEGORY),
                status=_text(row, sel.TX_STATUS),
            )
        )

    logger.bind(channel="dom").debug("канал dom отдал {} операций по {}", len(rows), product_id)
    return rows


def _exhaust_pagination(page: Page) -> None:
    seen = set(_row_keys(page))

    while page.locator(sel.LOAD_MORE).count() > 0:
        before = page.locator(sel.TX_ROW).count()
        page.locator(sel.LOAD_MORE).first.click()
        try:
            page.wait_for_function(
                f"document.querySelectorAll('{sel.TX_ROW}').length > {before}",
                timeout=RENDER_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError as exc:
            raise ChannelFailed("после нажатия «Показать ещё» новых строк не появилось") from exc

        fresh = set(_row_keys(page)) - seen
        if not fresh:
            raise ChannelFailed("подгрузка вернула только уже виденные операции")
        seen |= fresh
