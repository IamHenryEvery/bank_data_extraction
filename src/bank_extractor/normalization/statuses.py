from bank_extractor.enums import TransactionStatus, TransactionType
from bank_extractor.normalization.dialects import RU, Dialect

_CANONICAL_STATUSES = {status.value: status for status in TransactionStatus}
_CANONICAL_TYPES = {kind.value: kind for kind in TransactionType}


def normalize_status(raw: str | None, dialect: Dialect = RU) -> tuple[TransactionStatus, bool]:
    if raw is None or not raw.strip():
        return TransactionStatus.POSTED, False

    value = raw.strip().lower()
    resolved = _CANONICAL_STATUSES.get(value) or dialect.statuses.get(value)
    return (resolved, True) if resolved else (TransactionStatus.POSTED, False)


def normalize_type(
    raw: str | None, description: str = "", dialect: Dialect = RU
) -> tuple[TransactionType, bool]:
    if raw and raw.strip():
        value = raw.strip().lower()
        if resolved := _CANONICAL_TYPES.get(value) or dialect.types.get(value):
            return resolved, True

    lowered = description.lower()
    for needle, kind in dialect.hints:
        if needle in lowered:
            return kind, True

    return TransactionType.OTHER, False
