import stat
from pathlib import Path

from loguru import logger

from bank_extractor.config import OutputConfig
from bank_extractor.errors import ExportError
from bank_extractor.export import csv_export, json_export, parquet_export
from bank_extractor.models import Statement
from bank_extractor.report import ExtractionReport


def write_all(statement: Statement, report: ExtractionReport, cfg: OutputConfig) -> list[Path]:
    try:
        cfg.dir.mkdir(parents=True, exist_ok=True)
        cfg.dir.chmod(stat.S_IRWXU)
    except OSError as exc:
        raise ExportError(f"не удалось подготовить каталог {cfg.dir}: {exc}") from exc

    written = [json_export.write_report(report, cfg.dir / "extraction_report.json")]

    if "json" in cfg.formats:
        written.append(json_export.write_statement(statement, cfg.dir / "statement.json"))

    if "csv" in cfg.formats:
        written.append(csv_export.write_products(statement.products, cfg.dir / "products.csv"))
        written.append(
            csv_export.write_transactions(statement.transactions, cfg.dir / "transactions.csv")
        )

    if "parquet" in cfg.formats:
        written.append(
            parquet_export.write_transactions(
                statement.transactions, cfg.dir / "transactions.parquet"
            )
        )

    logger.bind(stage="export").info("записано артефактов: {}", len(written))
    return written
