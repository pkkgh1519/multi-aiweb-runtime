from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, Sequence

from .oracle_client import (
    DEFAULT_ORACLE_TARGET,
    OracleClient,
    OracleCommandResult,
    normalize_oracle_target,
    oracle_target_provider,
    resolve_oracle_model,
    resolve_oracle_thinking_time,
)
from .oracle_policy import OraclePolicyError, OracleScope, resolve_oracle_scope
from .redaction import redact


@dataclass(frozen=True)
class OracleRunResult:
    status: str
    phase: str
    message: str
    scope: OracleScope
    oracle_target: str = DEFAULT_ORACLE_TARGET
    provider: str = "chatgpt"
    oracle_model: str | None = None
    oracle_thinking_time: str | None = None
    oracle_engine: dict[str, str] | None = None
    response_text: str = ""
    command_result: OracleCommandResult | None = None


class OracleClientProtocol(Protocol):
    def run_browser_consult(
        self,
        *,
        prompt: str,
        files: Sequence[str | Path],
        output_path: str | Path,
        cwd: str | Path,
        mode_label: str,
        timeout_seconds: int,
        oracle_target: str = DEFAULT_ORACLE_TARGET,
        oracle_model: str | None = None,
        mode_variant: str | None = None,
    ) -> OracleCommandResult:
        ...


class OracleAdapter:
    def __init__(self, *, client: OracleClientProtocol | None = None) -> None:
        self.client = client

    def run(
        self,
        *,
        prompt: str,
        files: Sequence[str] | None,
        repo_root: str | Path | None,
        permission_level: str,
        mode_label: str,
        response_path: str | Path,
        timeout_seconds: int,
        oracle_target: str = DEFAULT_ORACLE_TARGET,
        oracle_model: str | None = None,
        mode_variant: str | None = None,
        dry_run_policy: bool = False,
    ) -> OracleRunResult:
        requested_files = list(files or [])
        effective_repo_root = self._effective_repo_root(
            files=requested_files,
            repo_root=repo_root,
            response_path=response_path,
        )
        scope = resolve_oracle_scope(files=requested_files, repo_root=effective_repo_root, permission_level=permission_level)
        target = DEFAULT_ORACLE_TARGET
        provider = "chatgpt"
        resolved_model: str | None = None
        thinking_time: str | None = None
        try:
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
        except ValueError as exc:
            return OracleRunResult(
                status="policy_blocked",
                phase="ORACLE_TARGET_BLOCKED",
                message=redact(str(exc)),
                scope=scope,
                oracle_target=target,
                provider=provider,
                oracle_model=oracle_model,
                oracle_thinking_time=thinking_time,
            )
        if dry_run_policy:
            return OracleRunResult(
                status="policy_preview",
                phase="ORACLE_POLICY_PREVIEW",
                message="Oracle policy preview generated; no external call was made.",
                scope=scope,
                oracle_target=target,
                provider=provider,
                oracle_model=resolved_model,
                oracle_thinking_time=thinking_time,
            )
        try:
            scope.raise_if_blocked()
        except OraclePolicyError as exc:
            return OracleRunResult(
                status="policy_blocked",
                phase="ORACLE_POLICY_BLOCKED",
                message=redact(str(exc)),
                scope=scope,
                oracle_target=target,
                provider=provider,
                oracle_model=resolved_model,
                oracle_thinking_time=thinking_time,
            )
        client = self._require_client(response_path)
        command_result = client.run_browser_consult(
            prompt=prompt,
            files=scope.allowed_files,
            output_path=response_path,
            cwd=scope.repo_root,
            mode_label=mode_label,
            timeout_seconds=timeout_seconds,
            oracle_target=target,
            oracle_model=resolved_model,
            mode_variant=mode_variant,
        )
        _write_command_logs(response_path, command_result)
        if command_result.exit_code == 0 and command_result.output_text.strip():
            return OracleRunResult(
                status="completed",
                phase="COMPLETED",
                message="Oracle browser run completed.",
                response_text=command_result.output_text,
                scope=scope,
                oracle_target=target,
                provider=provider,
                oracle_model=resolved_model,
                oracle_thinking_time=thinking_time,
                oracle_engine=command_result.engine_identity,
                command_result=command_result,
            )
        timeout_message = _failure_message("Oracle browser run timed out.", command_result)
        timeout_classified = _classify_chatgpt_pro_failure(timeout_message) if target == DEFAULT_ORACLE_TARGET else None
        if command_result.timed_out and timeout_classified is not None:
            status, phase = timeout_classified
            return OracleRunResult(
                status=status,
                phase=phase,
                message=redact(timeout_message),
                scope=scope,
                oracle_target=target,
                provider=provider,
                oracle_model=resolved_model,
                oracle_thinking_time=thinking_time,
                oracle_engine=command_result.engine_identity,
                command_result=command_result,
            )
        if command_result.timed_out:
            return OracleRunResult(
                status="timeout",
                phase="TIMEOUT",
                message=timeout_message,
                scope=scope,
                oracle_target=target,
                provider=provider,
                oracle_model=resolved_model,
                oracle_thinking_time=thinking_time,
                oracle_engine=command_result.engine_identity,
                command_result=command_result,
            )
        message = _failure_message("Oracle browser run failed.", command_result)
        classified = _classify_chatgpt_pro_failure(message) if target == DEFAULT_ORACLE_TARGET else None
        if classified is not None:
            status, phase = classified
            return OracleRunResult(
                status=status,
                phase=phase,
                message=redact(message),
                scope=scope,
                oracle_target=target,
                provider=provider,
                oracle_model=resolved_model,
                oracle_thinking_time=thinking_time,
                oracle_engine=command_result.engine_identity,
                command_result=command_result,
            )
        return OracleRunResult(
            status="failed",
            phase="ORACLE_FAILED",
            message=redact(message),
            scope=scope,
            oracle_target=target,
            provider=provider,
            oracle_model=resolved_model,
            oracle_thinking_time=thinking_time,
            oracle_engine=command_result.engine_identity,
            command_result=command_result,
        )

    def _require_client(self, response_path: str | Path) -> OracleClientProtocol:
        if self.client is not None:
            return self.client
        state_root = Path(response_path).resolve().parents[2]
        self.client = OracleClient(oracle_home_dir=state_root / "oracle")
        return self.client

    @staticmethod
    def _effective_repo_root(
        *,
        files: Sequence[str],
        repo_root: str | Path | None,
        response_path: str | Path,
    ) -> str | Path | None:
        has_requested_files = any(str(item or "").strip() for item in files)
        if has_requested_files:
            return repo_root
        prompt_only_root = _state_root_from_response_path(response_path) / "prompt-only-repo"
        _ensure_prompt_only_repo(prompt_only_root)
        return prompt_only_root


