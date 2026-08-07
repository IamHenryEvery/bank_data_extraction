from bank_extractor.adapters.base import BankAdapter

_REGISTRY: dict[str, BankAdapter] = {}


def register(adapter: BankAdapter) -> None:
    _REGISTRY[adapter.name] = adapter


def get_adapter(name: str) -> BankAdapter:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"адаптер для банка '{name}' не зарегистрирован. Известные: {sorted(_REGISTRY)}"
        ) from None


def known_banks() -> list[str]:
    return sorted(_REGISTRY)
