import time
from dataclasses import dataclass
from datetime import datetime

from loguru import logger
from playwright.sync_api import Page

from bank_extractor.adapters.base import BankAdapter, RawProduct, RawTransaction
from bank_extractor.browser.resilience import with_retries
from bank_extractor.browser.session import BrowserSession
from bank_extractor.config import AppConfig
from bank_extractor.consent import ConsentGrant, allowed, to_summary
from bank_extractor.enums import Channel, ExtractionStatus, Scope
from bank_extractor.errors import ChannelFailed, ChannelUnavailable
from bank_extractor.models import Statement
from bank_extractor.normalization.normalizer import NormalizationResult, normalize
from bank_extractor.report import (
    ErrorEntry,
    ExtractionReport,
    NormalizationReport,
    ProductFailure,
    ProductsReport,
    RunStatus,
    SessionInfo,
    TransactionsReport,
    summarise_warnings,
)
from bank_extractor.validation.checks import run_checks

_SESSION_MARKERS = ("401", "403", "не авторизован", "сессия истекла")


@dataclass(slots=True)
class ExtractionOutcome:
    statement: Statement
    report: ExtractionReport


def run_extraction(
    *,
    cfg: AppConfig,
    grant: ConsentGrant,
    adapter: BankAdapter,
    session: BrowserSession,
    run_id: str,
    now: datetime,
) -> ExtractionOutcome:
    started = time.monotonic()
    page = session.page()

    with_balances = allowed(grant, Scope.BALANCES)
    with_requisites = allowed(grant, Scope.REQUISITES)
    with_transactions = allowed(grant, Scope.TRANSACTIONS)

    restrictions = [
        f"скоуп {scope} отсутствует в согласии — данные не извлекались"
        for scope, granted in (
            (Scope.BALANCES, with_balances),
            (Scope.REQUISITES, with_requisites),
            (Scope.TRANSACTIONS, with_transactions),
        )
        if not granted
    ]

    errors: list[ErrorEntry] = []
    raw_products = _discover_products(
        cfg, adapter, page, with_balances=with_balances, with_requisites=with_requisites
    )

    raw_transactions: list[tuple[RawTransaction, Channel]] = []
    channels_used: dict[str, Channel] = {}
    failures: list[ProductFailure] = []
    session_lost = False

    if with_transactions:
        for raw_product, _ in raw_products:
            if session_lost:
                failures.append(
                    ProductFailure(
                        product_id=raw_product.product_id,
                        channels_tried=[],
                        reason="прогон остановлен: сессия перестала быть авторизованной",
                    )
                )
                continue

            rows, channel, failure = _fetch_with_fallback(cfg, adapter, page, raw_product)

            if failure is not None:
                failures.append(failure)
                errors.append(
                    ErrorEntry(
                        code="channel_failed",
                        message=failure.reason,
                        product_id=raw_product.product_id,
                    )
                )
                if _looks_like_lost_session(failure.reason):
                    session_lost = True
                    errors.append(
                        ErrorEntry(
                            code="session_expired",
                            message="сессия перестала быть авторизованной, прогон остановлен",
                        )
                    )
                continue

            if channel is not None:
                channels_used[raw_product.product_id] = channel
                raw_transactions.extend((row, channel) for row in rows)

    normalized = normalize(
        raw_products,
        raw_transactions,
        today=now.date(),
        order=adapter.date_order,
        dialect=adapter.dialect,
    )
    validation = run_checks(normalized.products, normalized.transactions, cfg.period)

    for product in normalized.products:
        failure = next((f for f in failures if f.product_id == product.product_id), None)
        channel = channels_used.get(product.product_id)
        product.extraction.channel = channel
        product.extraction.channels_tried = (
            failure.channels_tried if failure else ([channel] if channel else [])
        )
        product.extraction.status = ExtractionStatus.FAILED if failure else ExtractionStatus.OK
        if failure:
            product.extraction.warnings.append(failure.reason)

    statement = Statement(
        bank=cfg.bank,
        extracted_at=now,
        period=cfg.period,
        consent=to_summary(grant),
        products=normalized.products,
        transactions=normalized.transactions,
    )

    by_product: dict[str, int] = {}
    for tx in normalized.transactions:
        by_product[tx.product_id] = by_product.get(tx.product_id, 0) + 1

    by_type: dict[str, int] = {}
    for product in normalized.products:
        by_type[product.type] = by_type.get(product.type, 0) + 1

    finished = time.monotonic()

    report = ExtractionReport(
        run_id=run_id,
        bank=cfg.bank,
        status=_decide_status(normalized, failures, errors),
        period=cfg.period,
        session=SessionInfo(mode_requested=cfg.session.mode, mode_resolved=session.mode_resolved),
        consent=to_summary(grant),
        started_at=now,
        finished_at=now,
        duration_s=round(finished - started, 3),
        products=ProductsReport(total=len(normalized.products), by_type=by_type, failed=failures),
        transactions=TransactionsReport(
            total=len(normalized.transactions),
            by_product=by_product,
            rejected=len([r for r in normalized.rejected if r.kind == "transaction"]),
        ),
        channels_used=channels_used,
        normalization=NormalizationReport(
            fields_total=normalized.fields_total,
            fields_normalized=normalized.fields_normalized,
            warnings=summarise_warnings(normalized.warnings),
        ),
        validation=validation,
        rejected=normalized.rejected,
        errors=errors,
        scope_restrictions=restrictions,
    )

    logger.bind(stage="done", run_id=run_id).info(
        "извлечение завершено: {} продуктов, {} операций, статус {}",
        report.products.total,
        report.transactions.total,
        report.status,
    )
    return ExtractionOutcome(statement=statement, report=report)


