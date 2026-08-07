import pytest

from bank_extractor.adapters.demo_bank import export
from bank_extractor.errors import ChannelFailed
from bank_extractor.models import Period

pytestmark = pytest.mark.integration

PERIOD = Period.model_validate({"from": "2026-01-01", "to": "2026-06-17"})


def test_downloads_and_parses_export(authenticated_page, demo_server, tmp_path):
    rows = export.fetch_transactions(
        authenticated_page, demo_server, "card_001", PERIOD, download_dir=tmp_path
    )
    assert len(rows) == 34


def test_download_file_is_removed_after_parsing(authenticated_page, demo_server, tmp_path):
    export.fetch_transactions(
        authenticated_page, demo_server, "card_001", PERIOD, download_dir=tmp_path
    )
    assert list(tmp_path.glob("*.csv")) == []


def test_period_narrows_export(authenticated_page, demo_server, tmp_path):
    narrow = Period.model_validate({"from": "2026-06-01", "to": "2026-06-17"})
    rows = export.fetch_transactions(
        authenticated_page, demo_server, "card_001", narrow, download_dir=tmp_path
    )
    assert 0 < len(rows) < 34


@pytest.mark.scenario("empty_history")
def test_empty_export_is_not_an_error(scenario_page, demo_server, tmp_path):
    rows = export.fetch_transactions(
        scenario_page, demo_server, "acc_002", PERIOD, download_dir=tmp_path
    )
    assert rows == []


@pytest.mark.scenario("export_down")
def test_broken_export_raises_channel_failed(scenario_page, demo_server, tmp_path):
    with pytest.raises(ChannelFailed):
        export.fetch_transactions(
            scenario_page, demo_server, "card_001", PERIOD, download_dir=tmp_path, timeout_s=5
        )
