from collections import OrderedDict
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from bank_extractor.enums import Channel
from bank_extractor.models import ConsentSummary, Period
from bank_extractor.normalization.normalizer import Rejected
from bank_extractor.validation.checks import ValidationWarning


class RunStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


class WarningCount(BaseModel):
    code: str
    count: int
    sample: str | None = None


class ProductFailure(BaseModel):
    product_id: str
    channels_tried: list[Channel] = Field(default_factory=list)
    reason: str


class SessionInfo(BaseModel):
    mode_requested: str
    mode_resolved: str


class ProductsReport(BaseModel):
    total: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    failed: list[ProductFailure] = Field(default_factory=list)


class TransactionsReport(BaseModel):
    total: int = 0
    by_product: dict[str, int] = Field(default_factory=dict)
    rejected: int = 0


class NormalizationReport(BaseModel):
    fields_total: int = 0
    fields_normalized: int = 0
    warnings: list[WarningCount] = Field(default_factory=list)


class ErrorEntry(BaseModel):
    code: str
    message: str
    product_id: str | None = None
    channel: Channel | None = None


class ExtractionReport(BaseModel):
    run_id: str
    bank: str
    status: RunStatus
    period: Period
    session: SessionInfo | None = None
    consent: ConsentSummary | None = None
    started_at: datetime
    finished_at: datetime
    duration_s: float
    products: ProductsReport = Field(default_factory=ProductsReport)
    transactions: TransactionsReport = Field(default_factory=TransactionsReport)
    channels_used: dict[str, Channel] = Field(default_factory=dict)
    normalization: NormalizationReport = Field(default_factory=NormalizationReport)
    validation: list[ValidationWarning] = Field(default_factory=list)
    rejected: list[Rejected] = Field(default_factory=list)
    errors: list[ErrorEntry] = Field(default_factory=list)
    scope_restrictions: list[str] = Field(default_factory=list)


def summarise_warnings(warnings: Iterable[Any], code_attr: str = "code") -> list[WarningCount]:
    buckets: OrderedDict[str, WarningCount] = OrderedDict()
    for warning in warnings:
        code = getattr(warning, code_attr)
        sample = getattr(warning, "raw_value", None) or getattr(warning, "message", None)
        if code in buckets:
            buckets[code].count += 1
        else:
            buckets[code] = WarningCount(code=code, count=1, sample=sample)
    return list(buckets.values())
