from dataclasses import dataclass, replace
from typing import Literal

from bank_extractor.enums import TransactionStatus, TransactionType

DateOrder = Literal["dmy", "mdy", "ymd"]

Hints = tuple[tuple[str, TransactionType], ...]


@dataclass(frozen=True, slots=True)
class Dialect:
    name: str
    months: dict[str, int]
    relative: dict[str, int]
    statuses: dict[str, TransactionStatus]
    types: dict[str, TransactionType]
    hints: Hints
    categories: dict[str, str]
    currencies: dict[str, str]

    def extend(
        self,
        *,
        name: str | None = None,
        months: dict[str, int] | None = None,
        relative: dict[str, int] | None = None,
        statuses: dict[str, TransactionStatus] | None = None,
        types: dict[str, TransactionType] | None = None,
        hints: Hints = (),
        categories: dict[str, str] | None = None,
        currencies: dict[str, str] | None = None,
    ) -> "Dialect":
        return replace(
            self,
            name=name or self.name,
            months={**self.months, **(months or {})},
            relative={**self.relative, **(relative or {})},
            statuses={**self.statuses, **(statuses or {})},
            types={**self.types, **(types or {})},
            hints=self.hints + hints,
            categories={**self.categories, **(categories or {})},
            currencies={**self.currencies, **(currencies or {})},
        )


RU = Dialect(
    name="ru",
    months={
        "янв": 1,
        "фев": 2,
        "мар": 3,
        "апр": 4,
        "ма": 5,
        "июн": 6,
        "июл": 7,
        "авг": 8,
        "сен": 9,
        "окт": 10,
        "ноя": 11,
        "дек": 12,
    },
    relative={"сегодня": 0, "вчера": 1, "позавчера": 2},
    statuses={
        "проведена": TransactionStatus.POSTED,
        "проведено": TransactionStatus.POSTED,
        "исполнено": TransactionStatus.POSTED,
        "успешно": TransactionStatus.POSTED,
        "в обработке": TransactionStatus.PENDING,
        "обрабатывается": TransactionStatus.PENDING,
        "отклонена": TransactionStatus.DECLINED,
        "отклонено": TransactionStatus.DECLINED,
        "отказ": TransactionStatus.DECLINED,
        "удержание": TransactionStatus.HOLD,
        "заморожено": TransactionStatus.HOLD,
    },
    types={
        "покупка": TransactionType.PURCHASE,
        "оплата": TransactionType.PURCHASE,
        "перевод": TransactionType.TRANSFER,
        "комиссия": TransactionType.FEE,
        "проценты": TransactionType.INTEREST,
        "кэшбэк": TransactionType.CASHBACK,
        "возврат": TransactionType.REFUND,
        "снятие": TransactionType.ATM,
    },
    hints=(
        ("комиссия", TransactionType.FEE),
        ("кэшбэк", TransactionType.CASHBACK),
        ("кешбэк", TransactionType.CASHBACK),
        ("возврат", TransactionType.REFUND),
        ("процент", TransactionType.INTEREST),
        ("банкомат", TransactionType.ATM),
        ("atm", TransactionType.ATM),
        ("перевод", TransactionType.TRANSFER),
    ),
    categories={
        "супермаркеты": "groceries",
        "продукты": "groceries",
        "транспорт": "transport",
        "такси": "transport",
        "покупки": "shopping",
        "одежда": "shopping",
        "здоровье": "health",
        "аптеки": "health",
        "переводы": "transfers",
        "наличные": "cash",
        "комиссии": "fees",
        "развлечения": "entertainment",
        "жкх": "utilities",
    },
    currencies={
        "rur": "RUB",
        "₽": "RUB",
        "руб": "RUB",
        "руб.": "RUB",
        "р": "RUB",
        "р.": "RUB",
        "долл": "USD",
        "долл.": "USD",
        "доллар": "USD",
        "евро": "EUR",
        "$": "USD",
        "€": "EUR",
        "£": "GBP",
        "¥": "CNY",
        "₸": "KZT",
    },
)
