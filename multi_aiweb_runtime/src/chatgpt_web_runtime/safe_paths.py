from __future__ import annotations

import re

_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def validate_name(value: str, field_name: str, *, max_length: int = 127) -> str:
    text = str(value or "")
    if text in {"", ".", ".."} or len(text) > max_length or not _NAME_RE.fullmatch(text):
        raise ValueError(
            f"{field_name} must be a simple identifier using letters, digits, dot, underscore, or hyphen only"
        )
    return text
