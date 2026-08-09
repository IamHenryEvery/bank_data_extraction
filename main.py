import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from bank_extractor.adapters.registry import get_adapter
from bank_extractor.browser.session import open_session
from bank_extractor.config import AppConfig, load_config
from bank_extractor.consent import ConsentGrant, load_consent, to_summary, verify_consent
from bank_extractor.errors import ConfigError, ConsentError, ExtractionError, SessionError
from bank_extractor.export import write_all, write_report
from bank_extractor.extraction.runner import ExtractionOutcome, run_extraction
from bank_extractor.logging_setup import setup_logging
from bank_extractor.report import ErrorEntry, ExtractionReport, RunStatus


def run(config_path: Path) -> None:
    try:
        cfg = load_config(config_path)
    except ConfigError as exc:
        print(f"конфигурация: {exc}", file=sys.stderr)
        return

    setup_logging(cfg.logging.level, cfg.logging.file)
    started = time.monotonic()
    now = datetime.now(UTC)
    run_id = f"run_{now:%Y-%m-%dT%H-%M-%SZ}"
    grant: ConsentGrant | None = None

    try:
        grant = load_consent(cfg.consent_file)
        verify_consent(grant, bank=cfg.bank, period=cfg.period, now=now)
    except ConsentError as exc:
        _fail(cfg, run_id, now, started, "consent_rejected", str(exc), grant)
        return

    try:
        adapter = get_adapter(cfg.bank)
    except KeyError as exc:
        _fail(cfg, run_id, now, started, "unknown_bank", str(exc), grant)
        return

    session = None
    try:
        session = open_session(
            cfg.session, start_url=adapter.login_url(cfg.base_url), timeouts=cfg.timeouts
        )
        if session.mode_resolved == "launch":
            print("Войдите в кабинет в открывшемся браузере — извлечение начнётся после входа.")
        session.wait_for_authentication(adapter.is_authenticated, cfg.session.auth_timeout_s)

        outcome = run_extraction(
            cfg=cfg, grant=grant, adapter=adapter, session=session, run_id=run_id, now=now
        )
        paths = write_all(outcome.statement, outcome.report, cfg.output)
    except (SessionError, ExtractionError) as exc:
        logger.bind(run_id=run_id).error("прогон прерван: {}", exc)
        _fail(cfg, run_id, now, started, "extraction_failed", str(exc), grant)
        return
    finally:
        if session is not None:
            session.close()

    _print_summary(outcome, paths)


def _fail(
    cfg: AppConfig,
    run_id: str,
    now: datetime,
    started: float,
    code: str,
    message: str,
    grant: ConsentGrant | None,
) -> None:
    report = ExtractionReport(
        run_id=run_id,
        bank=cfg.bank,
        status=RunStatus.FAILED,
        period=cfg.period,
        consent=to_summary(grant) if grant is not None else None,
        started_at=now,
        finished_at=datetime.now(UTC),
        duration_s=round(time.monotonic() - started, 3),
        errors=[ErrorEntry(code=code, message=message)],
    )
    print(f"{code}: {message}", file=sys.stderr)

    try:
        path = write_report(report, cfg.output.dir)
        print(f"отчёт о прогоне: {path}", file=sys.stderr)
    except ExtractionError as exc:
        print(f"отчёт записать не удалось: {exc}", file=sys.stderr)


def _print_summary(outcome: ExtractionOutcome, paths: list[Path]) -> None:
    report = outcome.report
    channels = ", ".join(f"{pid}: {channel}" for pid, channel in report.channels_used.items())
    print(f"Статус:    {report.status}")
    print(f"Период:    {report.period.from_} — {report.period.to}")
    print(f"Продукты:  {report.products.total}, с ошибкой {len(report.products.failed)}")
    print(f"Операции:  {report.transactions.total}, отбраковано {report.transactions.rejected}")
    print(f"Каналы:    {channels}")
    if report.validation:
        print(f"Предупреждения валидации: {len(report.validation)}")
    print("Файлы:")
    for path in paths:
        print(f"  {path}")


if __name__ == "__main__":
    run(Path(sys.argv[1] if len(sys.argv) > 1 else "config.yaml"))
