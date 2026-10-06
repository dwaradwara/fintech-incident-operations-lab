import re
from typing import Tuple


PATTERNS = [
    re.compile(
        r"(?i)(api[_-]?key|secret|password|token)\s*[:=]\s*[^\s,;]+"
    ),
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?"
        r"-----END [A-Z ]*PRIVATE KEY-----",
        re.DOTALL,
    ),
    re.compile(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
    ),
]


def redact_text(value: str) -> Tuple[str, int]:
    redactions = 0
    output = value

    for pattern in PATTERNS:
        output, count = pattern.subn("[REDACTED]", output)
        redactions += count

    return output, redactions
