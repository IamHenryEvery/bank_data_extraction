import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bank_extractor.adapters.registry import get_adapter
from bank_extractor.config import AppConfig
from bank_extractor.consent import ConsentGrant
from bank_extractor.export import write_all
from bank_extractor.extraction.runner import run_extraction
from bank_extractor.report import RunStatus

pytestmark = [pytest.mark.e2e, pytest.mark.integration]

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "fixtures/golden/statement.json"
CONSENT = ROOT / "consent.example.json"
NOW = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)

VOLATILE = {"extracted_at", "run_id", "duration_s", "started_at", "finished_at"}


def normalise_volatile(payload):
    if isinstance(payload, dict):
        return {
            key: normalise_volatile(value) for key, value in payload.items() if key not in VOLATILE
        }
    if isinstance(payload, list):
        return [normalise_volatile(item) for item in payload]
    return payload


class PageSession:
    mode_resolved = "launch"

    def __init__(self, page):
        self._page = page

    def page(self):
        return self._page


def full_run(page, demo_server, out_dir):
    cfg = AppConfig.model_validate(
        {
            "bank": "demo_bank",
            "base_url": demo_server,
            "period": {"from": "2026-01-01", "to": "2026-06-17"},
            "consent_file": str(CONSENT),
            "output": {"dir": str(out_dir), "formats": ["json", "csv", "parquet"]},
            "retries": {"attempts": 2, "backoff_s": 0},
        }
    )
    grant = ConsentGrant.model_validate(json.loads(CONSENT.read_text(encoding="utf-8")))
    outcome = run_extraction(
        cfg=cfg,
        grant=grant,
        adapter=get_adapter("demo_bank"),
        session=PageSession(page),
        run_id="run_e2e",
        now=NOW,
    )
    paths = write_all(outcome.statement, outcome.report, cfg.output)
    return outcome, paths


def test_full_run_produces_all_artifacts(authenticated_page, demo_server, tmp_path):
    outcome, paths = full_run(authenticated_page, demo_server, tmp_path)

    assert outcome.report.status is RunStatus.OK
    assert {path.name for path in paths} == {
        "statement.json",
        "extraction_report.json",
        "products.csv",
        "transactions.csv",
        "transactions.parquet",
    }


def test_statement_matches_golden(authenticated_page, demo_server, tmp_path):
    full_run(authenticated_page, demo_server, tmp_path)
    produced = json.loads((tmp_path / "statement.json").read_text(encoding="utf-8"))

    if not GOLDEN.exists():
        pytest.skip("эталон ещё не создан")

    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert normalise_volatile(produced) == normalise_volatile(expected)


def test_run_is_reproducible(authenticated_page, demo_server, tmp_path):
    first, _ = full_run(authenticated_page, demo_server, tmp_path / "a")
    second, _ = full_run(authenticated_page, demo_server, tmp_path / "b")

    assert [tx.transaction_id for tx in first.statement.transactions] == [
        tx.transaction_id for tx in second.statement.transactions
    ]


def test_no_secrets_leak_into_artifacts(authenticated_page, demo_server, tmp_path):
    full_run(authenticated_page, demo_server, tmp_path)

    numbers = [
        product["number"]
        for product in json.loads(
            (ROOT / "demo_bank/data/products.json").read_text(encoding="utf-8")
        )
    ]
    forbidden = [*numbers, "password", "пароль", "не-настоящий-пароль", "cvv"]

    for path in tmp_path.glob("*"):
        if path.suffix == ".parquet" or path.is_dir():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for needle in forbidden:
            assert needle.lower() not in text, f"{needle} найдено в {path.name}"


def test_report_explains_completeness(authenticated_page, demo_server, tmp_path):
    outcome, _ = full_run(authenticated_page, demo_server, tmp_path)
    report = outcome.report

    assert report.products.total == 5
    assert report.transactions.total == 64
    assert len(report.channels_used) == 5
    assert report.consent is not None and report.consent.consent_id
    assert report.scope_restrictions == []
