import csv
import io
from pathlib import Path

from loguru import logger
from playwright.sync_api import Page
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from bank_extractor.adapters.base import RawTransaction
from bank_extractor.adapters.demo_bank import selectors as sel
from bank_extractor.errors import ChannelFailed, ChannelUnavailable
from bank_extractor.models import Period

ENCODING = "cp1251"
DELIMITER = ";"

CSV_HEADER: tuple[str, ...] = (
    "Дата операции",
    "Дата обработки",
    "Сумма",
    "Валюта",
    "Описание",
    "Контрагент",
    "Категория",
    "Статус",
)


def parse_csv(data: bytes, product_id: str) -> list[RawTransaction]:
    text = data.decode(ENCODING, errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter=DELIMITER)

    try:
        header = tuple(next(reader))
    except StopIteration:
        raise ChannelFailed("выгрузка пуста: нет даже шапки") from None

    if header != CSV_HEADER:
        raise ChannelFailed(
            f"неожиданная кодировка или шапка выгрузки: получено {header}, ожидалось {CSV_HEADER}"
        )

    rows = []
    for line in reader:
        if not any(cell.strip() for cell in line):
            continue
        if len(line) != len(CSV_HEADER):
            raise ChannelFailed(f"в строке выгрузки {len(line)} колонок вместо {len(CSV_HEADER)}")

        operation, posting, amount, currency, description, counterparty, category, status = line
        rows.append(
            RawTransaction(
                product_id=product_id,
                operation_date=operation,
                posting_date=posting or None,
                amount=amount,
                currency=currency,
                description=description,
                counterparty=counterparty or None,
                category=category or None,
                status=status or None,
            )
        )

    logger.bind(channel="export").debug(
        "канал export отдал {} операций по {}", len(rows), product_id
    )
    return rows


def fetch_transactions(
    page: Page,
    base_url: str,
    product_id: str,
    period: Period,
    *,
    download_dir: Path,
    timeout_s: int = 30,
) -> list[RawTransaction]:
    url = (
        f"{base_url}{sel.PATH_PRODUCT.format(product_id=product_id)}"
        f"?date_from={period.from_.isoformat()}&date_to={period.to.isoformat()}"
    )
    response = page.goto(url)
    if response is not None and response.status >= 400:
        raise ChannelFailed(f"страница продукта ответила {response.status}: {url}")

    if page.locator(sel.EXPORT_CSV).count() == 0:
        raise ChannelUnavailable("в интерфейсе нет кнопки экспорта")

    download_dir.mkdir(parents=True, exist_ok=True)
    target = download_dir / f"{product_id}.csv"

    try:
        with page.expect_download(timeout=timeout_s * 1000) as download_info:
            with page.expect_response(
                lambda response: sel.PATH_EXPORT in response.url, timeout=timeout_s * 1000
            ) as response_info:
                page.locator(sel.EXPORT_CSV).click()

            status = response_info.value.status
            if status >= 400:
                raise ChannelFailed(f"экспорт ответил {status} вместо файла")

            download_info.value.save_as(target)
    except PlaywrightTimeoutError as exc:
        raise ChannelFailed("экспорт не отдал файл — вероятно, выгрузка недоступна") from exc

    try:
        return parse_csv(target.read_bytes(), product_id)
    finally:
        target.unlink(missing_ok=True)
