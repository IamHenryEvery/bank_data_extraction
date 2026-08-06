import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"

FORBIDDEN = re.compile(
    r"""(?ix)
    \.\s*(fill|type|press|set_input_files)\s*\(
    [^)]*
    (password|passwd|pwd|otp|sms|cvv|cvc|pin|login|credential)
    """
)


def test_no_credential_input_in_source():
    offenders = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path}:{number}: {line.strip()}")
    assert not offenders, "Найден ввод учётных данных:\n" + "\n".join(offenders)


def test_guard_actually_catches_violation():
    assert FORBIDDEN.search('page.fill("#password", secret)')
    assert FORBIDDEN.search("page.press('input[name=otp]', 'Enter')")
    assert not FORBIDDEN.search('page.fill("#date-from", "2026-01-01")')
