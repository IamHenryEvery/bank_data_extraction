import json

import pytest
from loguru import logger

from bank_extractor.logging_setup import json_sink, redact_record, setup_logging


@pytest.fixture
def captured() -> list[str]:
    lines: list[str] = []
    logger.remove()
    logger.add(json_sink(lines.append), filter=redact_record, level="DEBUG")
    yield lines
    logger.remove()


def test_sink_emits_one_json_line_per_record(captured):
    logger.info("этап начат")

    assert len(captured) == 1
    payload = json.loads(captured[0])
    assert payload["level"] == "INFO"
    assert payload["message"] == "этап начат"
    assert payload["ts"]


def test_redacts_pan_in_message(captured):
    logger.info("карта 4276123456781234")
    assert "4276123456781234" not in captured[0]
    assert "**** 1234" in captured[0]


def test_redacts_pan_in_interpolated_argument(captured):
    logger.info("карта {}", "4276123456781234")
    assert "4276123456781234" not in captured[0]


def test_redacts_pan_in_bound_context(captured):
    logger.bind(product_id="4276123456781234").info("продукт обработан")
    assert "4276123456781234" not in captured[0]


def test_bound_context_lands_in_payload(captured):
    logger.bind(stage="auth", channel="api").info("канал опрошен")

    payload = json.loads(captured[0])
    assert payload["stage"] == "auth"
    assert payload["channel"] == "api"


def test_exception_is_serialised_without_breaking_json(captured):
    try:
        raise ValueError("карта 4276123456781234 недоступна")
    except ValueError:
        logger.exception("канал упал")

    payload = json.loads(captured[0])
    assert "4276123456781234" not in payload["error"]
    assert payload["level"] == "ERROR"


def test_setup_logging_writes_json_to_file(tmp_path):
    log_file = tmp_path / "nested" / "extraction.log"
    setup_logging("INFO", log_file)
    logger.info("карта 4276123456781234")
    logger.remove()

    payload = json.loads(log_file.read_text(encoding="utf-8").strip())
    assert "4276123456781234" not in payload["message"]


def test_setup_logging_respects_level(tmp_path):
    log_file = tmp_path / "extraction.log"
    setup_logging("WARNING", log_file)
    logger.debug("подробность")
    logger.warning("проблема")
    logger.remove()

    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["level"] == "WARNING"
