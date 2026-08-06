from pathlib import Path

import pytest

from bank_extractor.config import load_config
from bank_extractor.errors import ConfigError

EXAMPLE = Path(__file__).resolve().parents[2] / "config.example.yaml"


def test_loads_example_config():
    cfg = load_config(EXAMPLE)
    assert cfg.bank == "demo_bank"
    assert cfg.session.mode == "launch"
    assert cfg.output.formats == ["json", "csv", "parquet"]


def test_missing_file_raises_config_error():
    with pytest.raises(ConfigError):
        load_config(Path("/nonexistent/config.yaml"))


def test_unknown_session_mode_raises(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "bank: demo_bank\n"
        "base_url: http://localhost:8765\n"
        "period: {from: 2026-01-01, to: 2026-06-17}\n"
        "consent_file: ./consent.json\n"
        "session: {mode: telepathy}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)


def test_unknown_export_format_raises(tmp_path):
    path = tmp_path / "c.yaml"
    path.write_text(
        "bank: demo_bank\n"
        "base_url: http://localhost:8765\n"
        "period: {from: 2026-01-01, to: 2026-06-17}\n"
        "consent_file: ./consent.json\n"
        "output: {dir: ./out, formats: [json, xlsx]}\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(path)
