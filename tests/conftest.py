import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn
from playwright.sync_api import Page, sync_playwright

from demo_bank.scenarios import reset_counters
from demo_bank.server import app


@pytest.fixture(autouse=True)
def _clean_scenario_counters() -> Iterator[None]:
    # Счётчики стенда живут в памяти процесса — без сброса сценарии протекают.
    reset_counters()
    yield
    reset_counters()


@pytest.fixture(scope="session")
def demo_server() -> Iterator[str]:
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("демо-банк не поднялся за 10 секунд")
        time.sleep(0.05)

    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def _open_logged_in_page(base_url: str, scenario: str) -> Iterator[Page]:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{base_url}/login?scenario={scenario}")
        page.get_by_test_id("login-input").fill("demo")
        page.get_by_test_id("password-input").fill("не-настоящий-пароль")
        page.get_by_test_id("login-submit").click()
        page.wait_for_selector('[data-testid="dashboard-title"]')
        try:
            yield page
        finally:
            browser.close()


@pytest.fixture
def authenticated_page(demo_server: str) -> Iterator[Page]:
    yield from _open_logged_in_page(demo_server, "default")


@pytest.fixture
def scenario_page(demo_server: str, request: pytest.FixtureRequest) -> Iterator[Page]:
    marker = request.node.get_closest_marker("scenario")
    scenario = marker.args[0] if marker else "default"
    yield from _open_logged_in_page(demo_server, scenario)
