import pytest

from bank_extractor.browser.resilience import with_retries
from bank_extractor.errors import ChannelFailed


def test_returns_value_without_retry():
    calls = []

    def once():
        calls.append(1)
        return "ok"

    result = with_retries(
        once,
        attempts=3,
        backoff_s=0,
        retry_on=(ValueError,),
        description="test",
        sleep=lambda _: None,
    )
    assert result == "ok"
    assert len(calls) == 1


def test_retries_until_success():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise ValueError("ещё нет")
        return "ok"

    result = with_retries(
        flaky,
        attempts=3,
        backoff_s=0,
        retry_on=(ValueError,),
        description="test",
        sleep=lambda _: None,
    )
    assert result == "ok"
    assert len(calls) == 3


def test_gives_up_after_attempts_and_wraps_error():
    def always_fails():
        raise ValueError("никогда")

    with pytest.raises(ChannelFailed, match="test"):
        with_retries(
            always_fails,
            attempts=2,
            backoff_s=0,
            retry_on=(ValueError,),
            description="test",
            sleep=lambda _: None,
        )


def test_does_not_retry_unlisted_exception():
    calls = []

    def wrong_error():
        calls.append(1)
        raise KeyError("не транзиентная")

    with pytest.raises(KeyError):
        with_retries(
            wrong_error,
            attempts=3,
            backoff_s=0,
            retry_on=(ValueError,),
            description="test",
            sleep=lambda _: None,
        )
    assert len(calls) == 1


def test_backoff_grows_exponentially():
    delays = []

    def always_fails():
        raise ValueError("x")

    with pytest.raises(ChannelFailed):
        with_retries(
            always_fails,
            attempts=4,
            backoff_s=1.0,
            retry_on=(ValueError,),
            description="test",
            sleep=delays.append,
        )
    assert delays == [1.0, 2.0, 4.0]
