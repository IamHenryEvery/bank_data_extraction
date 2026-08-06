import pytest

from bank_extractor.masking import mask_account, mask_pan, mask_phone, redact_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("4276123456781234", "**** 1234"),
        ("4276 1234 5678 1234", "**** 1234"),
        ("4276-1234-5678-1234", "**** 1234"),
        ("**** 1234", "**** 1234"),
        ("•••• 1234", "**** 1234"),
    ],
)
def test_mask_pan(raw, expected):
    assert mask_pan(raw) == expected


def test_mask_pan_is_idempotent():
    assert mask_pan(mask_pan("4276123456781234")) == "**** 1234"


def test_mask_pan_rejects_too_short():
    with pytest.raises(ValueError):
        mask_pan("123")


def test_mask_account_keeps_last_four():
    assert mask_account("40817810099910004312") == "**** 4312"


def test_mask_phone_keeps_last_two():
    assert mask_phone("+7 (916) 123-45-67") == "+7 *** *** ** 67"


def test_redact_text_hides_pan_inside_sentence():
    text = "Списание по карте 4276123456781234 на сумму 100"
    result = redact_text(text)
    assert "4276123456781234" not in result
    assert "**** 1234" in result


def test_redact_text_hides_otp_near_keyword():
    assert "123456" not in redact_text("код подтверждения 123456")


def test_redact_text_keeps_amounts_intact():
    assert "1450.00" in redact_text("сумма 1450.00 RUB")
