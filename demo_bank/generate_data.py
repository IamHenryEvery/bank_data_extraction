import json
import random
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

DATA = Path(__file__).parent / "data"

SEED = 20260806
PERIOD_FROM = date(2026, 1, 1)
PERIOD_TO = date(2026, 6, 17)

MERCHANTS = [
    ("PYATEROCHKA MOSCOW", "groceries", "5411", "purchase"),
    ("YANDEX GO", "transport", "4121", "purchase"),
    ("OZON RU", "shopping", "5399", "purchase"),
    ("APTEKA 36.6", "health", "5912", "purchase"),
    ("IVAN P.", "transfers", None, "transfer"),
    ("ATM 4412 MOSCOW", "cash", "6011", "atm"),
    ("КОМИССИЯ ЗА ПЕРЕВОД", "fees", None, "fee"),
    ("КЭШБЭК ЗА ПОКУПКИ", "cashback", None, "cashback"),
    ("ВОЗВРАТ OZON RU", "shopping", "5399", "refund"),
    ("НАЧИСЛЕНИЕ ПРОЦЕНТОВ", "interest", None, "interest"),
]

PRODUCT_PLAN = {
    "card_001": (34, "RUB"),
    "acc_002": (12, "RUB"),
    "sav_003": (6, "USD"),
    "dep_004": (4, "RUB"),
    "cred_005": (8, "RUB"),
}


def build() -> list[dict[str, Any]]:
    rng = random.Random(SEED)
    span = (PERIOD_TO - PERIOD_FROM).days
    rows: list[dict[str, Any]] = []

    for product_id, (count, currency) in PRODUCT_PLAN.items():
        for index in range(count):
            counterparty, category, mcc, tx_type = rng.choice(MERCHANTS)
            operation = PERIOD_FROM + timedelta(days=rng.randint(0, span))
            posting = operation + timedelta(days=rng.choice([0, 0, 1, 1, 2]))
            positive = tx_type in {"cashback", "refund", "interest"}
            amount = Decimal(rng.randrange(5_000, 900_000)) / 100
            if not positive:
                amount = -amount

            status = "posted"
            if index == 0:
                status = "pending"
            elif index == 1 and tx_type == "purchase":
                status = "declined"

            rows.append(
                {
                    "id": f"{product_id}_tx_{index:03d}",
                    "product_id": product_id,
                    "operation_date": operation.isoformat(),
                    "posting_date": posting.isoformat() if status == "posted" else None,
                    "amount": f"{amount:.2f}",
                    "currency": currency,
                    "type": tx_type,
                    "description": f"Операция {counterparty.title()}",
                    "counterparty": counterparty,
                    "category": category,
                    "status": status,
                    "mcc": mcc,
                }
            )

    rows.sort(key=lambda row: (row["operation_date"], row["id"]), reverse=True)
    return rows


if __name__ == "__main__":
    path = DATA / "transactions.json"
    path.write_text(json.dumps(build(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"записано: {path}")
