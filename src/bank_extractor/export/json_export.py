from pathlib import Path

from pydantic import BaseModel

from bank_extractor.errors import ExportError
from bank_extractor.models import Statement
from bank_extractor.report import ExtractionReport


def _dump(model: BaseModel, path: Path) -> Path:
    try:
        path.write_text(
            model.model_dump_json(by_alias=True, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        raise ExportError(f"не удалось записать {path}: {exc}") from exc
    return path


def write_statement(statement: Statement, path: Path) -> Path:
    return _dump(statement, path)


def write_report(report: ExtractionReport, path: Path) -> Path:
    return _dump(report, path)
