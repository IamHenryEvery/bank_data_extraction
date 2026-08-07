from collections.abc import Iterator

import pytest

from demo_bank.scenarios import reset_counters


@pytest.fixture(autouse=True)
def _clean_scenario_counters() -> Iterator[None]:
    # Счётчики стенда живут в памяти процесса — без сброса сценарии протекают.
    reset_counters()
    yield
    reset_counters()
