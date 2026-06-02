from __future__ import annotations

import re

_SECRET_PATTERNS = [
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)([\s:=]+)([^\s,}]+)"),
]


def redact(text: str) -> str:
    value = str(text)
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.startswith("(?i)(bearer"):
            value = pattern.sub(lambda match: f"{match.group(1)}<redacted>", value)
        else:
            value = pattern.sub(lambda match: f"{match.group(1)}{match.group(2)}<redacted>", value)
    return value
