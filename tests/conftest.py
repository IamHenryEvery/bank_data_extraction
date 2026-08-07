import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

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
