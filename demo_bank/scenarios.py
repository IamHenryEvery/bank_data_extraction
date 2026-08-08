import re
from collections import Counter
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from starlette.middleware.base import BaseHTTPMiddleware

SCENARIO_COOKIE = "demo_scenario"
SESSION_COOKIE = "demo_session"

EMPTY_PRODUCT = "acc_002"
BROKEN_PRODUCT = "card_001"
FAILING_PRODUCT = "sav_003"

SESSION_TTL_REQUESTS = 3
PAGE_OVERLAP = 1

MONTHS_RU = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}

NBSP = " "


class Scenario(StrEnum):
    DEFAULT = "default"
    EMPTY_HISTORY = "empty_history"
    BROKEN_FORMATS = "broken_formats"
    API_DOWN = "api_down"
    EXPORT_DOWN = "export_down"
    SLOW_LOAD = "slow_load"
    PARTIAL_FAILURE = "partial_failure"
    SESSION_EXPIRED = "session_expired"
    DUPLICATE_PAGE = "duplicate_page"
    STUCK_CURSOR = "stuck_cursor"


def current(request: Request) -> Scenario:
    raw = request.cookies.get(SCENARIO_COOKIE, Scenario.DEFAULT)
    try:
        return Scenario(raw)
    except ValueError:
        return Scenario.DEFAULT


_first_attempt_seen: Counter[str] = Counter()
_session_requests: Counter[str] = Counter()


def reset_counters() -> None:
    _first_attempt_seen.clear()
    _session_requests.clear()


_API_TX = re.compile(r"^/api/products/(?P<product_id>[^/]+)/transactions$")


class ScenarioMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        scenario = current(request)
        path = request.url.path

        if scenario is Scenario.SESSION_EXPIRED and path.startswith(("/api/", "/export/")):
            token = request.cookies.get(SESSION_COOKIE, "")
            _session_requests[token] += 1
            if _session_requests[token] > SESSION_TTL_REQUESTS:
                return JSONResponse({"detail": "сессия истекла"}, status_code=401)

        match = _API_TX.match(path)
        if match is not None:
            product_id = match.group("product_id")
        else:
            product_id = request.query_params.get("product_id", "")

        if scenario is Scenario.PARTIAL_FAILURE and (
            product_id == FAILING_PRODUCT or path == f"/accounts/{FAILING_PRODUCT}"
        ):
            return PlainTextResponse("внутренняя ошибка", status_code=500)

        if scenario in (Scenario.API_DOWN, Scenario.EXPORT_DOWN) and path.startswith("/api/"):
            return JSONResponse({"detail": "сервис недоступен"}, status_code=503)

        if scenario is Scenario.EXPORT_DOWN and path == "/export/transactions.csv":
            return PlainTextResponse("ошибка выгрузки", status_code=500)

        if scenario is Scenario.SLOW_LOAD and match is not None:
            key = f"{path}?{request.url.query}"
            _first_attempt_seen[key] += 1
            if _first_attempt_seen[key] == 1:
                return JSONResponse({"detail": "шлюз не ответил"}, status_code=504)

        return await call_next(request)


def shift_cursor(scenario: Scenario, cursor: int) -> int:
    if scenario is Scenario.DUPLICATE_PAGE:
        return max(0, cursor - PAGE_OVERLAP)
    if scenario is Scenario.STUCK_CURSOR:
        return 0
    return cursor


def override_next_cursor(scenario: Scenario, cursor: int, next_cursor: int | None) -> int | None:
    if scenario is Scenario.STUCK_CURSOR:
        return cursor + 1
    return next_cursor


def apply_data_scenario(
    scenario: Scenario, product_id: str, rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if scenario is Scenario.EMPTY_HISTORY and product_id == EMPTY_PRODUCT:
        return []
    if scenario is Scenario.BROKEN_FORMATS and product_id == BROKEN_PRODUCT:
        return format_dates_broken(rows)
    return rows


def format_dates_broken(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for index, row in enumerate(rows):
        item = dict(row)
        year, month, day = row["operation_date"].split("-")

        if index % 3 == 0:
            item["operation_date"] = f"{day}.{month}.{year}"
        elif index % 3 == 1:
            item["operation_date"] = f"{int(day)} {MONTHS_RU[int(month)]} {year} г."

        if index % 2 == 0:
            item["amount"] = _spaced(row["amount"])
        else:
            item["amount"] = _parenthesised(row["amount"])

        out.append(item)
    return out


def _spaced(amount: str) -> str:
    negative = amount.startswith("-")
    whole, _, fraction = amount.lstrip("-").partition(".")
    groups: list[str] = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]
    return f"{'-' if negative else ''}{NBSP.join(groups)},{fraction}"


def _parenthesised(amount: str) -> str:
    if not amount.startswith("-"):
        return _spaced(amount)
    return f"({_spaced(amount).lstrip('-')})"