def _discover_products(
    cfg: AppConfig,
    adapter: BankAdapter,
    page: Page,
    *,
    with_balances: bool,
    with_requisites: bool,
) -> list[tuple[RawProduct, Channel]]:
    last_error: Exception | None = None

    for channel in adapter.product_channels:
        try:
            products = with_retries(
                lambda ch=channel: adapter.fetch_products( 
                    page,
                    cfg.base_url,
                    ch,
                    with_balances=with_balances,
                    with_requisites=with_requisites,
                ),
                attempts=cfg.retries.attempts,
                backoff_s=cfg.retries.backoff_s,
                retry_on=(ChannelFailed,),
                description=f"продукты через канал {channel}",
            )
            logger.bind(stage="products", channel=channel).info(
                "продукты получены каналом {}: {} шт.", channel, len(products)
            )
            return [(product, channel) for product in products]
        except ChannelUnavailable as exc:
            last_error = exc
            logger.bind(channel=channel).debug("канал недоступен для продуктов")
        except ChannelFailed as exc:
            last_error = exc
            logger.bind(channel=channel).warning("канал не отдал продукты")

    raise ChannelFailed(f"ни один канал не отдал список продуктов: {last_error}") from last_error


def _fetch_with_fallback(
    cfg: AppConfig, adapter: BankAdapter, page: Page, raw_product: RawProduct
) -> tuple[list[RawTransaction], Channel | None, ProductFailure | None]:
    tried: list[Channel] = []
    last_reason = "каналы не пробовались"

    for channel in adapter.transaction_channels:
        tried.append(channel)
        try:
            rows = with_retries(
                lambda ch=channel: adapter.fetch_transactions( 
                    page, cfg.base_url, raw_product, cfg.period, ch
                ),
                attempts=cfg.retries.attempts,
                backoff_s=cfg.retries.backoff_s,
                retry_on=(ChannelFailed,),
                description=f"операции {raw_product.product_id} через канал {channel}",
            )
            logger.bind(
                stage="transactions", product_id=raw_product.product_id, channel=channel
            ).info("операции получены каналом {}: {} шт.", channel, len(rows))
            return rows, channel, None
        except ChannelUnavailable as exc:
            tried.pop()
            last_reason = str(exc)
        except ChannelFailed as exc:
            last_reason = str(exc)
            logger.bind(product_id=raw_product.product_id, channel=channel).warning(
                "канал не отдал операции"
            )

    return (
        [],
        None,
        ProductFailure(
            product_id=raw_product.product_id,
            channels_tried=tried,
            reason=f"все каналы исчерпаны: {last_reason}",
        ),
    )


def _looks_like_lost_session(reason: str) -> bool:
    lowered = reason.lower()
    return any(marker in lowered for marker in _SESSION_MARKERS)


def _decide_status(
    normalized: NormalizationResult,
    failures: list[ProductFailure],
    errors: list[ErrorEntry],
) -> RunStatus:
    if not normalized.products:
        return RunStatus.FAILED
    if failures or normalized.rejected or errors:
        return RunStatus.PARTIAL
    return RunStatus.OK
