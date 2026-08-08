from bank_extractor.normalization import NormalizationError
from bank_extractor.normalization.dialects import RU, Dialect


def normalize_currency(raw: str | None, dialect: Dialect = RU) -> str:
    if raw is None or not str(raw).strip():
        raise NormalizationError("пустое значение валюты")

    value = str(raw).strip().lower()
    if resolved := dialect.currencies.get(value):
        return resolved
    if len(value) == 3 and value.isalpha() and value.isascii():
        return value.upper()

    raise NormalizationError(f"неизвестная валюта: {raw}")
