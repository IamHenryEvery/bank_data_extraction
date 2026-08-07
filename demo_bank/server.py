import csv
import io
import json
import secrets
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from demo_bank import scenarios
from demo_bank.scenarios import SCENARIO_COOKIE, SESSION_COOKIE, ScenarioMiddleware

BASE = Path(__file__).parent
DATA = BASE / "data"
PAGE_SIZE = 20

app = FastAPI(title="Демо-банк")
app.add_middleware(ScenarioMiddleware)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
templates = Jinja2Templates(directory=BASE / "templates")

PRODUCTS: list[dict[str, Any]] = json.loads((DATA / "products.json").read_text(encoding="utf-8"))
TRANSACTIONS: list[dict[str, Any]] = json.loads(
    (DATA / "transactions.json").read_text(encoding="utf-8")
)

SESSIONS: set[str] = set()


def mask(number: str) -> str:
    return f"**** {number[-4:]}"


def is_logged_in(request: Request) -> bool:
    return request.cookies.get(SESSION_COOKIE, "") in SESSIONS


def require_login(request: Request) -> None:
    if not is_logged_in(request):
        raise HTTPException(status_code=401, detail="не авторизован")


def public_product(product: dict[str, Any]) -> dict[str, Any]:
    out = {key: value for key, value in product.items() if key not in {"number", "requisites"}}
    out["masked_number"] = mask(product["number"])
    if "requisites" in product:
        requisites = dict(product["requisites"])
        requisites["account"] = mask(requisites["account"])
        requisites["corr_account"] = mask(requisites["corr_account"])
        out["requisites"] = requisites
    return out


def select_transactions(product_id: str, date_from: str, date_to: str) -> list[dict[str, Any]]:
    return [
        tx
        for tx in TRANSACTIONS
        if tx["product_id"] == product_id and date_from <= tx["operation_date"] <= date_to
    ]


def find_product(product_id: str) -> dict[str, Any]:
    product = next((p for p in PRODUCTS if p["product_id"] == product_id), None)
    if product is None:
        raise HTTPException(status_code=404, detail="продукт не найден")
    return product


@app.get("/", include_in_schema=False)
def root(request: Request) -> Response:
    target = "/accounts" if is_logged_in(request) else "/login"
    return RedirectResponse(target, status_code=302)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, scenario: str = "default") -> Response:
    response = templates.TemplateResponse(request, "login.html", {"scenario": scenario})
    response.set_cookie(SCENARIO_COOKIE, scenario)
    return response


@app.post("/login")
def login_submit(username: str = Form(""), password: str = Form("")) -> Response:
    # Введённое не проверяется, не логируется и не хранится.
    del username, password
    token = secrets.token_urlsafe(16)
    SESSIONS.add(token)
    response = RedirectResponse("/accounts", status_code=302)
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")
    return response


@app.get("/logout")
def logout(request: Request) -> Response:
    SESSIONS.discard(request.cookies.get(SESSION_COOKIE, ""))
    response = RedirectResponse("/login", status_code=302)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/accounts", response_class=HTMLResponse)
def accounts_page(request: Request) -> Response:
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=302)

    # Список продуктов рисует сервер, а остатки догружает JS из /api/products —
    # как делают настоящие кабинеты. Поэтому DOM-канал всегда видит все продукты,
    # но при недоступном API остаётся без балансов, и это честная частичная выдача.
    listed = [public_product(product) for product in PRODUCTS]
    for item in listed:
        item.pop("balance", None)
        item.pop("available_balance", None)
    return templates.TemplateResponse(request, "accounts.html", {"products": listed})


@app.get("/accounts/{product_id}", response_class=HTMLResponse)
def product_page(
    request: Request, product_id: str, date_from: str = "", date_to: str = ""
) -> Response:
    if not is_logged_in(request):
        return RedirectResponse("/login", status_code=302)

    product = find_product(product_id)
    date_from = date_from or "1970-01-01"
    date_to = date_to or date.today().isoformat()
    rows = scenarios.apply_data_scenario(
        scenarios.current(request), product_id, select_transactions(product_id, date_from, date_to)
    )

    return templates.TemplateResponse(
        request,
        "product.html",
        {
            "product": public_product(product),
            "rows": rows[:PAGE_SIZE],
            "has_more": len(rows) > PAGE_SIZE,
            "date_from": date_from,
            "date_to": date_to,
        },
    )


@app.get("/api/products")
def api_products(request: Request) -> JSONResponse:
    require_login(request)
    return JSONResponse({"products": [public_product(product) for product in PRODUCTS]})


@app.get("/api/products/{product_id}/transactions")
def api_transactions(
    request: Request,
    product_id: str,
    date_from: str = "1970-01-01",
    date_to: str = "2100-01-01",
    cursor: int = 0,
) -> JSONResponse:
    require_login(request)
    rows = scenarios.apply_data_scenario(
        scenarios.current(request), product_id, select_transactions(product_id, date_from, date_to)
    )
    page = rows[cursor : cursor + PAGE_SIZE]
    next_cursor = cursor + PAGE_SIZE if cursor + PAGE_SIZE < len(rows) else None
    return JSONResponse({"items": page, "next_cursor": next_cursor})


@app.get("/export/transactions.csv")
def export_csv(
    request: Request,
    product_id: str,
    date_from: str = "1970-01-01",
    date_to: str = "2100-01-01",
) -> Response:
    require_login(request)
    rows = scenarios.apply_data_scenario(
        scenarios.current(request), product_id, select_transactions(product_id, date_from, date_to)
    )

    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "Дата операции",
            "Дата обработки",
            "Сумма",
            "Валюта",
            "Описание",
            "Контрагент",
            "Категория",
            "Статус",
        ]
    )
    for tx in rows:
        writer.writerow(
            [
                ru_date(tx["operation_date"]),
                ru_date(tx["posting_date"]) if tx["posting_date"] else "",
                ru_amount(tx["amount"]),
                tx["currency"],
                tx["description"],
                tx["counterparty"] or "",
                tx["category"] or "",
                ru_status(tx["status"]),
            ]
        )

    body = buffer.getvalue().encode("cp1251", errors="replace")
    return Response(
        content=body,
        media_type="text/csv; charset=windows-1251",
        headers={"content-disposition": 'attachment; filename="transactions.csv"'},
    )


def ru_date(value: str) -> str:
    parts = value.split("-")
    if len(parts) != 3:
        return value
    year, month, day = parts
    return f"{day}.{month}.{year}"


def ru_amount(value: str) -> str:
    if "." not in value:
        return value
    negative = value.startswith("-")
    whole, _, fraction = value.lstrip("-").partition(".")
    groups: list[str] = []
    while whole:
        groups.insert(0, whole[-3:])
        whole = whole[:-3]

    joined = " ".join(groups)
    return f"{'-' if negative else ''}{joined},{fraction}"


STATUS_RU = {
    "posted": "Проведена",
    "pending": "В обработке",
    "declined": "Отклонена",
    "hold": "Удержание",
}


def ru_status(status: str) -> str:
    return STATUS_RU.get(status, status)
