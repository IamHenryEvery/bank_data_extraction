from decimal import Decimal

import pytest

from bank_extractor.normalization import NormalizationError
from bank_extractor.normalization.amounts import parse_amount

NBSP = " "
THIN = " "


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1450.50", Decimal("1450.50")),
        ("1450,50", Decimal("1450.50")),
        (f"1{NBSP}450,50", Decimal("1450.50")),
        (f"1{THIN}450,50", Decimal("1450.50")),
        ("1 450,50", Decimal("1450.50")),
        ("-1 450,50", Decimal("-1450.50")),
        ("−1 450,50", Decimal("-1450.50")),
        ("(1 450,50)", Decimal("-1450.50")),
        ("+1 450,50", Decimal("1450.50")),
        ("1 450,50 ₽", Decimal("1450.50")),
        ("1 450,50 руб.", Decimal("1450.50")),
        ("$1450.50", Decimal("1450.50")),
        ("1 234 567,89", Decimal("1234567.89")),
        ("0,00", Decimal("0.00")),
        ("100", Decimal("100")),
    ],
)
def test_parses_known_formats(raw, expected):
    assert parse_amount(raw) == expected


def test_mixed_separators_treat_last_as_decimal():
    assert parse_amount("1,450.50") == Decimal("1450.50")
    assert parse_amount("1.450,50") == Decimal("1450.50")


def test_result_is_decimal_not_float():
    assert isinstance(parse_amount("0,1"), Decimal)
    assert parse_amount("0,1") + parse_amount("0,2") == Decimal("0.3")


@pytest.mark.parametrize("raw", ["", "   ", "бесплатно", "—", "1,2,3.4.5", None])
def test_rejects_garbage(raw):
    with pytest.raises(NormalizationError):
        parse_amount(raw)
