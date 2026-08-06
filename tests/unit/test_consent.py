import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from bank_extractor.consent import allowed, load_consent, to_summary, verify_consent
from bank_extractor.enums import Scope
from bank_extractor.errors import ConsentError
from bank_extractor.models import Period

EXAMPLE = Path(__file__).resolve().parents[2] / "consent.example.json"
NOW = datetime(2026, 8, 6, 10, 0, tzinfo=UTC)
PERIOD = Period.model_validate({"from": "2026-01-01", "to": "2026-06-17"})


def write_grant(tmp_path, **overrides):
    payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    payload.update(overrides)
    path = tmp_path / "consent.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_example_grant_passes_verification():
    grant = load_consent(EXAMPLE)
    verify_consent(grant, bank="demo_bank", period=PERIOD, now=NOW)


def test_missing_file_raises():
    with pytest.raises(ConsentError):
        load_consent(Path("/nonexistent/consent.json"))


def test_expired_grant_rejected(tmp_path):
    grant = load_consent(write_grant(tmp_path, expires_at="2026-08-06T09:30:00Z"))
    with pytest.raises(ConsentError, match="истек"):
        verify_consent(grant, bank="demo_bank", period=PERIOD, now=NOW)


def test_wrong_bank_rejected(tmp_path):
    grant = load_consent(write_grant(tmp_path, bank="other_bank"))
    with pytest.raises(ConsentError, match="банк"):
        verify_consent(grant, bank="demo_bank", period=PERIOD, now=NOW)


def test_period_wider_than_grant_rejected(tmp_path):
    grant = load_consent(write_grant(tmp_path, period={"from": "2026-03-01", "to": "2026-04-01"}))
    with pytest.raises(ConsentError, match="период"):
        verify_consent(grant, bank="demo_bank", period=PERIOD, now=NOW)


def test_grant_without_products_scope_rejected(tmp_path):
    grant = load_consent(write_grant(tmp_path, scopes=["transactions"]))
    with pytest.raises(ConsentError, match="products"):
        verify_consent(grant, bank="demo_bank", period=PERIOD, now=NOW)


def test_allowed_reflects_scopes(tmp_path):
    grant = load_consent(write_grant(tmp_path, scopes=["products", "balances"]))
    assert allowed(grant, Scope.BALANCES)
    assert not allowed(grant, Scope.REQUISITES)


def test_summary_carries_no_client_reference():
    summary = to_summary(load_consent(EXAMPLE))
    dumped = summary.model_dump_json()
    assert "client_7f3a" not in dumped
    assert summary.consent_id
