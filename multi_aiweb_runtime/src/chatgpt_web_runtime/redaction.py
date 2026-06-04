from __future__ import annotations

import re
from typing import Any

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]{16,}"),
    re.compile(
        r"(?i)((?:api[_-]?key|(?:auth[_-]?)?token|access[_-]?token|refresh[_-]?token|id[_-]?token|session[_-]?token|secret|password)\s*[=:]\s*)['\"]?[A-Za-z0-9._~+/=-]{8,}['\"]?"
    ),
    re.compile(r"(?i)(\"(?:access_token|refresh_token|id_token|session_token)\"\s*:\s*\")[^\"]{8,}(\")"),
    re.compile(r"(?i)(cookie\s*:\s*)[^\r\n]{8,}"),
    re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
)


def redact(text: str | None) -> str:
    if not text:
        return ""
    value = str(text)
    for pattern in _SECRET_PATTERNS:
        value = pattern.sub(_replace_secret_match, value)
    return value


def contains_secret_risk(value: Any) -> bool:
    if value is None:
        return False
    text = str(value)
    return any(pattern.search(text) for pattern in _SECRET_PATTERNS)


def redact_nested(value: Any) -> Any:
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {redact(str(key)): redact_nested(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_nested(item) for item in value]
    if isinstance(value, tuple):
        return [redact_nested(item) for item in value]
    return value


def _replace_secret_match(match: re.Match[str]) -> str:
    groups = match.groups()
    if len(groups) == 2 and groups[1] == '"':
        return f"{groups[0]}[REDACTED_SECRET]{groups[1]}"
    if groups:
        return f"{groups[0]}[REDACTED_SECRET]"
    return "[REDACTED_SECRET]"
