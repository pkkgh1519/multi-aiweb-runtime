from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DEFAULT_CAPABILITIES_VERSION = "2026-05-31"
CHATGPT_BROWSER_TARGET = "chatgpt_browser"
GEMINI_BROWSER_TARGET = "gemini_browser"
DEFAULT_GEMINI_BROWSER_MODEL = "gemini-3.1-pro"

BlockedReason = Literal["retired", "experimental_unproven"]


@dataclass(frozen=True)
class GeminiBrowserCapabilities:
    default_model: str = DEFAULT_GEMINI_BROWSER_MODEL
    models: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "gemini-3.1-pro",
                "gemini-3.5-flash",
                "gemini-3.1-flash-lite",
            }
        )
    )
    aliases: dict[str, str] = field(default_factory=lambda: {"gemini": DEFAULT_GEMINI_BROWSER_MODEL})
    blocked_models: dict[str, BlockedReason] = field(
        default_factory=lambda: {
            "gemini-3-pro": "retired",
            "gemini-3-pro-deep-think": "retired",
            "gemini-3-deep-think": "retired",
            "gemini-2.5-pro": "retired",
            "gemini-2.5-flash": "retired",
        }
    )


GEMINI_BROWSER_CAPABILITIES = GeminiBrowserCapabilities()


def gemini_browser_models() -> frozenset[str]:
    return frozenset(GEMINI_BROWSER_CAPABILITIES.models | frozenset(GEMINI_BROWSER_CAPABILITIES.aliases))


def blocked_gemini_browser_models() -> dict[str, BlockedReason]:
    return dict(GEMINI_BROWSER_CAPABILITIES.blocked_models)


def resolve_gemini_browser_model(model: str | None) -> str:
    normalized = _normalize_model_name(model) or GEMINI_BROWSER_CAPABILITIES.default_model
    resolved = GEMINI_BROWSER_CAPABILITIES.aliases.get(normalized, normalized)
    blocked_reason = GEMINI_BROWSER_CAPABILITIES.blocked_models.get(resolved) or GEMINI_BROWSER_CAPABILITIES.blocked_models.get(normalized)
    if blocked_reason == "retired":
        allowed = ", ".join(sorted(gemini_browser_models()))
        raise ValueError(f"{normalized} is not in the current Gemini Web picker. Allowed models: {allowed}")
    if blocked_reason == "experimental_unproven":
        raise ValueError(
            f"{normalized} is not proven for Gemini browser mode yet. "
            "A Web model header/resolver and browser-only live smoke are required first."
        )
    if resolved not in GEMINI_BROWSER_CAPABILITIES.models:
        allowed = ", ".join(sorted(gemini_browser_models()))
        raise ValueError(f"Unsupported Gemini browser model: {normalized}. Allowed models: {allowed}")
    return resolved


def _normalize_model_name(model: str | None) -> str | None:
    if model is None:
        return None
    normalized = str(model).strip().lower().replace("_", "-").replace(" ", "-")
    return normalized or None
