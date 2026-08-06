import re

_DIGITS = re.compile(r"\D")
_PAN_IN_TEXT = re.compile(r"\b(?:\d[ -]?){12,18}\d\b")
_OTP_NEAR_KEYWORD = re.compile(r"(?i)\b(код|пароль|otp|cvv|cvc|пин|pin)\b\D{0,20}\d{3,8}")


def _last_digits(value: str, count: int) -> str:
    digits = _DIGITS.sub("", value)
    if len(digits) < count:
        raise ValueError("значение слишком короткое для маскирования")
    return digits[-count:]


def mask_pan(value: str) -> str:
    return f"**** {_last_digits(value, 4)}"


def mask_account(value: str) -> str:
    return f"**** {_last_digits(value, 4)}"


def mask_phone(value: str) -> str:
    return f"+7 *** *** ** {_last_digits(value, 2)}"


def _redact_otp(match: re.Match[str]) -> str:
    return re.sub(r"\d{3,8}$", "****", match.group(0))


def redact_text(text: str) -> str:
    text = _OTP_NEAR_KEYWORD.sub(_redact_otp, text)
    return _PAN_IN_TEXT.sub(lambda match: mask_pan(match.group(0)), text)
