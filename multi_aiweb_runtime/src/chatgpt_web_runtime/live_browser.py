from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .browser_session import BrowserSessionResult
from .completion_cdp import CDP_OBSERVER_SCRIPT
from .event_model import RuntimeEvent
from .redaction import redact


@dataclass(frozen=True)
class PageSnapshot:
    url: str = ""
    title: str = ""
    text: str = ""
    user_text: str = ""
    assistant_text: str = ""
    composer_present: bool = False
    stop_visible: bool = False
    assistant_action_visible: bool = False
    conversation_id: str = ""
    tab_id: str | None = None
    page_session_id: str = ""
    model_label: str = ""
    error_text: str = ""
    signals: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LiveRunResult:
    status: str
    response_text: str = ""
    events: list[RuntimeEvent] = field(default_factory=list)
    message: str = ""
    error_text: str = ""


class LiveBrowserBackend(Protocol):
    def prepare_session(self, *, profile_dir: Path, chat_url: str, open_browser: bool = False) -> BrowserSessionResult:
        ...

    def run_prompt(self, *, run_id: str, prompt: str, timeout_seconds: int) -> LiveRunResult:
        ...


_LOGIN_PATTERNS = [
    re.compile(r"\blog\s*in\b", re.I),
    re.compile(r"\bsign\s*up\b", re.I),
    re.compile(r"로그인"),
]
_CAPTCHA_PATTERNS = [
    re.compile(r"captcha", re.I),
    re.compile(r"verify\s+you\s+are\s+human", re.I),
    re.compile(r"사람인지\s*확인"),
]
_PAYMENT_PATTERNS = [
    re.compile(r"upgrade\s+your\s+plan", re.I),
    re.compile(r"usage\s+limit", re.I),
    re.compile(r"결제|업그레이드|사용량\s*한도"),
]


