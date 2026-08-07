import pytest

from bank_extractor.adapters.registry import get_adapter, known_banks
from bank_extractor.enums import Channel


def test_demo_bank_is_registered():
    assert get_adapter("demo_bank").name == "demo_bank"


def test_channel_priority_puts_api_first_and_dom_last():
    adapter = get_adapter("demo_bank")
    assert adapter.transaction_channels == (Channel.API, Channel.EXPORT, Channel.DOM)
    assert adapter.product_channels == (Channel.API, Channel.DOM)


def test_unknown_bank_raises_listing_known_ones():
    with pytest.raises(KeyError, match="demo_bank"):
        get_adapter("sberbank")


def test_known_banks_lists_demo_bank():
    assert "demo_bank" in known_banks()
