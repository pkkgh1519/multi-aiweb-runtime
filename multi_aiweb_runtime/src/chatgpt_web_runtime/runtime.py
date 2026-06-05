from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .artifacts import RunArtifacts, atomic_write_json, atomic_write_text, make_run_id
from .config import RuntimeConfig
from .event_model import RuntimeEvent
from .live_browser import LiveBrowserBackend, LiveRunResult, PlaywrightChatGptBackend
from .oracle_adapter import OracleAdapter
from .oracle_client import (
    DEFAULT_ORACLE_TARGET,
    OracleClient,
    normalize_oracle_target,
    oracle_target_chat_url,
    oracle_target_home_dir,
    oracle_target_profile_dir,
    oracle_target_provider,
    resolve_oracle_model,
    resolve_oracle_thinking_time,
)
from .redaction import redact, redact_nested
from .safe_paths import validate_name
from .state import read_json, status_is_terminal

PLAYWRIGHT_MCP_BACKEND = "playwright_mcp"
ORACLE_BACKEND = "oracle"
DIRECT_BROWSER_BACKENDS = {"persistent_profile", "python_playwright"}
DEFAULT_MODE_LABEL = "Extension Heavy"
PRO_EXTENDED_MODE_LABEL = "Pro Extended"
USER_ACTION_FAILURE_STATUSES = {"login_required", "captcha_required", "payment_required", "user_action_required"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ChatGptWebRuntime:
    def __init__(
        self,
        state_root: str | Path | None = None,
        config: RuntimeConfig | None = None,
        live_backend: LiveBrowserBackend | None = None,
        oracle_adapter: OracleAdapter | None = None,
    ) -> None:
        self.config = config or RuntimeConfig.from_env(state_root)
        self.live_backend = live_backend
        self.oracle_adapter = oracle_adapter
        self._live_backend_cache: dict[str, LiveBrowserBackend] = {}
        self.config.runs_dir.mkdir(parents=True, exist_ok=True)
        self.config.profiles_dir.mkdir(parents=True, exist_ok=True)

    def _run_dir(self, run_id: str) -> Path:
        return self.config.runs_dir / validate_name(run_id, "run_id")

    def _artifacts(self, run_id: str) -> RunArtifacts:
        return RunArtifacts(self._run_dir(run_id))

    def _create_live_backend(self, profile_name: str | None = None) -> LiveBrowserBackend:
        return PlaywrightChatGptBackend(profile_dir=self.config.profile_dir(profile_name), chat_url=self.config.chat_url)

    def _live_backend_cache_key(self, profile_name: str | None = None) -> str:
        return validate_name(profile_name or self.config.default_profile_name, "profile_name")

    def _resolve_live_backend(self, profile_name: str | None = None) -> LiveBrowserBackend:
        if self.live_backend is not None:
            return self.live_backend
        cache_key = self._live_backend_cache_key(profile_name)
        if cache_key not in self._live_backend_cache:
            self._live_backend_cache[cache_key] = self._create_live_backend(cache_key)
        return self._live_backend_cache[cache_key]

    def _resolve_oracle_adapter(self) -> OracleAdapter:
        if self.oracle_adapter is None:
            self.oracle_adapter = OracleAdapter(
                client=OracleClient(
                    command=self.config.oracle_command,
                    oracle_home_dir=self.config.oracle_home_dir or (self.config.state_root / "oracle"),
                )
            )
        return self.oracle_adapter

    @staticmethod
    def _validate_browser_backend(browser_backend: str) -> str:
        backend = str(browser_backend or PLAYWRIGHT_MCP_BACKEND)
        if backend == PLAYWRIGHT_MCP_BACKEND or backend == ORACLE_BACKEND or backend in DIRECT_BROWSER_BACKENDS:
            return backend
        raise ValueError(f"Unsupported browser_backend: {browser_backend}")

    @staticmethod
    def _redact_nested(value: Any) -> Any:
        return redact_nested(value)

    @staticmethod
    def _prompt_hash(question: str) -> str:
        return hashlib.sha256(question.encode("utf-8")).hexdigest()

    def _assert_run_not_terminal(self, artifacts: RunArtifacts) -> None:
        if not artifacts.status_json.exists():
            return
        status_payload = read_json(artifacts.status_json)
        status = str(status_payload.get("status") or "")
        if status_is_terminal(status) and not self._status_payload_recoverable(status_payload):
            raise ValueError(f"Cannot update terminal run status: {status}")

    @staticmethod
    def _status_payload_recoverable(status_payload: dict[str, Any]) -> bool:
        status = str(status_payload.get("status") or "")
        phase = str(status_payload.get("phase") or "")
        if status == "running":
            return True
        return phase in {
            "PROFILE_BUSY",
            "LOGIN_REQUIRED",
            "MODEL_SELECTOR_UNAVAILABLE",
            "PRO_NOT_AVAILABLE",
            "PRO_EFFORT_UNCONFIRMED",
            "PROMPT_NOT_SUBMITTED",
            "CHROME_NOT_FOUND",
            "LONG_THINKING_IN_PROGRESS",
            "REATTACH_REQUIRED",
            "CAPTURE_INCOMPLETE",
            "USER_ACTION_REQUIRED",
        }

    def _external_playwright_action_plan(
        self,
        *,
        run_id: str | None = None,
        prompt: str = "",
        profile_name: str | None = None,
        oracle_target: str = DEFAULT_ORACLE_TARGET,
        oracle_model: str | None = None,
        mode_label: str = DEFAULT_MODE_LABEL,
        mode_variant: str | None = None,
    ) -> dict[str, Any]:
        target = normalize_oracle_target(oracle_target)
        provider = oracle_target_provider(target)
        chat_url = oracle_target_chat_url(target)
        resolved_model = resolve_oracle_model(
            oracle_target=target,
            oracle_model=oracle_model,
            mode_label=mode_label,
        )
        thinking_time = resolve_oracle_thinking_time(
            oracle_target=target,
            resolved_model=resolved_model,
            mode_label=mode_label,
            mode_variant=mode_variant,
        )
        provider_label = "Gemini" if provider == "gemini" else "ChatGPT"
        return {
            "mcp_server": "playwright",
            "backend": PLAYWRIGHT_MCP_BACKEND,
            "run_id": run_id,
            "chat_url": chat_url,
            "profile_name": profile_name or self.config.default_profile_name,
            "oracle_target": target,
            "oracle_provider": provider,
            "oracle_model": resolved_model,
            "oracle_thinking_time": thinking_time,
            "prompt": prompt,
            "event_tool": "aiweb_run_record_event",
            "completion_tool": "aiweb_run_complete",
            "failure_tool": "aiweb_run_fail",
            "mode_policy": {
                "default_mode_label": DEFAULT_MODE_LABEL,
                "pro_extended_mode_label": PRO_EXTENDED_MODE_LABEL,
                "pro_extended_timeout_guidance_seconds": 3600,
                "mode_variant_values": ["light", "standard", "extended", "heavy"],
                "guidance": "Use Extension Heavy by default. Use Pro Extended only when the user explicitly asks for GPT Pro / 프로모드 / pro expansion. Pass mode_variant to request a supported thinking-time intensity, and set timeout_seconds to 3600 or more for 30-60 minute Pro runs.",
            },
            "safety": [
                "Use the configured Codex playwright MCP session profile; do not extract cookies or localStorage.",
                "If login, captcha, or payment gates appear, stop and record a user_action_required failure.",
            ],
            "steps": [
                {"tool": "browser_navigate", "args": {"url": chat_url}},
                {"tool": "browser_snapshot", "purpose": "Detect login, captcha, payment, and composer state."},
                {"tool": "browser_type", "purpose": f"Type the run prompt into the {provider_label} composer."},
                {"tool": "browser_press_key", "args": {"key": "Enter"}, "purpose": "Submit the prompt."},
                {"tool": "browser_wait_for", "purpose": "Wait until the assistant response stabilizes."},
                {"tool": "browser_evaluate", "purpose": "Extract assistant text, URL, title, model label, and completion signals."},
                {"tool": "aiweb_run_complete", "purpose": "Persist response.md, events.jsonl, status.json, and run.json."},
            ],
            "completion_criteria": {
                "assistant_response_non_empty": True,
                "assistant_response_stable": True,
                "response_must_correspond_to_prompt": True,
            },
        }

    @staticmethod
    def _next_event_id(artifacts: RunArtifacts) -> int:
        if not artifacts.events_jsonl.exists():
            return 1
        text = artifacts.events_jsonl.read_text(encoding="utf-8")
        if not text.strip():
            return 1
        return len(text.splitlines()) + 1

    def _load_run_payload(self, artifacts: RunArtifacts, run_id: str) -> dict[str, Any]:
        payload = read_json(artifacts.run_json)
        if not payload:
            raise ValueError(f"Unknown run_id: {run_id}")
        return payload

    def _write_status_and_update_run(self, artifacts: RunArtifacts, status_payload: dict[str, Any]) -> None:
        run_payload = read_json(artifacts.run_json)
        if run_payload:
            history = list(run_payload.get("state_history") or [])
            history.append(
                {
                    "status": status_payload.get("status"),
                    "phase": status_payload.get("phase"),
                    "updated_at": status_payload.get("updated_at"),
                }
            )
            run_payload.update(
                {
                    "status": status_payload.get("status"),
                    "phase": status_payload.get("phase"),
                    "updated_at": status_payload.get("updated_at"),
                    "state_history": history[-20:],
                    "recoverable": self._status_payload_recoverable(status_payload),
                }
            )
            atomic_write_json(artifacts.run_json, run_payload)
        atomic_write_json(artifacts.status_json, status_payload)

    def _validate_external_completion_evidence(
        self,
        *,
        run_id: str,
        artifacts: RunArtifacts,
        response_text: str,
        evidence: dict[str, Any] | None,
    ) -> dict[str, Any]:
        run_payload = self._load_run_payload(artifacts, run_id)
        if run_payload.get("browser_backend") != PLAYWRIGHT_MCP_BACKEND:
            return self._redact_nested(evidence or {})
        payload = evidence or {}
        if not response_text.strip():
            raise ValueError("External completion response_text must be non-empty")
        required = ("run_id", "oracle_provider", "oracle_target", "url", "prompt_hash", "final_status")
        missing = [key for key in required if not payload.get(key)]
        if missing:
            raise ValueError(f"Missing completion evidence: {', '.join(missing)}")
        if str(payload.get("run_id")) != run_id:
            raise ValueError("External completion evidence run_id mismatch")
        expected_target = str(run_payload.get("oracle_target") or DEFAULT_ORACLE_TARGET)
        expected_provider = oracle_target_provider(expected_target)
        if str(payload.get("oracle_provider")) != expected_provider:
            raise ValueError(f"External completion evidence must identify {expected_provider} provider")
        if str(payload.get("oracle_target")) != expected_target:
            raise ValueError(f"External completion evidence must identify {expected_target} target")
        if str(payload.get("prompt_hash")) != str(run_payload.get("prompt_hash")):
            raise ValueError("External completion evidence prompt_hash mismatch")
        url = str(payload.get("url") or "")
        if expected_provider == "chatgpt":
            if "chatgpt.com" not in url:
                raise ValueError("External completion evidence must include a ChatGPT URL")
            if "/c/" not in url and not payload.get("conversation_id"):
                raise ValueError("External completion evidence must include a conversation URL or conversation_id")
        elif expected_provider == "gemini":
            if "gemini.google.com" not in url:
                raise ValueError("External completion evidence must include a Gemini URL")
        if str(payload.get("final_status")).lower() not in {"done", "completed"}:
            raise ValueError("External completion evidence final_status must be done or completed")
        return self._redact_nested(payload)

    def _resume_guidance_for_phase(self, status_payload: dict[str, Any]) -> tuple[str, str]:
        phase = str(status_payload.get("phase") or "")
        provider = str(status_payload.get("oracle_provider") or "").lower()
        target = str(status_payload.get("oracle_target") or DEFAULT_ORACLE_TARGET)
        provider_label = "Gemini" if provider == "gemini" or target == "gemini_browser" else "ChatGPT"
        target_arg = "gemini_browser" if provider_label == "Gemini" else "chatgpt_browser"
        if phase == "MODEL_SELECTOR_UNAVAILABLE":
            return (
                "use_playwright_mcp",
                "ChatGPT model selector was not available to Oracle. Use Playwright MCP to inspect the visible ChatGPT tab and record user_action_required if the UI changed or a gate is visible.",
            )
        if phase == "PRO_NOT_AVAILABLE":
            return (
                "use_playwright_mcp",
                "ChatGPT Pro was not available in the model picker. Inspect the account in the browser profile before retrying.",
            )
        if phase == "PRO_EFFORT_UNCONFIRMED":
            return (
                "use_playwright_mcp",
                "Oracle refused to submit because Pro Extended effort was not confirmed. Inspect the model picker and thinking effort controls.",
            )
        if phase == "PROFILE_BUSY":
            return (
                "close_conflicting_browser",
                f"The Oracle {provider_label} profile is busy or has an unreachable DevTools port. Close Chrome windows using the Oracle profile, then retry prepare_session or run_start.",
            )
        if phase == "LOGIN_REQUIRED":
            return (
                "run_oracle_manual_login_setup",
                f"The {provider_label} browser profile is not logged in. Run aiweb_prepare_session with browser_backend='oracle', oracle_target='{target_arg}', open_browser=true.",
            )
        if phase == "CHROME_NOT_FOUND":
            return (
                "configure_chrome_path",
                "Oracle could not locate a Chrome or Chromium browser. Install Chrome, or ensure the standard Windows Chrome path is available before retrying prepare_session or run_start.",
            )
        if phase == "REATTACH_REQUIRED":
            return (
                "inspect_artifacts",
                "The Pro run appears to need reattach because it may still be thinking or capture was incomplete. Inspect Oracle artifacts and retry resume after the answer appears.",
            )
        if phase == "CAPTURE_INCOMPLETE":
            return (
                "inspect_artifacts",
                "The Pro answer capture was incomplete. Inspect Oracle artifacts, then retry resume or use Playwright MCP to harvest the completed response.",
            )
        return (
            "inspect_artifacts" if status_payload.get("status") != "user_action_required" else "use_playwright_mcp",
            str(status_payload.get("message") or "Inspect artifacts for the current run state."),
        )

    def prepare_session(
        self,
        *,
        profile_name: str | None = None,
        dry_run: bool = False,
        open_browser: bool = False,
        browser_backend: str = PLAYWRIGHT_MCP_BACKEND,
        oracle_target: str = DEFAULT_ORACLE_TARGET,
    ) -> dict[str, Any]:
        backend = self._validate_browser_backend(browser_backend)
        profile_dir = self.config.profile_dir(profile_name)
        profile_dir.mkdir(parents=True, exist_ok=True)
        if dry_run:
            if backend in {ORACLE_BACKEND, PLAYWRIGHT_MCP_BACKEND}:
                target = normalize_oracle_target(oracle_target)
                provider = oracle_target_provider(target)
                payload = {
                    "ok": True,
                    "auth_state": "ready",
                    "next_action": "continue",
                    "profile_dir": str(profile_dir),
                    "chat_url": oracle_target_chat_url(target),
                    "browser_backend": backend,
                    "oracle_target": target,
                    "oracle_provider": provider,
                    "message": "Dry-run session is ready.",
                }
                if backend == ORACLE_BACKEND:
                    oracle_home_base = self.config.oracle_home_dir or (self.config.state_root / "oracle")
                    oracle_home = oracle_target_home_dir(oracle_home_base, target)
                    oracle_profile = oracle_target_profile_dir(oracle_home_base, target)
                    payload.update(
                        {
                            "profile_dir": str(oracle_profile.resolve()),
                            "codex_profile_dir": str(profile_dir),
                            "oracle_home_dir": str(oracle_home.resolve()),
                            "oracle_profile_dir": str(oracle_profile.resolve()),
                        }
                    )
                return payload
            return {
                "ok": True,
                "auth_state": "ready",
                "next_action": "continue",
                "profile_dir": str(profile_dir),
                "chat_url": self.config.chat_url,
                "browser_backend": backend,
                "message": "Dry-run session is ready.",
            }
        if backend == ORACLE_BACKEND:
            target = normalize_oracle_target(oracle_target)
            provider = oracle_target_provider(target)
            oracle_home_base = self.config.oracle_home_dir or (self.config.state_root / "oracle")
            oracle_home = oracle_target_home_dir(oracle_home_base, target)
            oracle_profile = oracle_target_profile_dir(oracle_home_base, target)
            oracle_profile.mkdir(parents=True, exist_ok=True)
            oracle_client = OracleClient(command=self.config.oracle_command, oracle_home_dir=oracle_home_base)
            setup_command = oracle_client.build_manual_login_setup_command(oracle_target=target)
            chat_url = oracle_target_chat_url(target)
            provider_label = "Gemini" if provider == "gemini" else "ChatGPT"
            payload = {
                "ok": False,
                "auth_state": "user_action_required",
                "next_action": "run_oracle_manual_login_setup",
                "profile_dir": str(oracle_profile.resolve()),
                "codex_profile_dir": str(profile_dir),
                "oracle_home_dir": str(oracle_home.resolve()),
                "oracle_profile_dir": str(oracle_profile.resolve()),
                "oracle_target": target,
                "oracle_provider": provider,
                "chat_url": chat_url,
                "browser_backend": backend,
                "manual_login_setup": {
                    "command": setup_command,
                    "profile_dir": str(oracle_profile.resolve()),
                    "opens_visible_browser": True,
                    "keeps_browser_open": True,
                    "purpose": f"Initialize the dedicated Oracle {provider_label} manual-login browser profile.",
                },
                "message": f"Oracle {provider_label} browser runs use a dedicated manual-login profile. Initialize that profile with manual_login_setup before normal Oracle runs.",
            }
            if open_browser:
                launch = oracle_client.launch_manual_login_setup(
                    cwd=self.config.state_root,
                    oracle_target=target,
                )
                payload["manual_login_setup"].update(
                    {
                        "launched": True,
                        "pid": launch.pid,
                        "stdout_log": str(launch.stdout_path),
                        "stderr_log": str(launch.stderr_path),
                        "command": launch.command,
                    }
                )
                payload["message"] = (
                    f"Oracle {provider_label} manual-login setup was launched. "
                    "Complete login in the visible dedicated browser, then retry the Oracle run."
                )
            return payload
        if backend == PLAYWRIGHT_MCP_BACKEND and open_browser:
            target = normalize_oracle_target(oracle_target)
            chat_url = oracle_target_chat_url(target)
            return {
                "ok": False,
                "auth_state": "user_action_required",
                "next_action": "use_playwright_mcp",
                "profile_dir": str(profile_dir),
                "chat_url": chat_url,
                "browser_backend": backend,
                "oracle_target": target,
                "oracle_provider": oracle_target_provider(target),
                "action_plan": self._external_playwright_action_plan(profile_name=profile_name, oracle_target=target),
                "message": "Use the configured Codex playwright MCP to open the target Web provider and complete any manual login.",
            }
        if not open_browser:
            return {
                "ok": False,
                "auth_state": "login_required",
                "next_action": "user_login",
                "profile_dir": str(profile_dir),
                "chat_url": self.config.chat_url,
                "browser_backend": backend,
                "message": "ChatGPT login must be prepared in the browser profile before live runs.",
            }
        result = self._resolve_live_backend(profile_name).prepare_session(
            profile_dir=profile_dir,
            chat_url=self.config.chat_url,
            open_browser=open_browser,
        )
        return {**result.__dict__, "browser_backend": backend}

    def start_run(
        self,
        *,
        question: str,
        files: list[str] | None = None,
        output_name: str | None = None,
        mode_label: str = DEFAULT_MODE_LABEL,
        mode_variant: str | None = None,
        dry_run: bool = False,
        dry_run_response: str | None = None,
        browser_backend: str = PLAYWRIGHT_MCP_BACKEND,
        completion_backend: str = "cdp_injected",
        live: bool = False,
        profile_name: str | None = None,
        timeout_seconds: int = 120,
        open_browser: bool = False,
        repo_root: str | None = None,
        permission_level: str = "safe_default",
        dry_run_policy: bool = False,
        oracle_target: str = DEFAULT_ORACLE_TARGET,
        oracle_model: str | None = None,
    ) -> dict[str, Any]:
        if not question or not str(question).strip():
            raise ValueError("question is required")
        backend = self._validate_browser_backend(browser_backend)
        safe_output_name = validate_name(output_name, "output_name", max_length=80) if output_name else None
        run_id = make_run_id(safe_output_name)
        artifacts = self._artifacts(run_id)
        artifacts.run_dir.mkdir(parents=True, exist_ok=True)
        created_at = now_iso()
        created_at_ns = time.time_ns()
        run_payload = {
            "run_id": run_id,
            "created_at": created_at,
            "created_at_ns": created_at_ns,
            "updated_at": created_at,
            "question_chars": len(question),
            "prompt_hash": self._prompt_hash(question),
            "prompt_hash_algorithm": "sha256",
            "hash_algorithm": "sha256",
            "state_history": [],
            "recoverable": False,
            "files": files or [],
            "mode_label": mode_label,
            "mode_variant": mode_variant,
            "browser_backend": backend,
            "completion_backend": completion_backend,
            "dry_run": bool(dry_run),
            "live": bool(live),
            "profile_name": profile_name,
            "repo_root": repo_root,
            "permission_level": permission_level,
            "dry_run_policy": bool(dry_run_policy),
            "oracle_target": oracle_target if backend == ORACLE_BACKEND else None,
            "oracle_model": oracle_model if backend == ORACLE_BACKEND else None,
            "artifact_paths": artifacts.to_dict(),
        }
        atomic_write_text(artifacts.prompt_txt, question)
        artifacts.events_jsonl.touch(exist_ok=True)
        if dry_run:
            response = dry_run_response if dry_run_response is not None else "DRY RUN: ChatGPT Web runtime is wired."
            atomic_write_text(artifacts.response_md, response)
            event = RuntimeEvent(
                event_id=1,
                run_id=run_id,
                status="done",
                user_text=question,
                assistant_text=response,
                model_label=mode_label,
                signals={"dry_run": True, "assistant_action_visible": True, "stable_ms": 0},
            )
            artifacts.append_event(event)
            status_payload = {
                "run_id": run_id,
                "status": "completed",
                "phase": "COMPLETED",
                "updated_at": now_iso(),
                "message": "Dry-run completed.",
            }
        elif live and backend == ORACLE_BACKEND:
            status_payload = self._run_oracle(
                run_id=run_id,
                question=question,
                artifacts=artifacts,
                files=files or [],
                repo_root=repo_root,
                permission_level=permission_level,
                mode_label=mode_label,
                mode_variant=mode_variant,
                timeout_seconds=timeout_seconds,
                dry_run_policy=dry_run_policy,
                oracle_target=oracle_target,
                oracle_model=oracle_model,
            )
        elif live and backend == PLAYWRIGHT_MCP_BACKEND:
            status_payload = self._start_external_playwright_run(
                run_id=run_id,
                question=question,
                profile_name=profile_name,
                oracle_target=oracle_target,
                oracle_model=oracle_model,
                mode_label=mode_label,
                mode_variant=mode_variant,
            )
        elif live:
            status_payload = self._run_live(
                run_id=run_id,
                question=question,
                artifacts=artifacts,
                profile_name=profile_name,
                timeout_seconds=timeout_seconds,
                open_browser=open_browser,
            )
        else:
            status_payload = {
                "run_id": run_id,
                "status": "user_action_required",
                "phase": "LOGIN_REQUIRED",
                "updated_at": now_iso(),
                "message": "Live ChatGPT Web execution requires prepare_session and browser backend enablement.",
            }
        run_payload.update(
            {
                "status": status_payload["status"],
                "phase": status_payload["phase"],
                "updated_at": status_payload["updated_at"],
                "recoverable": self._status_payload_recoverable(status_payload),
            }
        )
        for key in ("oracle_scope", "oracle_target", "oracle_provider", "oracle_model", "oracle_thinking_time", "oracle_engine"):
            if key in status_payload:
                run_payload[key] = status_payload[key]
        atomic_write_json(artifacts.run_json, run_payload)
        atomic_write_json(artifacts.status_json, status_payload)
        return {**status_payload, "artifact_paths": artifacts.to_dict()}

    def _run_oracle(
        self,
        *,
        run_id: str,
        question: str,
        artifacts: RunArtifacts,
        files: list[str],
        repo_root: str | None,
        permission_level: str,
        mode_label: str,
        timeout_seconds: int,
        dry_run_policy: bool,
        oracle_target: str,
        oracle_model: str | None,
        mode_variant: str | None,
    ) -> dict[str, Any]:
        result = self._resolve_oracle_adapter().run(
            prompt=question,
            files=files,
            repo_root=repo_root,
            permission_level=permission_level,
            mode_label=mode_label,
            mode_variant=mode_variant,
            response_path=artifacts.response_md,
            timeout_seconds=timeout_seconds,
            oracle_target=oracle_target,
            oracle_model=oracle_model,
            dry_run_policy=dry_run_policy,
        )
        if result.response_text:
            atomic_write_text(artifacts.response_md, result.response_text)
        if result.status == "completed":
            event_status = "done"
        elif result.status == "policy_preview":
            event_status = "preview"
        else:
            event_status = "error"
        artifacts.append_event(
            RuntimeEvent(
                event_id=self._next_event_id(artifacts),
                run_id=run_id,
                status=event_status,
                user_text=question,
                assistant_text=result.response_text,
                model_label=mode_label,
                error_text="" if result.status == "completed" else redact(result.message),
                signals={
                    "oracle": True,
                    "oracle_target": result.oracle_target,
                    "oracle_provider": result.provider,
                    "oracle_model": result.oracle_model,
                    "oracle_thinking_time": result.oracle_thinking_time,
                    "mode_variant": mode_variant,
                    "oracle_engine": result.oracle_engine,
                    "permission_level": permission_level,
                    "dry_run_policy": dry_run_policy,
                    "scope": result.scope.to_preview(),
                    "exit_code": result.command_result.exit_code if result.command_result else None,
                },
            )
        )
        return {
            "run_id": run_id,
            "status": result.status,
            "phase": result.phase,
            "updated_at": now_iso(),
            "message": redact(result.message),
            "oracle_target": result.oracle_target,
            "oracle_provider": result.provider,
            "oracle_model": result.oracle_model,
            "oracle_thinking_time": result.oracle_thinking_time,
            "oracle_engine": result.oracle_engine,
            "oracle_scope": result.scope.to_preview(),
        }

    def _start_external_playwright_run(
        self,
        *,
        run_id: str,
        question: str,
        profile_name: str | None,
        oracle_target: str,
        oracle_model: str | None,
        mode_label: str,
        mode_variant: str | None,
    ) -> dict[str, Any]:
        target = normalize_oracle_target(oracle_target)
        provider = oracle_target_provider(target)
        resolved_model = resolve_oracle_model(
            oracle_target=target,
            oracle_model=oracle_model,
            mode_label=mode_label,
        )
        thinking_time = resolve_oracle_thinking_time(
            oracle_target=target,
            resolved_model=resolved_model,
            mode_label=mode_label,
            mode_variant=mode_variant,
        )
        action_plan = self._external_playwright_action_plan(
            run_id=run_id,
            prompt=question,
            profile_name=profile_name,
            oracle_target=target,
            oracle_model=resolved_model,
            mode_label=mode_label,
            mode_variant=mode_variant,
        )
        return {
            "run_id": run_id,
            "status": "awaiting_external_browser",
            "phase": "PLAYWRIGHT_MCP_ACTION_REQUIRED",
            "updated_at": now_iso(),
            "next_action": "use_playwright_mcp",
            "browser_backend": PLAYWRIGHT_MCP_BACKEND,
            "oracle_target": target,
            "oracle_provider": provider,
            "oracle_model": resolved_model,
            "oracle_thinking_time": thinking_time,
            "message": "Use the configured Codex playwright MCP to submit the prompt, then call aiweb_run_complete or aiweb_run_fail.",
            "action_plan": action_plan,
        }

    def _run_live(
        self,
        *,
        run_id: str,
        question: str,
        artifacts: RunArtifacts,
        profile_name: str | None,
        timeout_seconds: int,
        open_browser: bool,
    ) -> dict[str, Any]:
        profile_dir = self.config.profile_dir(profile_name)
        backend = self._resolve_live_backend(profile_name)
        session = backend.prepare_session(profile_dir=profile_dir, chat_url=self.config.chat_url, open_browser=open_browser)
        if not session.ok:
            phase = {
                "login_required": "LOGIN_REQUIRED",
                "captcha_required": "CAPTCHA_REQUIRED",
                "payment_required": "PAYMENT_REQUIRED",
            }.get(session.auth_state, "USER_ACTION_REQUIRED")
            return {
                "run_id": run_id,
                "status": "user_action_required",
                "phase": phase,
                "auth_state": session.auth_state,
                "next_action": session.next_action,
                "updated_at": now_iso(),
                "message": redact(session.message),
            }

        result = backend.run_prompt(run_id=run_id, prompt=question, timeout_seconds=timeout_seconds)
        self._write_live_events(artifacts, result)
        if result.status == "done":
            atomic_write_text(artifacts.response_md, result.response_text)
            return {
                "run_id": run_id,
                "status": "completed",
                "phase": "COMPLETED",
                "updated_at": now_iso(),
                "message": redact(result.message or "Live run completed."),
            }
        if result.status in {"login_required", "captcha_required", "payment_required"}:
            return {
                "run_id": run_id,
                "status": "user_action_required",
                "phase": result.status.upper(),
                "auth_state": result.status,
                "next_action": "prepare_session",
                "updated_at": now_iso(),
                "message": redact(result.message),
            }
        return {
            "run_id": run_id,
            "status": "failed" if result.status in {"error", "timeout", "watch_lost"} else result.status,
            "phase": result.status.upper(),
            "updated_at": now_iso(),
            "message": redact(result.message),
            "error_text": redact(result.error_text),
        }

    @staticmethod
    def _write_live_events(artifacts: RunArtifacts, result: LiveRunResult) -> None:
        for event in result.events:
            event.error_text = redact(event.error_text)
            artifacts.append_event(event)

    def record_event(
        self,
        *,
        run_id: str,
        status: str,
        user_text: str = "",
        assistant_text: str = "",
        url: str = "",
        title: str = "",
        conversation_id: str = "",
        tab_id: str | int | None = None,
        page_session_id: str = "",
        model_label: str = "",
        error_text: str = "",
        signals: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifacts = self._artifacts(run_id)
        self._load_run_payload(artifacts, run_id)
        event = RuntimeEvent(
            event_id=self._next_event_id(artifacts),
            run_id=run_id,
            status=status,
            user_text=user_text,
            assistant_text=assistant_text,
            url=url,
            title=title,
            conversation_id=conversation_id,
            tab_id=tab_id,
            page_session_id=page_session_id,
            model_label=model_label,
            error_text=redact(error_text),
            signals=self._redact_nested(signals or {}),
        )
        artifacts.append_event(event)
        return {"run_id": run_id, "status": "recorded", "event_id": event.event_id}

    def complete_run(
        self,
        run_id: str,
        *,
        response_text: str,
        evidence: dict[str, Any] | None = None,
        message: str | None = None,
    ) -> dict[str, Any]:
        artifacts = self._artifacts(run_id)
        self._load_run_payload(artifacts, run_id)
        self._assert_run_not_terminal(artifacts)
        safe_evidence = self._validate_external_completion_evidence(
            run_id=run_id,
            artifacts=artifacts,
            response_text=response_text,
            evidence=evidence,
        )
        atomic_write_text(artifacts.response_md, response_text)
        prompt_text = artifacts.prompt_txt.read_text(encoding="utf-8") if artifacts.prompt_txt.exists() else ""
        event = RuntimeEvent(
            event_id=self._next_event_id(artifacts),
            run_id=run_id,
            status="done",
            user_text=str(safe_evidence.get("user_text") or prompt_text),
            assistant_text=response_text,
            url=str(safe_evidence.get("url") or ""),
            title=str(safe_evidence.get("title") or ""),
            model_label=str(safe_evidence.get("model_label") or ""),
            signals={"external_browser": True, "evidence": safe_evidence},
        )
        artifacts.append_event(event)
        status_payload = {
            "run_id": run_id,
            "status": "completed",
            "phase": "COMPLETED",
            "updated_at": now_iso(),
            "message": redact(message or "External Playwright MCP run completed."),
            "evidence": safe_evidence,
        }
        self._write_status_and_update_run(artifacts, status_payload)
        return status_payload

    def fail_run(
        self,
        run_id: str,
        *,
        status: str,
        message: str,
        error_text: str | None = None,
        evidence: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        artifacts = self._artifacts(run_id)
        self._load_run_payload(artifacts, run_id)
        self._assert_run_not_terminal(artifacts)
        normalized_status = str(status or "error").lower()
        safe_evidence = self._redact_nested(evidence or {})
        runtime_status = "user_action_required" if normalized_status in USER_ACTION_FAILURE_STATUSES else "failed"
        event_status = "watch_lost" if normalized_status == "watch_lost" else "error"
        event = RuntimeEvent(
            event_id=self._next_event_id(artifacts),
            run_id=run_id,
            status=event_status,
            error_text=redact(error_text or message),
            signals={"external_browser": True, "failure_status": normalized_status, "evidence": safe_evidence},
        )
        artifacts.append_event(event)
        status_payload = {
            "run_id": run_id,
            "status": runtime_status,
            "phase": normalized_status.upper(),
            "auth_state": normalized_status if normalized_status in USER_ACTION_FAILURE_STATUSES else None,
            "next_action": "use_playwright_mcp" if runtime_status == "user_action_required" else "inspect_artifacts",
            "updated_at": now_iso(),
            "message": redact(message),
            "error_text": redact(error_text or ""),
            "evidence": safe_evidence,
        }
        self._write_status_and_update_run(artifacts, status_payload)
        return status_payload

    def run_status(self, run_id: str) -> dict[str, Any]:
        status = read_json(self._artifacts(run_id).status_json)
        if not status:
            raise ValueError(f"Unknown run_id: {run_id}")
        return status

    def run_wait(self, run_id: str, *, timeout_seconds: int | None = None, poll_interval_seconds: float = 0.25) -> dict[str, Any]:
        deadline = time.time() + timeout_seconds if timeout_seconds and timeout_seconds > 0 else None
        latest = self.run_status(run_id)
        while not status_is_terminal(str(latest.get("status", ""))):
            if deadline is not None and time.time() >= deadline:
                return {**latest, "wait_timeout": True}
            time.sleep(max(poll_interval_seconds, 0.05))
            latest = self.run_status(run_id)
        return latest

    def run_resume(self, run_id: str) -> dict[str, Any]:
        status = self.run_status(run_id)
        next_action, message = self._resume_guidance_for_phase(status)
        return {
            **status,
            "resumable": bool(self._status_payload_recoverable(status)),
            "next_action": next_action,
            "message": message,
        }

    def run_artifacts(self, run_id: str) -> dict[str, str]:
        artifacts = self._artifacts(run_id)
        if not artifacts.run_json.exists():
            raise ValueError(f"Unknown run_id: {run_id}")
        return artifacts.to_dict()

    def list_recent_runs(self, *, limit: int = 20) -> list[dict[str, Any]]:
        runs = []
        for run_json in self.config.runs_dir.glob("*/run.json"):
            payload = read_json(run_json)
            if payload:
                runs.append(payload)
        runs.sort(key=lambda item: (int(item.get("created_at_ns", 0)), str(item.get("created_at", ""))), reverse=True)
        return runs[: max(1, min(int(limit), 100))]
