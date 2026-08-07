import time
from collections.abc import Callable

from loguru import logger
from playwright.sync_api import Browser, BrowserContext, Page, Playwright, sync_playwright

from bank_extractor.browser.attach import attach_to_running_browser, cdp_reachable
from bank_extractor.browser.launch import launch_own_browser
from bank_extractor.config import SessionConfig, TimeoutConfig
from bank_extractor.errors import SessionError

AuthCheck = Callable[[Page], bool]


class BrowserSession:
    def __init__(
        self,
        playwright: Playwright,
        context: BrowserContext,
        page: Page,
        *,
        mode_resolved: str,
        owns_browser: bool,
        browser: Browser | None = None,
    ) -> None:
        self._playwright = playwright
        self._context = context
        self._page = page
        self._browser = browser
        self._owns_browser = owns_browser
        self.mode_resolved = mode_resolved

    def page(self) -> Page:
        return self._page

    def context(self) -> BrowserContext:
        return self._context

    def wait_for_authentication(self, is_authenticated: AuthCheck, timeout_s: int) -> None:
        # Ждём, пока клиент сам завершит вход. Ничего не вводим и не читаем из форм.
        deadline = time.monotonic() + timeout_s
        logger.bind(stage="auth").info("ожидаем авторизацию клиента")

        while time.monotonic() < deadline:
            if is_authenticated(self._page):
                logger.bind(stage="auth").info("клиент авторизовался")
                return
            self._page.wait_for_timeout(500)

        raise SessionError(
            f"клиент не завершил авторизацию за {timeout_s} с — извлечение не начато"
        )

    def close(self) -> None:
        try:
            if self._owns_browser:
                self._context.close()
            if self._browser is not None:
                self._browser.close()
        finally:
            self._playwright.stop()


def open_session(cfg: SessionConfig, *, start_url: str, timeouts: TimeoutConfig) -> BrowserSession:
    playwright = sync_playwright().start()
    try:
        mode = cfg.mode
        if mode == "auto":
            mode = "attach" if cdp_reachable(cfg.cdp_url) else "launch"
            logger.bind(stage="session").info("режим auto выбрал {}", mode)

        if mode == "attach":
            context, page, browser = attach_to_running_browser(playwright, cfg, start_url, timeouts)
            return BrowserSession(
                playwright,
                context,
                page,
                mode_resolved="attach",
                owns_browser=False,
                browser=browser,
            )

        context, page = launch_own_browser(playwright, cfg, start_url, timeouts)
        return BrowserSession(playwright, context, page, mode_resolved="launch", owns_browser=True)
    except Exception:
        playwright.stop()
        raise
