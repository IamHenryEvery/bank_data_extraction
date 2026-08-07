import urllib.error
import urllib.request
from urllib.parse import urlparse

from loguru import logger
from playwright.sync_api import Browser, BrowserContext, Page, Playwright

from bank_extractor.config import SessionConfig, TimeoutConfig
from bank_extractor.errors import SessionError


def cdp_reachable(cdp_url: str, timeout_s: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(f"{cdp_url.rstrip('/')}/json/version", timeout=timeout_s):
            return True
    except (urllib.error.URLError, OSError):
        return False


def attach_to_running_browser(
    playwright: Playwright, cfg: SessionConfig, start_url: str, timeouts: TimeoutConfig
) -> tuple[BrowserContext, Page, Browser]:
    try:
        browser = playwright.chromium.connect_over_cdp(cfg.cdp_url)
    except Exception as exc:
        raise SessionError(
            f"не удалось подключиться к браузеру по {cfg.cdp_url}. "
            "Браузер должен быть запущен с флагом --remote-debugging-port, например: "
            "google-chrome --remote-debugging-port=9222"
        ) from exc

    if not browser.contexts:
        raise SessionError("в подключённом браузере нет ни одного контекста")

    context = browser.contexts[0]
    context.set_default_timeout(timeouts.selector_s * 1000)
    context.set_default_navigation_timeout(timeouts.navigation_s * 1000)

    page = _find_bank_tab(context, urlparse(start_url).netloc)

    if page is None:
        logger.bind(stage="session").info("вкладка банка не найдена, открываем новую")
        page = context.new_page()
        page.goto(start_url)
    else:
        logger.bind(stage="session").info("подключились к открытой вкладке банка")
        page.bring_to_front()

    return context, page, browser


def _find_bank_tab(context: BrowserContext, host: str) -> Page | None:
    for page in context.pages:
        if urlparse(page.url).netloc == host:
            return page
    return None
