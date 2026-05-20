from __future__ import annotations

import re

_SECRET_PATTERNS = [
    re.compile(r"(password=)[^\s&]+", re.IGNORECASE),
    re.compile(r"(token=)[^\s&]+", re.IGNORECASE),
    re.compile(r"(Authorization:\s*Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.IGNORECASE),
]


def safe_error(message: str) -> str:
    """Remove credential-looking values from messages before they reach Claude."""
    cleaned = message or "Unexpected Spendee error"
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.startswith("Bearer"):
            cleaned = pattern.sub("Bearer [redacted]", cleaned)
        else:
            cleaned = pattern.sub(r"\1[redacted]", cleaned)
    return cleaned
