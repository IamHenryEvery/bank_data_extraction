from bank_extractor.normalization.dialects import RU, Dialect

CANONICAL = {
    "groceries",
    "transport",
    "shopping",
    "health",
    "transfers",
    "cash",
    "fees",
    "cashback",
    "interest",
    "entertainment",
    "utilities",
}


def normalize_category(raw: str | None, dialect: Dialect = RU) -> tuple[str | None, bool]:
    if raw is None or not raw.strip():
        return None, True

    value = raw.strip().lower()
    if value in CANONICAL:
        return value, True
    if mapped := dialect.categories.get(value):
        return mapped, True
    return raw.strip(), False
