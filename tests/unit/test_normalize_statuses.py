import pytest

from bank_extractor.enums import TransactionStatus, TransactionType
from bank_extractor.normalization.categories import normalize_category
from bank_extractor.normalization.statuses import normalize_status, normalize_type


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("posted", TransactionStatus.POSTED),
        ("Проведена", TransactionStatus.POSTED),
        ("Исполнено", TransactionStatus.POSTED),
        ("pending", TransactionStatus.PENDING),
        ("В обработке", TransactionStatus.PENDING),
        ("Обрабатывается", TransactionStatus.PENDING),
        ("declined", TransactionStatus.DECLINED),
        ("Отклонена", TransactionStatus.DECLINED),
        ("hold", TransactionStatus.HOLD),
        ("Удержание", TransactionStatus.HOLD),
    ],
)
def test_known_statuses_are_recognised(raw, expected):
    status, recognised = normalize_status(raw)
    assert status is expected
    assert recognised


def test_unknown_status_defaults_to_posted_and_flags_it():
    status, recognised = normalize_status("Какой-то новый статус")
    assert status is TransactionStatus.POSTED
    assert not recognised


def test_missing_status_defaults_to_posted():
    status, recognised = normalize_status(None)
    assert status is TransactionStatus.POSTED
    assert not recognised


@pytest.mark.parametrize(
    ("raw", "description", "expected"),
    [
        ("purchase", "", TransactionType.PURCHASE),
        ("Покупка", "", TransactionType.PURCHASE),
        ("transfer", "", TransactionType.TRANSFER),
        ("Перевод", "", TransactionType.TRANSFER),
        ("fee", "", TransactionType.FEE),
        (None, "КОМИССИЯ ЗА ПЕРЕВОД", TransactionType.FEE),
        (None, "КЭШБЭК ЗА ПОКУПКИ", TransactionType.CASHBACK),
        (None, "ВОЗВРАТ OZON RU", TransactionType.REFUND),
        (None, "ATM 4412 MOSCOW", TransactionType.ATM),
    ],
)
def test_type_falls_back_to_description(raw, description, expected):
    kind, _ = normalize_type(raw, description)
    assert kind is expected


def test_unknown_type_becomes_other_and_flags_it():
    kind, recognised = normalize_type("нечто", "нечто")
    assert kind is TransactionType.OTHER
    assert not recognised


def test_unknown_category_passes_through_unchanged():
    category, recognised = normalize_category("странная_категория")
    assert category == "странная_категория"
    assert not recognised


def test_known_category_is_mapped():
    category, recognised = normalize_category("groceries")
    assert category == "groceries"
    assert recognised
