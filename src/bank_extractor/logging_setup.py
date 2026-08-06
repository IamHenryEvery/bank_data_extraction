import json
import sys
import traceback
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from bank_extractor.masking import redact_text

if TYPE_CHECKING:
    from loguru import Message, Record

CONTEXT_KEYS = ("stage", "product_id", "channel", "run_id")


def redact_record(record: "Record") -> bool:
    record["message"] = redact_text(record["message"])
    for key, value in record["extra"].items():
        if isinstance(value, str):
            record["extra"][key] = redact_text(value)
    return True


def json_sink(write: Callable[[str], Any]) -> "Callable[[Message], None]":
    def sink(message: "Message") -> None:
        record = message.record
        payload: dict[str, Any] = {
            "ts": record["time"].isoformat(),
            "level": record["level"].name,
            "logger": record["name"],
            "message": record["message"],
        }
        for key in CONTEXT_KEYS:
            value = record["extra"].get(key)
            if value is not None:
                payload[key] = value

        exception = record["exception"]
        if exception is not None:
            payload["error"] = redact_text(
                "".join(
                    traceback.format_exception(
                        exception.type, exception.value, exception.traceback
                    )
                ).strip()
            )

        write(json.dumps(payload, ensure_ascii=False) + "\n")

    return sink


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    logger.remove()
    logger.add(json_sink(sys.stderr.write), filter=redact_record, level=level.upper())

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handle = log_file.open("a", encoding="utf-8")
        logger.add(
            json_sink(handle.write),
            filter=redact_record,
            level=level.upper(),
            catch=False,
        )
