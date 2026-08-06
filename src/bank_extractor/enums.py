from enum import StrEnum


class Channel(StrEnum):
    API = "api"
    EXPORT = "export"
    DOM = "dom"


class ProductType(StrEnum):
    CARD = "card"
    ACCOUNT = "account"
    SAVINGS = "savings"
    DEPOSIT = "deposit"
    CREDIT = "credit"


class ProductStatus(StrEnum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class TransactionType(StrEnum):
    PURCHASE = "purchase"
    TRANSFER = "transfer"
    FEE = "fee"
    INTEREST = "interest"
    CASHBACK = "cashback"
    REFUND = "refund"
    ATM = "atm"
    OTHER = "other"


class TransactionStatus(StrEnum):
    POSTED = "posted"
    PENDING = "pending"
    DECLINED = "declined"
    HOLD = "hold"


class ExtractionStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


class Scope(StrEnum):
    PRODUCTS = "products"
    BALANCES = "balances"
    TRANSACTIONS = "transactions"
    REQUISITES = "requisites"
