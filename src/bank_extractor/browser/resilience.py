import time
from collections.abc import Callable, Iterable

from loguru import logger
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from bank_extractor.errors import ChannelFailed

TRANSIENT: tuple[type[BaseException], ...] = (PlaywrightTimeoutError, PlaywrightError, TimeoutError)


def with_retries[T](
    operation: Callable[[], T],
    *,
    attempts: int,
    backoff_s: float,
    retry_on: Iterable[type[BaseException]] = TRANSIENT,
    description: str,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    retryable = tuple(retry_on)
    delay = backoff_s
    last: BaseException | None = None

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except retryable as exc:
            last = exc
            if attempt == attempts:
                break
            logger.bind(stage="retry").warning(
                "попытка {}/{} не удалась: {}", attempt, attempts, description
            )
            sleep(delay)
            delay *= 2

    raise ChannelFailed(f"{description}: исчерпаны попытки ({attempts}): {last}") from last
