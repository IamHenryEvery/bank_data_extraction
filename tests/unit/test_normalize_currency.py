import pytest

from bank_extractor.normalization import NormalizationError
from bank_extractor.normalization.currency import normalize_currency


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("RUB", "RUB"),
        ("rub", "RUB"),
        ("RUR", "RUB"),
        ("₽", "RUB"),
        ("руб.", "RUB"),
        ("руб", "RUB"),
        ("Р", "RUB"),
        ("USD", "USD"),
        ("$", "USD"),
        ("долл.", "USD"),
        ("EUR", "EUR"),
        ("€", "EUR"),
        ("  usd  ", "USD"),
    ],
)
def test_normalizes_known_currencies(raw, expected):
    assert normalize_currency(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", "¤", "биткоин", None])
def test_rejects_unknown(raw):
    with pytest.raises(NormalizationError):
        normalize_currency(raw)
