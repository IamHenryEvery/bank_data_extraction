from loguru import logger
from playwright.sync_api import BrowserContext, Page, Playwright

from bank_extractor.config import SessionConfig, TimeoutConfig
from bank_extractor.errors import SessionError


def launch_own_browser(
    playwright: Playwright, cfg: SessionConfig, start_url: str, timeouts: TimeoutConfig
) -> tuple[BrowserContext, Page]:
    cfg.user_data_dir.mkdir(parents=True, exist_ok=True)

    try:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(cfg.user_data_dir),
            headless=cfg.headless,
        )
    except Exception as exc:
        raise SessionError(f"не удалось запустить браузер: {exc}") from exc

    context.set_default_timeout(timeouts.selector_s * 1000)
    context.set_default_navigation_timeout(timeouts.navigation_s * 1000)

    page = context.pages[0] if context.pages else context.new_page()
    page.goto(start_url)
    logger.bind(stage="session").info("браузер запущен, открыта страница банка")
    return context, page
