from typing import Any

from loguru import logger
from playwright.sync_api import Page

from bank_extractor.adapters.base import RawProduct, RawTransaction
from bank_extractor.adapters.demo_bank import selectors as sel
from bank_extractor.errors import ChannelFailed
from bank_extractor.models import Period

# Страховка от бесконечной пагинации при поломке курсора.
MAX_PAGES = 200


# Запросы идут через page.request, то есть через тот же браузерный контекст:
# используются уже выданные клиенту cookies, отдельная авторизация не нужна
# и никакие секреты не копируются.
def _get_json(
    page: Page, url: str, params: dict[str, str | float | bool] | None = None
) -> dict[str, Any]:
    response = page.request.get(url, params=params or {})
    if not response.ok:
        raise ChannelFailed(f"API ответил {response.status} на {url}")
    data: dict[str, Any] = response.json()
    return data


def fetch_products(
    page: Page, base_url: str, *, with_balances: bool, with_requisites: bool
) -> list[RawProduct]:
    payload = _get_json(page, f"{base_url}{sel.PATH_API_PRODUCTS}")
    products = []

    for item in payload.get("products", []):
        requisites = None
        if with_requisites and item.get("requisites"):
            requisites = {
                "masked_account": item["requisites"].get("account"),
                "bic": item["requisites"].get("bic"),
                "corr_account": item["requisites"].get("corr_account"),
                "bank_name": item["requisites"].get("bank_name"),
            }

        products.append(
            RawProduct(
                product_id=item["product_id"],
                type=item.get("type", ""),
                name=item.get("name", ""),
                currency=item.get("currency", ""),
                masked_number=item.get("masked_number"),
                balance=item.get("balance") if with_balances else None,
                available_balance=item.get("available_balance") if with_balances else None,
                credit_limit=item.get("credit_limit") if with_balances else None,
                requisites=requisites,
                status=item.get("status"),
            )
        )

    logger.bind(channel="api").debug("канал api отдал {} продуктов", len(products))
    return products


def fetch_transactions(
    page: Page, base_url: str, product_id: str, period: Period
) -> list[RawTransaction]:
    url = f"{base_url}{sel.PATH_API_TRANSACTIONS.format(product_id=product_id)}"
    rows: list[RawTransaction] = []
    cursor: int | None = 0

    for _ in range(MAX_PAGES):
        if cursor is None:
            break
        payload = _get_json(
            page,
            url,
            {
                "date_from": period.from_.isoformat(),
                "date_to": period.to.isoformat(),
                "cursor": str(cursor),
            },
        )
        for item in payload.get("items", []):
            rows.append(
                RawTransaction(
                    external_id=item.get("id"),
                    product_id=product_id,
                    operation_date=item["operation_date"],
                    posting_date=item.get("posting_date"),
                    amount=item["amount"],
                    currency=item.get("currency", ""),
                    type=item.get("type"),
                    description=item.get("description", ""),
                    counterparty=item.get("counterparty"),
                    category=item.get("category"),
                    status=item.get("status"),
                    mcc=item.get("mcc"),
                )
            )
        cursor = payload.get("next_cursor")
    else:
        raise ChannelFailed(f"пагинация не завершилась за {MAX_PAGES} страниц")

    logger.bind(channel="api").debug("канал api отдал {} операций по {}", len(rows), product_id)
    return rows
