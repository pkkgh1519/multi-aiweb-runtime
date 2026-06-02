from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def status_is_terminal(status: str) -> bool:
    return status in {
        "completed",
        "failed",
        "cancelled",
        "user_action_required",
        "timeout",
        "watch_lost",
        "policy_preview",
        "policy_blocked",
    }
