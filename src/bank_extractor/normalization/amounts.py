import re
from decimal import Decimal, InvalidOperation

from bank_extractor.normalization import NormalizationError

_NOISE = re.compile(r"[^\d.,]")
_PLAIN = re.compile(r"^\d+(\.\d{1,4})?$")

MAX_FRACTION_DIGITS = 4


def parse_amount(raw: str | None) -> Decimal:
    if raw is None or not str(raw).strip():
        raise NormalizationError("пустое значение суммы")

    value = str(raw).strip().replace("−", "-")
    negative = False

    if value.startswith("(") and value.endswith(")"):
        negative = True
        value = value[1:-1].strip()
    if value.startswith("-"):
        negative = True
    elif value.startswith("+"):
        value = value[1:]

    value = _NOISE.sub("", value).strip(".,")
    value = _pick_decimal_separator(value, str(raw))

    if not _PLAIN.match(value):
        raise NormalizationError(f"не удалось разобрать сумму: {raw}")

    try:
        amount = Decimal(value)
    except InvalidOperation as exc:
        raise NormalizationError(f"не удалось разобрать сумму: {raw}") from exc

    return -amount if negative else amount


def _pick_decimal_separator(value: str, original: str) -> str:
    last_comma = value.rfind(",")
    last_dot = value.rfind(".")

    if last_comma == -1 and last_dot == -1:
        return value

    decimal_pos = max(last_comma, last_dot)
    if value.count(value[decimal_pos]) > 1:
        raise NormalizationError(f"не удалось разобрать сумму: {original}")

    whole = value[:decimal_pos].replace(",", "").replace(".", "")
    fraction = value[decimal_pos + 1 :]

    if not whole.isdigit() or not fraction.isdigit():
        raise NormalizationError(f"не удалось разобрать сумму: {original}")
    if len(fraction) > MAX_FRACTION_DIGITS:
        raise NormalizationError(f"слишком длинная дробная часть: {original}")

    return f"{whole}.{fraction}"
