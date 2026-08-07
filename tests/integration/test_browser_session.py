import subprocess
import time

import pytest
from playwright.sync_api import Page, sync_playwright

from bank_extractor.browser.attach import cdp_reachable
from bank_extractor.browser.session import open_session
from bank_extractor.config import SessionConfig, TimeoutConfig
from bank_extractor.errors import SessionError

pytestmark = pytest.mark.integration

TIMEOUTS = TimeoutConfig(navigation_s=20, selector_s=10)


def dashboard_visible(page: Page) -> bool:
    return page.locator('[data-testid="dashboard-title"]').count() > 0


def act_as_client_logging_in(page: Page) -> None:
    # Роль клиента играет тест: библиотека учётных данных не вводит нигде.
    page.get_by_test_id("login-input").fill("demo")
    page.get_by_test_id("password-input").fill("не-настоящий-пароль")
    page.get_by_test_id("login-submit").click()


def test_launch_mode_waits_for_client_authentication(demo_server, tmp_path):
    cfg = SessionConfig(
        mode="launch", headless=True, user_data_dir=tmp_path / "profile", auth_timeout_s=30
    )
    session = open_session(cfg, start_url=f"{demo_server}/login", timeouts=TIMEOUTS)
    try:
        assert session.mode_resolved == "launch"
        assert not dashboard_visible(session.page())

        act_as_client_logging_in(session.page())
        session.wait_for_authentication(dashboard_visible, timeout_s=30)

        assert dashboard_visible(session.page())
    finally:
        session.close()


def test_launch_mode_times_out_if_client_never_logs_in(demo_server, tmp_path):
    cfg = SessionConfig(
        mode="launch", headless=True, user_data_dir=tmp_path / "profile", auth_timeout_s=1
    )
    session = open_session(cfg, start_url=f"{demo_server}/login", timeouts=TIMEOUTS)
    try:
        with pytest.raises(SessionError, match="авторизац"):
            session.wait_for_authentication(dashboard_visible, timeout_s=1)
    finally:
        session.close()


def test_launch_mode_reuses_profile_between_runs(demo_server, tmp_path):
    profile = tmp_path / "profile"
    cfg = SessionConfig(mode="launch", headless=True, user_data_dir=profile, auth_timeout_s=30)

    first = open_session(cfg, start_url=f"{demo_server}/login", timeouts=TIMEOUTS)
    try:
        act_as_client_logging_in(first.page())
        first.wait_for_authentication(dashboard_visible, timeout_s=30)
    finally:
        first.close()

    second = open_session(cfg, start_url=f"{demo_server}/accounts", timeouts=TIMEOUTS)
    try:
        # Кука пережила перезапуск браузера.
        assert dashboard_visible(second.page())
    finally:
        second.close()


def start_client_browser(user_data_dir, port: int) -> subprocess.Popen[bytes]:
    # Браузер клиента поднимаем отдельным процессом: вложенный sync_playwright()
    # внутри уже работающего невозможен, и чужой процесс честнее моделирует attach.
    with sync_playwright() as p:
        executable = p.chromium.executable_path

    process = subprocess.Popen(
        [
            executable,
            "--headless=new",
            f"--remote-debugging-port={port}",
            f"--user-data-dir={user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    deadline = time.monotonic() + 20
    while not cdp_reachable(f"http://localhost:{port}"):
        if time.monotonic() > deadline or process.poll() is not None:
            process.kill()
            raise RuntimeError("браузер клиента не открыл отладочный порт")
        time.sleep(0.1)
    return process


def test_attach_mode_connects_to_running_browser(demo_server, tmp_path):
    port = 9333
    client = start_client_browser(tmp_path / "client-profile", port)
    try:
        cfg = SessionConfig(mode="attach", cdp_url=f"http://localhost:{port}")
        session = open_session(cfg, start_url=f"{demo_server}/login", timeouts=TIMEOUTS)
        try:
            assert session.mode_resolved == "attach"

            act_as_client_logging_in(session.page())
            session.wait_for_authentication(dashboard_visible, timeout_s=30)
            assert dashboard_visible(session.page())
        finally:
            session.close()

        # Браузер клиента остался жив: гасить его мы не имеем права.
        assert client.poll() is None
        assert cdp_reachable(f"http://localhost:{port}")
    finally:
        client.kill()
        client.wait(timeout=10)


def test_attach_mode_fails_clearly_when_nothing_listens(demo_server):
    cfg = SessionConfig(mode="attach", cdp_url="http://localhost:9444")
    with pytest.raises(SessionError, match="remote-debugging-port"):
        open_session(cfg, start_url=f"{demo_server}/accounts", timeouts=TIMEOUTS)


def test_auto_mode_falls_back_to_launch(demo_server, tmp_path):
    cfg = SessionConfig(
        mode="auto",
        cdp_url="http://localhost:9445",
        headless=True,
        user_data_dir=tmp_path / "profile",
    )
    session = open_session(cfg, start_url=f"{demo_server}/login", timeouts=TIMEOUTS)
    try:
        assert session.mode_resolved == "launch"
    finally:
        session.close()
