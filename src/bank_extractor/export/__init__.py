import stat
from pathlib import Path

from loguru import logger

from bank_extractor.config import OutputConfig
from bank_extractor.errors import ExportError
from bank_extractor.export import csv_export, json_export, parquet_export
from bank_extractor.models import Statement
from bank_extractor.report import ExtractionReport


def prepare_dir(directory: Path) -> Path:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(stat.S_IRWXU)
    except OSError as exc:
        raise ExportError(f"не удалось подготовить каталог {directory}: {exc}") from exc
    return directory


def write_report(report: ExtractionReport, directory: Path) -> Path:
    return json_export.write_report(report, prepare_dir(directory) / "extraction_report.json")


def write_all(statement: Statement, report: ExtractionReport, cfg: OutputConfig) -> list[Path]:
    written = [write_report(report, cfg.dir)]

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
