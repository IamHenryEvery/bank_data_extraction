import re
from datetime import date, timedelta

from bank_extractor.normalization import NormalizationError
from bank_extractor.normalization.dialects import RU, DateOrder, Dialect

_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$")
_NUMERIC = re.compile(r"^(\d{1,4})[./-](\d{1,2})[./-](\d{2}|\d{4})$")
_VERBAL = re.compile(r"^(\d{1,2})\s+(\w+)\.?\s+(\d{4})(?:\s*г\.?)?$")


def parse_date(raw: str | None, *, today: date, order: DateOrder, dialect: Dialect = RU) -> date:
    if not raw or not str(raw).strip():
        raise NormalizationError("пустое значение даты")

    value = str(raw).strip()

    if (offset := dialect.relative.get(value.lower())) is not None:
        return today - timedelta(days=offset)

    if match := _ISO.match(value):
        return _build(int(match[1]), int(match[2]), int(match[3]), value)

    if match := _NUMERIC.match(value):
        return _build(*_order_parts(match[1], match[2], match[3], order), value)

    if match := _VERBAL.match(value):
        month = _month_from_name(match[2], value, dialect)
        return _build(int(match[3]), month, int(match[1]), value)

    raise NormalizationError(f"неизвестный формат даты: {value}")


def _order_parts(first: str, second: str, third: str, order: DateOrder) -> tuple[int, int, int]:
    if order == "dmy":
        return _with_century(third), int(second), int(first)
    if order == "mdy":
        return _with_century(third), int(first), int(second)
    return _with_century(first), int(second), int(third)


def _with_century(year: str) -> int:
    value = int(year)
    return value + 2000 if value < 100 else value


def _month_from_name(name: str, original: str, dialect: Dialect) -> int:
    lowered = name.lower().rstrip(".")
    for prefix, number in dialect.months.items():
        if lowered.startswith(prefix):
            return number
    raise NormalizationError(f"неизвестный месяц в дате: {original}")


def _build(year: int, month: int, day: int, original: str) -> date:
    try:
        return date(year, month, day)
    except ValueError as exc:
        raise NormalizationError(f"недопустимая дата: {original}") from exc
