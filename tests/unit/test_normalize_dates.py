from datetime import date

import pytest

from bank_extractor.normalization import NormalizationError
from bank_extractor.normalization.dates import parse_date

TODAY = date(2026, 6, 17)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026-06-10", date(2026, 6, 10)),
        ("10.06.2026", date(2026, 6, 10)),
        ("10/06/2026", date(2026, 6, 10)),
        ("10-06-2026", date(2026, 6, 10)),
        ("10.06.26", date(2026, 6, 10)),
        ("10 июня 2026 г.", date(2026, 6, 10)),
        ("10 июня 2026", date(2026, 6, 10)),
        ("10 июн 2026", date(2026, 6, 10)),
        ("1 января 2026 г.", date(2026, 1, 1)),
        ("1 марта 2026", date(2026, 3, 1)),
        ("1 мая 2026", date(2026, 5, 1)),
        ("  2026-06-10  ", date(2026, 6, 10)),
        ("Сегодня", date(2026, 6, 17)),
        ("сегодня", date(2026, 6, 17)),
        ("Вчера", date(2026, 6, 16)),
    ],
)
def test_parses_known_formats(raw, expected):
    assert parse_date(raw, today=TODAY, order="dmy") == expected


def test_day_month_order_follows_the_declared_order():
    assert parse_date("06.10.2026", today=TODAY, order="dmy") == date(2026, 10, 6)
    assert parse_date("06.10.2026", today=TODAY, order="mdy") == date(2026, 6, 10)


@pytest.mark.parametrize("raw", ["", "   ", "не дата", "32.13.2026", "2026-13-45", None])
def test_rejects_garbage(raw):
    with pytest.raises(NormalizationError):
        parse_date(raw, today=TODAY, order="dmy")


def test_error_carries_raw_value_for_the_report():
    with pytest.raises(NormalizationError, match="кракозябра"):
        parse_date("кракозябра", today=TODAY, order="dmy")