def _state_root_from_response_path(response_path: str | Path) -> Path:
    resolved = Path(response_path).expanduser().resolve()
    try:
        return resolved.parents[2]
    except IndexError:
        return resolved.parent


def _ensure_prompt_only_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir(exist_ok=True)


def _write_command_logs(response_path: str | Path, command_result: OracleCommandResult) -> None:
    run_dir = Path(response_path).expanduser().resolve().parent
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "oracle.stdout.log").write_text(command_result.stdout or "", encoding="utf-8")
    (run_dir / "oracle.stderr.log").write_text(command_result.stderr or "", encoding="utf-8")


def _failure_message(prefix: str, command_result: OracleCommandResult) -> str:
    stderr = _tail(command_result.stderr)
    stdout = _tail(command_result.stdout)
    details: list[str] = []
    if stderr:
        details.append(f"stderr_tail={stderr}")
    if stdout:
        details.append(f"stdout_tail={stdout}")
    if not details:
        return prefix
    return redact(prefix + " " + " ".join(details))


def _classify_chatgpt_pro_failure(message: str) -> tuple[str, str] | None:
    lowered = message.lower()
    if "chatgpt thinking" in lowered or "pro thinking" in lowered:
        return "running", "LONG_THINKING_IN_PROGRESS"
    if "model_selector_unavailable" in lowered or "unable to locate the chatgpt model selector button" in lowered:
        return "user_action_required", "MODEL_SELECTOR_UNAVAILABLE"
    if "unable to find model option" in lowered and "pro" in lowered:
        return "user_action_required", "PRO_NOT_AVAILABLE"
    if "pro_effort_unconfirmed" in lowered or "refusing to submit without confirmed pro extended" in lowered:
        return "user_action_required", "PRO_EFFORT_UNCONFIRMED"
    if "assistant response timed out before completion" in lowered or "reattach later" in lowered:
        return "running", "REATTACH_REQUIRED"
    if "incomplete-capture" in lowered or "capture incomplete" in lowered:
        return "running", "CAPTURE_INCOMPLETE"
    if "prompt did not appear in conversation" in lowered:
        return "user_action_required", "PROMPT_NOT_SUBMITTED"
    if "chrome window closed" in lowered or "econnrefused" in lowered:
        return "user_action_required", "PROFILE_BUSY"
    if "login" in lowered and "required" in lowered:
        return "user_action_required", "LOGIN_REQUIRED"
    return None


def _tail(text: str, limit: int = 1200) -> str:
    normalized = " ".join(str(text or "").split())
    if len(normalized) <= limit:
        return normalized
    return "..." + normalized[-limit:]