def _contains_any(text: str, patterns: list[re.Pattern[str]]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _compact_text(value: str | None) -> str:
    return " ".join(str(value or "").split())


def classify_auth_state(snapshot: PageSnapshot) -> BrowserSessionResult:
    combined = "\n".join([snapshot.url, snapshot.title, snapshot.text, snapshot.error_text])
    lower_url = snapshot.url.lower()
    if snapshot.composer_present:
        return BrowserSessionResult(True, "ready", "continue", "ChatGPT composer is available.")
    if _contains_any(combined, _CAPTCHA_PATTERNS):
        return BrowserSessionResult(False, "captcha_required", "user_solve_captcha", "ChatGPT requires a human verification step.")
    if _contains_any(combined, _PAYMENT_PATTERNS):
        return BrowserSessionResult(False, "payment_required", "user_upgrade_or_change_model", "ChatGPT reported a payment or usage-limit gate.")
    if "auth/login" in lower_url or "login" in lower_url or _contains_any(combined, _LOGIN_PATTERNS):
        return BrowserSessionResult(False, "login_required", "user_login", "ChatGPT login is required in this browser profile.")
    return BrowserSessionResult(False, "unknown", "inspect_browser", "Could not determine ChatGPT session state.")


def completion_event_from_snapshot(
    snapshot: PageSnapshot,
    *,
    run_id: str,
    event_id: int,
    expected_user_text: str | None = None,
    baseline_assistant_text: str | None = None,
) -> RuntimeEvent:
    expected = _compact_text(expected_user_text)
    actual = _compact_text(snapshot.user_text)
    baseline_assistant = _compact_text(baseline_assistant_text)
    current_assistant = _compact_text(snapshot.assistant_text)
    if expected and actual != expected and (actual or snapshot.assistant_text):
        status = "watch_lost"
    elif snapshot.error_text:
        status = "error"
    elif baseline_assistant and current_assistant == baseline_assistant:
        status = "thinking" if expected and actual == expected else "idle"
    elif snapshot.assistant_text and not snapshot.stop_visible and snapshot.assistant_action_visible:
        status = "done"
    elif snapshot.assistant_text:
        status = "streaming"
    elif snapshot.user_text:
        status = "thinking"
    else:
        status = "idle"
    return RuntimeEvent(
        event_id=event_id,
        run_id=run_id,
        status=status,
        user_text=snapshot.user_text,
        assistant_text=snapshot.assistant_text,
        url=snapshot.url,
        title=snapshot.title,
        conversation_id=snapshot.conversation_id,
        tab_id=snapshot.tab_id,
        page_session_id=snapshot.page_session_id,
        model_label=snapshot.model_label,
        error_text=redact(snapshot.error_text),
        signals=snapshot.signals,
    )


class PlaywrightChatGptBackend:
    """Optional Playwright-backed ChatGPT Web adapter.

    The module imports Playwright only inside methods so dry-run/test environments do not
    require browser dependencies. Login remains user-mediated through a persistent profile.
    """

    def __init__(self, *, profile_dir: Path, chat_url: str = "https://chatgpt.com/", headless: bool = True) -> None:
        self.profile_dir = profile_dir
        self.chat_url = chat_url
        self.headless = headless
        self._playwright: Any | None = None
        self._context: Any | None = None
        self._page: Any | None = None

    def prepare_session(self, *, profile_dir: Path | None = None, chat_url: str | None = None, open_browser: bool = False) -> BrowserSessionResult:
        self.profile_dir = profile_dir or self.profile_dir
        self.chat_url = chat_url or self.chat_url
        try:
            return self._with_page(lambda page: classify_auth_state(self._snapshot(page)), open_browser=open_browser)
        except ModuleNotFoundError:
            return BrowserSessionResult(
                False,
                "user_action_required",
                "install_browser_backend",
                "Install the optional browser backend with: python -m pip install -e .[browser] && playwright install chromium",
                profile_dir=str(self.profile_dir),
                chat_url=self.chat_url,
            )
        except Exception as exc:  # noqa: BLE001 - keep browser errors contained and redacted
            return BrowserSessionResult(
                False,
                "unknown",
                "inspect_browser",
                f"Browser session check failed: {redact(str(exc))}",
                profile_dir=str(self.profile_dir),
                chat_url=self.chat_url,
            )

    def run_prompt(self, *, run_id: str, prompt: str, timeout_seconds: int) -> LiveRunResult:
        try:
            return self._with_page(lambda page: self._run_prompt_on_page(page, run_id, prompt, timeout_seconds), open_browser=False)
        except ModuleNotFoundError:
            return LiveRunResult(
                status="error",
                message="Install the optional browser backend with: python -m pip install -e .[browser] && playwright install chromium",
            )
        except Exception as exc:  # noqa: BLE001 - browser automation errors must not crash MCP server
            return LiveRunResult(status="error", message="Browser run failed.", error_text=redact(str(exc)))

    def _start_playwright(self) -> Any:
        from playwright.sync_api import sync_playwright

        return sync_playwright().start()

    def _with_page(self, callback: Callable[[Any], Any], *, open_browser: bool) -> Any:
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        if self._context is not None:
            page = self._page or (self._context.pages[0] if self._context.pages else self._context.new_page())
            self._page = page
            if not getattr(page, "url", "") or getattr(page, "url", "") == "about:blank":
                page.goto(self.chat_url, wait_until="domcontentloaded")
            return callback(page)

        playwright = self._start_playwright()
        context = None
        keep_open = False
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(self.profile_dir),
                headless=self.headless and not open_browser,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(self.chat_url, wait_until="domcontentloaded")
            result = callback(page)
            keep_open = bool(open_browser)
            if keep_open:
                self._playwright = playwright
                self._context = context
                self._page = page
            return result
        finally:
            if not keep_open:
                if context is not None:
                    context.close()
                playwright.stop()

    def _snapshot(self, page) -> PageSnapshot:
        page.evaluate(CDP_OBSERVER_SCRIPT)
        observer = page.evaluate("window.__chatgptWebRuntimeObserver && window.__chatgptWebRuntimeObserver.snapshot && window.__chatgptWebRuntimeObserver.snapshot()") or {}
        body_text = self._safe_inner_text(page, "body")
        composer_present = self._locator_count(page, '#prompt-textarea, textarea, div[contenteditable="true"]') > 0
        stop_visible = bool(observer.get("stopVisible")) or self._visible_by_text(page, ["Stop", "중지"])
        action_visible = bool(observer.get("actionVisible")) or self._visible_by_text(page, ["Copy", "Regenerate", "복사", "다시"])
        return PageSnapshot(
            url=getattr(page, "url", ""),
            title=page.title(),
            text=body_text,
            user_text=str(observer.get("userText") or ""),
            assistant_text=str(observer.get("assistantText") or ""),
            composer_present=composer_present,
            stop_visible=stop_visible,
            assistant_action_visible=action_visible,
            signals={"observer": observer},
        )

    def _run_prompt_on_page(self, page, run_id: str, prompt: str, timeout_seconds: int) -> LiveRunResult:
        initial_snapshot = self._snapshot(page)
        initial_state = classify_auth_state(initial_snapshot)
        if not initial_state.ok:
            return LiveRunResult(status=initial_state.auth_state, message=initial_state.message)
        baseline_assistant_text = initial_snapshot.assistant_text
        self._submit_prompt(page, prompt)
        events: list[RuntimeEvent] = []
        deadline = time.time() + max(timeout_seconds, 1)
        event_id = 0
        while time.time() < deadline:
            event_id += 1
            snapshot = self._snapshot(page)
            event = completion_event_from_snapshot(
                snapshot,
                run_id=run_id,
                event_id=event_id,
                expected_user_text=prompt,
                baseline_assistant_text=baseline_assistant_text,
            )
            events.append(event)
            if event.status == "done":
                return LiveRunResult(status="done", response_text=event.assistant_text, events=events, message="Completed.")
            if event.status == "error":
                return LiveRunResult(status="error", response_text=event.assistant_text, events=events, message="ChatGPT Web reported an error.", error_text=event.error_text)
            time.sleep(0.5)
        if events and events[-1].status == "watch_lost":
            return LiveRunResult(
                status="watch_lost",
                events=events,
                message="Could not correlate ChatGPT Web completion to the submitted prompt.",
            )
        return LiveRunResult(status="timeout", events=events, message="Timed out waiting for ChatGPT Web completion.")

    def _submit_prompt(self, page, prompt: str) -> None:
        selectors = ['#prompt-textarea', 'textarea', 'div[contenteditable="true"]']
        for selector in selectors:
            locator = page.locator(selector).first
            if locator.count() > 0:
                try:
                    locator.fill(prompt)
                except Exception:  # noqa: BLE001 - contenteditable often does not support fill
                    locator.click()
                    page.keyboard.insert_text(prompt)
                break
        else:
            raise RuntimeError("ChatGPT composer was not found.")
        send_selectors = ['button[data-testid="send-button"]', 'button[aria-label*="Send"]', 'button:has-text("Send")']
        for selector in send_selectors:
            locator = page.locator(selector).first
            if locator.count() > 0:
                locator.click()
                return
        page.keyboard.press("Enter")

    @staticmethod
    def _safe_inner_text(page, selector: str) -> str:
        try:
            return page.locator(selector).first.inner_text(timeout=1000)
        except Exception:  # noqa: BLE001
            return ""

    @staticmethod
    def _locator_count(page, selector: str) -> int:
        try:
            return page.locator(selector).count()
        except Exception:  # noqa: BLE001
            return 0

    @staticmethod
    def _visible_by_text(page, labels: list[str]) -> bool:
        for label in labels:
            try:
                if page.get_by_text(label, exact=False).first.is_visible(timeout=250):
                    return True
            except Exception:  # noqa: BLE001
                continue
        return False
