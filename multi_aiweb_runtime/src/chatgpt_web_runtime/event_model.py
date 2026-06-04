from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from .redaction import redact, redact_nested

VALID_STATUSES = {
    "idle",
    "draft",
    "thinking",
    "streaming",
    "done",
    "error",
    "unknown",
    "watch_lost",
    "preview",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_hash(value: Any) -> str:
    """Small deterministic FNV-1a hash compatible with WebLatch-style matching."""
    text = str(value or "")
    h = 2166136261
    for char in text:
        h ^= ord(char)
        h = (h * 16777619) & 0xFFFFFFFF
    return format(h, "x")


def normalize_status(value: str | None) -> str:
    status = str(value or "unknown").lower()
    return status if status in VALID_STATUSES else "unknown"


@dataclass(slots=True)
class RuntimeEvent:
    event_id: int
    run_id: str
    status: str
    user_text: str = ""
    assistant_text: str = ""
    url: str = ""
    title: str = ""
    conversation_id: str = ""
    tab_id: str | int | None = None
    page_session_id: str = ""
    model_label: str = ""
    error_text: str = ""
    observed_at: str = field(default_factory=utc_now_iso)
    signals: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.status = normalize_status(self.status)
        if self.tab_id is not None:
            self.tab_id = str(self.tab_id)

    @property
    def user_text_hash(self) -> str:
        return stable_hash(self.user_text)

    @property
    def assistant_text_hash(self) -> str:
        return stable_hash(self.assistant_text)

    def to_dict(self) -> dict[str, Any]:
        return {
            "eventId": self.event_id,
            "runId": self.run_id,
            "status": self.status,
            "url": redact(self.url),
            "title": redact(self.title),
            "conversationId": redact(self.conversation_id),
            "tabId": self.tab_id,
            "pageSessionId": redact(self.page_session_id),
            "userText": redact(self.user_text),
            "assistantText": redact(self.assistant_text),
            "userTextHash": self.user_text_hash,
            "assistantTextHash": self.assistant_text_hash,
            "modelLabel": redact(self.model_label),
            "errorText": redact(self.error_text),
            "observedAt": self.observed_at,
            "signals": redact_nested(self.signals or {}),
        }


def event_matches(
    event: RuntimeEvent,
    *,
    status: str | None = None,
    after_id: int | None = None,
    user_text: str | None = None,
    user_text_hash: str | None = None,
    conversation_id: str | None = None,
    tab_id: str | int | None = None,
    page_session_id: str | None = None,
) -> bool:
    if status and event.status != normalize_status(status):
        return False
    if after_id is not None and event.event_id <= int(after_id):
        return False
    expected_hash = user_text_hash or (stable_hash(user_text) if user_text is not None else None)
    if expected_hash and event.user_text_hash != expected_hash:
        return False
    if conversation_id and event.conversation_id != conversation_id:
        return False
    if tab_id is not None and str(event.tab_id) != str(tab_id):
        return False
    if page_session_id and event.page_session_id != page_session_id:
        return False
    return True
