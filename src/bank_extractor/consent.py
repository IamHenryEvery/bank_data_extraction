import json
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ValidationError

from bank_extractor.enums import Scope
from bank_extractor.errors import ConsentError
from bank_extractor.models import ConsentSummary, Period


class ConsentGrant(BaseModel):
    consent_id: str
    client_ref: str
    bank: str
    scopes: list[Scope]
    period: Period
    granted_at: datetime
    expires_at: datetime
    method: str


def load_consent(path: Path) -> ConsentGrant:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConsentError(f"файл согласия не найден: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConsentError(f"не удалось разобрать JSON согласия: {path}") from exc

    try:
        return ConsentGrant.model_validate(raw)
    except ValidationError as exc:
        raise ConsentError(f"согласие невалидно: {exc}") from exc


def verify_consent(
    grant: ConsentGrant, *, bank: str, period: Period, now: datetime | None = None
) -> None:
    moment = now or datetime.now(UTC)

    if grant.bank != bank:
        raise ConsentError(f"согласие выдано на банк {grant.bank}, запрошен {bank}")

    if grant.expires_at <= moment:
        raise ConsentError(f"срок согласия истек: {grant.expires_at.isoformat()}")

    if not grant.period.contains(period):
        raise ConsentError(
            "запрошенный период выходит за границы согласия: "
            f"{period.from_}..{period.to} против {grant.period.from_}..{grant.period.to}"
        )

    if Scope.PRODUCTS not in grant.scopes:
        raise ConsentError("в согласии нет скоупа products — извлекать нечего")


def allowed(grant: ConsentGrant, scope: Scope) -> bool:
    return scope in grant.scopes


def to_summary(grant: ConsentGrant) -> ConsentSummary:
    return ConsentSummary(
        consent_id=grant.consent_id, scopes=grant.scopes, expires_at=grant.expires_at
    )
