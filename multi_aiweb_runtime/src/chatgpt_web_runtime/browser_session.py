from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BrowserSessionRequest:
    backend: str = "persistent_profile"
    profile_dir: Path | None = None
    cdp_url: str | None = None


@dataclass(frozen=True)
class BrowserSessionResult:
    ok: bool
    auth_state: str
    next_action: str
    message: str
    profile_dir: str | None = None
    chat_url: str = "https://chatgpt.com/"
