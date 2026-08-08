import csv
import json
import stat
from datetime import UTC, date, datetime
from decimal import Decimal

import pyarrow.parquet as pq
import pytest

from bank_extractor.config import OutputConfig
from bank_extractor.enums import Channel, ProductType, TransactionStatus, TransactionType
from bank_extractor.export import write_all
from bank_extractor.models import ConsentSummary, Period, Product, Statement, Transaction
from bank_extractor.report import ExtractionReport, RunStatus, SessionInfo

PERIOD = Period.model_validate({"from": "2026-01-01", "to": "2026-06-17"})
NOW = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)
CONSENT = ConsentSummary(consent_id="cns_1", scopes=["products"], expires_at=NOW)


@pytest.fixture
def statement() -> Statement:
    return Statement(
        bank="demo_bank",
        extracted_at=NOW,
        period=PERIOD,
        consent=CONSENT,
        products=[
            Product(
                product_id="card_001",
                type=ProductType.CARD,
                name="Карта",
                masked_number="**** 1234",
                currency="RUB",
                balance=Decimal("125000.50"),
            ),
        ],
        transactions=[
            Transaction(
                transaction_id="tx_1",
                product_id="card_001",
                operation_date=date(2026, 6, 10),
                posting_date=date(2026, 6, 11),
                amount=Decimal("-1450.50"),
                currency="RUB",
                type=TransactionType.PURCHASE,
                description="Оплата покупки",
                counterparty="STORE",
                category="shopping",
                status=TransactionStatus.POSTED,
                source_channel=Channel.API,
            ),
        ],
    )


@pytest.fixture
def report() -> ExtractionReport:
    return ExtractionReport(
        run_id="run_1",
        bank="demo_bank",
        status=RunStatus.OK,
        period=PERIOD,
        session=SessionInfo(mode_requested="launch", mode_resolved="launch"),
        consent=CONSENT,
        started_at=NOW,
        finished_at=NOW,
        duration_s=1.5,
    )


def test_writes_every_requested_format(statement, report, tmp_path):
    cfg = OutputConfig(dir=tmp_path, formats=["json", "csv", "parquet"])
    paths = write_all(statement, report, cfg)
    names = {path.name for path in paths}
    assert names == {
        "statement.json",
        "extraction_report.json",
        "products.csv",
        "transactions.csv",
        "transactions.parquet",
    }


def test_report_is_written_even_without_json_format(statement, report, tmp_path):
    write_all(statement, report, OutputConfig(dir=tmp_path, formats=["csv"]))
    assert (tmp_path / "extraction_report.json").exists()
    assert not (tmp_path / "statement.json").exists()


def test_json_matches_tz_structure(statement, report, tmp_path):
    write_all(statement, report, OutputConfig(dir=tmp_path, formats=["json"]))
    payload = json.loads((tmp_path / "statement.json").read_text(encoding="utf-8"))

    assert payload["bank"] == "demo_bank"
    assert payload["period"] == {"from": "2026-01-01", "to": "2026-06-17"}
    assert payload["products"][0]["masked_number"] == "**** 1234"
    assert payload["transactions"][0]["amount"] == "-1450.50"


def test_json_keeps_russian_text_readable(statement, report, tmp_path):
    write_all(statement, report, OutputConfig(dir=tmp_path, formats=["json"]))
    raw = (tmp_path / "statement.json").read_text(encoding="utf-8")
    assert "Оплата покупки" in raw


def test_csv_is_readable_and_keeps_amount_precision(statement, report, tmp_path):
    write_all(statement, report, OutputConfig(dir=tmp_path, formats=["csv"]))
    text = (tmp_path / "transactions.csv").read_text(encoding="utf-8-sig")
    rows = list(csv.DictReader(text.splitlines()))

    assert rows[0]["transaction_id"] == "tx_1"
    assert rows[0]["amount"] == "-1450.50"
    assert rows[0]["description"] == "Оплата покупки"


def test_parquet_round_trips_decimals(statement, report, tmp_path):
    write_all(statement, report, OutputConfig(dir=tmp_path, formats=["parquet"]))
    table = pq.read_table(tmp_path / "transactions.parquet")

    assert table.num_rows == 1
    assert table.column("amount")[0].as_py() == Decimal("-1450.50")


def test_output_directory_is_private(statement, report, tmp_path):
    target = tmp_path / "out"
    write_all(statement, report, OutputConfig(dir=target, formats=["json"]))
    mode = stat.S_IMODE(target.stat().st_mode)
    assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0


def test_empty_statement_still_produces_valid_files(report, tmp_path):
    empty = Statement(bank="demo_bank", extracted_at=NOW, period=PERIOD, consent=CONSENT)
    write_all(empty, report, OutputConfig(dir=tmp_path, formats=["json", "csv", "parquet"]))

    assert json.loads((tmp_path / "statement.json").read_text())["transactions"] == []
    assert (tmp_path / "transactions.csv").read_text(encoding="utf-8-sig").strip()
    assert pq.read_table(tmp_path / "transactions.parquet").num_rows == 0
