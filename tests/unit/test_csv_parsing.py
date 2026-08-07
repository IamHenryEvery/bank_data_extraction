from pathlib import Path

import pytest

from bank_extractor.adapters.demo_bank.export import CSV_HEADER, parse_csv
from bank_extractor.errors import ChannelFailed

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures/demo_bank/transactions_export.csv"


def test_parses_all_rows_from_fixture():
    rows = parse_csv(FIXTURE.read_bytes(), product_id="card_001")
    assert len(rows) == 34
    assert all(row.product_id == "card_001" for row in rows)


def test_keeps_bank_formats_untouched():
    rows = parse_csv(FIXTURE.read_bytes(), product_id="card_001")
    assert any("." in row.operation_date for row in rows)
    assert any("," in row.amount for row in rows)


def test_csv_has_no_external_ids():
    rows = parse_csv(FIXTURE.read_bytes(), product_id="card_001")
    assert all(row.external_id is None for row in rows)


def test_russian_statuses_survive_to_normalization():
    rows = parse_csv(FIXTURE.read_bytes(), product_id="card_001")
    assert {"Проведена", "В обработке", "Отклонена"} & {row.status for row in rows}


def test_empty_export_yields_empty_list():
    header = ";".join(CSV_HEADER).encode("cp1251") + b"\r\n"
    assert parse_csv(header, product_id="acc_002") == []


def test_unexpected_header_raises_channel_failed():
    broken = "Дата;Сумма\r\n01.01.2026;100,00\r\n".encode("cp1251")
    with pytest.raises(ChannelFailed, match="шапка"):
        parse_csv(broken, product_id="card_001")


def test_wrong_encoding_raises_channel_failed():
    with pytest.raises(ChannelFailed, match="кодировк"):
        parse_csv("Дата операции;Сумма".encode(), product_id="card_001")
