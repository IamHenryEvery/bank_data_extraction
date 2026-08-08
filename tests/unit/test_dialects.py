from datetime import date

import pytest

from bank_extractor.adapters.registry import get_adapter
from bank_extractor.enums import TransactionStatus, TransactionType
from bank_extractor.normalization import NormalizationError
from bank_extractor.normalization.categories import normalize_category
from bank_extractor.normalization.currency import normalize_currency
from bank_extractor.normalization.dates import parse_date
from bank_extractor.normalization.dialects import RU, Dialect
from bank_extractor.normalization.statuses import normalize_status, normalize_type

TODAY = date(2026, 6, 17)

FOREIGN = Dialect(
    name="test",
    months={"jan": 1, "jun": 6},
    relative={"today": 0, "yesterday": 1},
    statuses={"completed": TransactionStatus.POSTED, "rejected": TransactionStatus.DECLINED},
    types={"payment": TransactionType.PURCHASE, "withdrawal": TransactionType.ATM},
    hints=(("refund", TransactionType.REFUND),),
    categories={"grocery": "groceries"},
    currencies={"dollar": "USD"},
)


def test_demo_bank_declares_its_dialect_and_date_order():
    adapter = get_adapter("demo_bank")
    assert adapter.dialect is RU
    assert adapter.date_order == "dmy"


def test_same_numeric_date_differs_by_declared_order():
    assert parse_date("06.10.2026", today=TODAY, order="dmy") == date(2026, 10, 6)
    assert parse_date("06.10.2026", today=TODAY, order="mdy") == date(2026, 6, 10)
    assert parse_date("2026/10/06", today=TODAY, order="ymd") == date(2026, 10, 6)


def test_foreign_dialect_reads_its_own_words():
    assert parse_date("10 jun 2026", today=TODAY, order="mdy", dialect=FOREIGN) == date(2026, 6, 10)
    assert parse_date("yesterday", today=TODAY, order="mdy", dialect=FOREIGN) == date(2026, 6, 16)
    assert normalize_status("Completed", FOREIGN) == (TransactionStatus.POSTED, True)
    assert normalize_type("withdrawal", "", FOREIGN) == (TransactionType.ATM, True)
    assert normalize_type(None, "REFUND FOR ORDER", FOREIGN) == (TransactionType.REFUND, True)
    assert normalize_category("grocery", FOREIGN) == ("groceries", True)
    assert normalize_currency("dollar", FOREIGN) == "USD"


def test_russian_words_are_not_recognised_by_a_foreign_dialect():
    status, recognised = normalize_status("Проведена", FOREIGN)
    assert status is TransactionStatus.POSTED
    assert not recognised

    with pytest.raises(NormalizationError):
        parse_date("10 июня 2026 г.", today=TODAY, order="dmy", dialect=FOREIGN)


def test_canonical_values_are_read_by_any_dialect():
    assert normalize_status("posted", FOREIGN) == (TransactionStatus.POSTED, True)
    assert normalize_type("purchase", "", FOREIGN) == (TransactionType.PURCHASE, True)
    assert normalize_category("groceries", FOREIGN) == ("groceries", True)


def test_bank_can_extend_a_language_dialect_without_touching_it():
    quirky = RU.extend(name="quirky", statuses={"выполнено": TransactionStatus.POSTED})

    assert normalize_status("выполнено", quirky) == (TransactionStatus.POSTED, True)
    assert normalize_status("Проведена", quirky) == (TransactionStatus.POSTED, True)
    assert normalize_status("выполнено", RU)[1] is False
    assert quirky.name == "quirky"
