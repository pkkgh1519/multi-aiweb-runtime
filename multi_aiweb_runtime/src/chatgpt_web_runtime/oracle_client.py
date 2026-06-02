from __future__ import annotations

import os
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .oracle_engine import (
    LEGACY_PLUGIN_ROOT_ENV,
    PLUGIN_ROOT_ENV,
    default_oracle_command,
    is_bundled_oracle_command,
    oracle_engine_identity,
)
from .oracle_engine_capabilities import (
    CHATGPT_BROWSER_TARGET,
    GEMINI_BROWSER_TARGET,
    resolve_gemini_browser_model,
)
from .redaction import redact

DEFAULT_ORACLE_COMMAND = default_oracle_command()
PRO_EXTENDED_MODE_LABEL = "Pro Extended"
DEFAULT_ORACLE_TARGET = CHATGPT_BROWSER_TARGET
CHATGPT_BROWSER_URL = "https://chatgpt.com/"
GEMINI_BROWSER_URL = "https://gemini.google.com/app"
BROWSER_THINKING_TIMES = frozenset({"light", "standard", "extended", "heavy"})
_THINKING_TIME_ALIASES = {
    "fast": "light",
    "low": "light",
    "normal": "standard",
    "medium": "standard",
    "default": "standard",
    "deep": "extended",
    "high": "extended",
    "pro": "extended",
    "max": "heavy",
    "maximum": "heavy",
}
_ORACLE_TARGET_PROVIDERS = {
    CHATGPT_BROWSER_TARGET: "chatgpt",
    GEMINI_BROWSER_TARGET: "gemini",
}
_ORACLE_TARGET_ALIASES = {
    "chatgpt": CHATGPT_BROWSER_TARGET,
    "chatgpt_browser": CHATGPT_BROWSER_TARGET,
    "gemini": GEMINI_BROWSER_TARGET,
    "gemini_browser": GEMINI_BROWSER_TARGET,
    "gemini_web": GEMINI_BROWSER_TARGET,
}
_FORBIDDEN_BASE_SUBCOMMANDS = {"serve", "mcp"}
_FORBIDDEN_BASE_OPTIONS = {
    "--engine",
    "--file",
    "--write-output",
    "--dry-run",
    "--model",
    "--prompt",
    "-p",
}
_FORBIDDEN_BASE_OPTION_PREFIXES = ("--browser-", "--remote-")
_FORBIDDEN_COMMAND_EXECUTABLES = {
    "sh",
    "sh.exe",
    "bash",
    "bash.exe",
    "dash",
    "dash.exe",
    "zsh",
    "zsh.exe",
    "fish",
    "fish.exe",
    "ksh",
    "ksh.exe",
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "pwsh.exe",
    "env",
    "env.exe",
}

_SAFE_ENV_NAMES = {
    "PATH",
    "HOME",
    "USER",
    "USERNAME",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "TMP",
    "TEMP",
    "TMPDIR",
    "SYSTEMROOT",
    "COMSPEC",
    "PATHEXT",
    "PROGRAMFILES",
    "PROGRAMFILES(X86)",
    "LOCALAPPDATA",
    "APPDATA",
    "XDG_RUNTIME_DIR",
}
_DANGEROUS_ENV_PREFIXES = (
    "OPENAI_",
    "OPENROUTER_",
    "ANTHROPIC_",
    "GEMINI_",
    "GOOGLE_",
    "AZURE_OPENAI_",
    "XAI_",
    "ORACLE_",
)
PRO_EXTENDED_MIN_BROWSER_TIMEOUT_SECONDS = 3600
_MIN_SUBPROCESS_GRACE_SECONDS = 180
_MAX_SUBPROCESS_GRACE_SECONDS = 600


@dataclass(frozen=True)
class OracleCommandResult:
    exit_code: int
    stdout: str
    stderr: str
    output_text: str
    command: list[str]
    output_path: Path | None = None
    timed_out: bool = False
    engine_identity: dict[str, str] | None = None


@dataclass(frozen=True)
class OracleManualLoginLaunchResult:
    pid: int
    command: list[str]
    profile_dir: Path
    stdout_path: Path
    stderr_path: Path
    engine_identity: dict[str, str] | None = None


class OracleClient:
    def __init__(
        self,
        *,
        command: Sequence[str] | None = None,
        oracle_home_dir: str | Path,
        runner: Callable[..., Any] | None = None,
    ) -> None:
        self.command = list(validate_oracle_command(command or default_oracle_command()))
        self.engine_identity = oracle_engine_identity(command=tuple(self.command))
        self.oracle_home_dir = Path(oracle_home_dir).expanduser().resolve()
        self.runner = runner or subprocess.run

    def build_manual_login_setup_command(
        self,
        *,
        oracle_target: str = DEFAULT_ORACLE_TARGET,
        oracle_model: str | None = None,
        mode_label: str = "",
    ) -> list[str]:
        target = normalize_oracle_target(oracle_target)
        resolved_model = resolve_oracle_model(
            oracle_target=target,
            oracle_model=oracle_model,
            mode_label=mode_label,
        )
        profile_dir = oracle_target_profile_dir(self.oracle_home_dir, target)
        command = [
            *self.command,
            "--engine",
            "browser",
            "--browser-manual-login",
            "--browser-keep-browser",
            "--browser-manual-login-profile-dir",
            str(profile_dir),
            "--browser-input-timeout",
            "120000",
            "--browser-archive",
            "never",
        ]
        if target == CHATGPT_BROWSER_TARGET:
            command.extend(["--browser-model-strategy", "current"])
        elif target == GEMINI_BROWSER_TARGET:
            command.extend(["--browser-thinking-time", "standard"])
        if resolved_model:
            command.extend(["--model", resolved_model])
        command.extend(["-p", "HI"])
        return command

    def launch_manual_login_setup(
        self,
        *,
        cwd: str | Path,
        oracle_target: str = DEFAULT_ORACLE_TARGET,
        oracle_model: str | None = None,
        mode_label: str = "",
        base_env: Mapping[str, str] | None = None,
    ) -> OracleManualLoginLaunchResult:
        target = normalize_oracle_target(oracle_target)
        target_home = oracle_target_home_dir(self.oracle_home_dir, target)
        profile_dir = oracle_target_profile_dir(self.oracle_home_dir, target)
        target_home.mkdir(parents=True, exist_ok=True)
        profile_dir.mkdir(parents=True, exist_ok=True)
        stdout_path = target_home / "manual-login-setup.stdout.log"
        stderr_path = target_home / "manual-login-setup.stderr.log"
        command = self.build_manual_login_setup_command(
            oracle_target=target,
            oracle_model=oracle_model,
            mode_label=mode_label,
        )
        creationflags = 0
        if os.name == "nt":
            creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            creationflags |= getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with stdout_path.open("ab") as stdout_file, stderr_path.open("ab") as stderr_file:
            process = subprocess.Popen(
                command,
                cwd=str(Path(cwd).expanduser().resolve()),
                env=self._sanitized_env(base_env, oracle_target=target),
                stdin=subprocess.DEVNULL,
                stdout=stdout_file,
                stderr=stderr_file,
                shell=False,
                creationflags=creationflags,
            )
        return OracleManualLoginLaunchResult(
            pid=int(process.pid),
            command=command,
            profile_dir=profile_dir,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            engine_identity=self.engine_identity,
        )

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
        dry_run: bool = False,
        base_env: Mapping[str, str] | None = None,
    ) -> OracleCommandResult:
        target = normalize_oracle_target(oracle_target)
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
        cwd_path = Path(cwd).expanduser().resolve()
        output = Path(output_path).expanduser().resolve()
        target_home = oracle_target_home_dir(self.oracle_home_dir, target)
        target_profile = oracle_target_profile_dir(self.oracle_home_dir, target)
        target_home.mkdir(parents=True, exist_ok=True)
        target_profile.mkdir(parents=True, exist_ok=True)
        if not dry_run:
            output.parent.mkdir(parents=True, exist_ok=True)

        command = self._build_browser_command(
            prompt=prompt,
            files=files,
            output_path=output,
            mode_label=mode_label,
            timeout_seconds=timeout_seconds,
            oracle_target=target,
            resolved_model=resolved_model,
            thinking_time=thinking_time,
            dry_run=dry_run,
        )
        browser_timeout = max(
            int(timeout_seconds or 1),
            PRO_EXTENDED_MIN_BROWSER_TIMEOUT_SECONDS
            if str(mode_label).strip().lower() == PRO_EXTENDED_MODE_LABEL.lower()
            else 1,
        )
        effective_timeout = _subprocess_timeout_seconds(browser_timeout)
        try:
            completed = self.runner(
                command,
                cwd=str(cwd_path),
                env=self._sanitized_env(base_env, oracle_target=target),
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=effective_timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            output_text = "" if dry_run else _read_output_text(output)
            if output_text.strip():
                return OracleCommandResult(
                    exit_code=0,
                    stdout=redact(_ensure_text(exc.stdout or "")),
                    stderr=redact(_ensure_text(exc.stderr or "Oracle timed out after writing output.")),
                    output_text=output_text,
                    command=command,
                    output_path=None if dry_run else output,
                    engine_identity=self.engine_identity,
                )
            return OracleCommandResult(
                exit_code=124,
                stdout=redact(_ensure_text(exc.stdout or "")),
                stderr=redact(_ensure_text(exc.stderr or "Oracle timed out.")),
                output_text="",
                command=command,
                output_path=None if dry_run else output,
                timed_out=True,
                engine_identity=self.engine_identity,
            )
        except OSError as exc:
            return OracleCommandResult(
                exit_code=127,
                stdout="",
                stderr=redact(str(exc)),
                output_text="",
                command=command,
                output_path=None if dry_run else output,
                engine_identity=self.engine_identity,
            )
        except subprocess.SubprocessError as exc:
            return OracleCommandResult(
                exit_code=1,
                stdout="",
                stderr=redact(str(exc)),
                output_text="",
                command=command,
                output_path=None if dry_run else output,
                engine_identity=self.engine_identity,
            )

        stdout = redact(getattr(completed, "stdout", "") or "")
        stderr = redact(getattr(completed, "stderr", "") or "")
        output_text = stdout if dry_run else _read_output_text(output)
        return OracleCommandResult(
            exit_code=int(getattr(completed, "returncode", 1)),
            stdout=stdout,
            stderr=stderr,
            output_text=output_text,
            command=command,
            output_path=None if dry_run else output,
            engine_identity=self.engine_identity,
        )

    def _build_browser_command(
        self,
        *,
        prompt: str,
        files: Sequence[str | Path],
        output_path: Path,
        mode_label: str,
        timeout_seconds: int,
        oracle_target: str,
        resolved_model: str | None,
        thinking_time: str,
        dry_run: bool,
    ) -> list[str]:
        pro_extended = str(mode_label).strip().lower() == PRO_EXTENDED_MODE_LABEL.lower()
        browser_timeout = max(int(timeout_seconds or 1), PRO_EXTENDED_MIN_BROWSER_TIMEOUT_SECONDS if pro_extended else 1)
        profile_dir = oracle_target_profile_dir(self.oracle_home_dir, oracle_target)
        command = [
            *self.command,
            "--engine",
            "browser",
            "--browser-manual-login",
            "--browser-manual-login-profile-dir",
            str(profile_dir),
            "--browser-auto-reattach-delay",
            "5s",
            "--browser-auto-reattach-interval",
            "3s",
            "--browser-auto-reattach-timeout",
            "60s",
            "--browser-archive",
            "never",
            "--browser-timeout",
            f"{browser_timeout}s",
        ]
        if oracle_target == CHATGPT_BROWSER_TARGET:
            command.extend(
                [
                    "--browser-model-strategy",
                    "select" if pro_extended else "current",
                    "--browser-thinking-time",
                    thinking_time,
                ]
            )
        elif oracle_target == GEMINI_BROWSER_TARGET:
            command.extend(["--browser-thinking-time", thinking_time])
        if resolved_model:
            command.extend(["--model", resolved_model])
        if dry_run:
            command.extend(["--dry-run", "summary"])
        else:
            command.extend(["--write-output", str(output_path)])
        for path in files:
            command.extend(["--file", str(Path(path))])
        command.extend(["-p", prompt])
        return command

    def _sanitized_env(self, base_env: Mapping[str, str] | None = None, *, oracle_target: str = DEFAULT_ORACLE_TARGET) -> dict[str, str]:
        source = dict(base_env or os.environ)
        env: dict[str, str] = {}
        for key, value in source.items():
            upper = key.upper()
            if upper in _SAFE_ENV_NAMES:
                env[key] = value
                continue
            if upper.startswith(_DANGEROUS_ENV_PREFIXES):
                continue
        env["ORACLE_HOME_DIR"] = str(oracle_target_home_dir(self.oracle_home_dir, oracle_target))
        env["ORACLE_ENGINE"] = "browser"
        bundled_pythonpath = self._bundled_pythonpath(source)
        if bundled_pythonpath:
            env["PYTHONPATH"] = bundled_pythonpath
            env["PYTHONSAFEPATH"] = "1"
        return env

    def _bundled_pythonpath(self, source: Mapping[str, str]) -> str | None:
        if not is_bundled_oracle_command(self.command):
            return None
        plugin_root = source.get(PLUGIN_ROOT_ENV) or source.get(LEGACY_PLUGIN_ROOT_ENV)
        if not plugin_root:
            return None
        root = Path(plugin_root).expanduser().resolve()
        for package_root_name in ("multi_aiweb_runtime", "chatgpt_web_runtime"):
            installed_src = root / package_root_name / "src"
            if installed_src.exists():
                return str(installed_src)
        return None


def validate_oracle_command(command: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(str(token).strip() for token in command if str(token).strip())
    if not normalized:
        raise ValueError("Oracle command must not be empty")
    executable = normalized[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
    if executable in _FORBIDDEN_COMMAND_EXECUTABLES:
        raise ValueError(f"Shell interpreter or command wrapper is not allowed as Oracle command: {normalized[0]}")
    forbidden_long_options = _FORBIDDEN_BASE_OPTIONS - {"-p"}
    for token in normalized:
        lowered = token.lower()
        option_name = token.split("=", 1)[0]
        option_name_lower = lowered.split("=", 1)[0]
        if lowered in _FORBIDDEN_BASE_SUBCOMMANDS or option_name_lower in forbidden_long_options or option_name == "-p":
            raise ValueError(f"Forbidden Oracle command token: {token}")
        if any(option_name_lower.startswith(prefix) for prefix in _FORBIDDEN_BASE_OPTION_PREFIXES):
            raise ValueError(f"Forbidden Oracle command token: {token}")
    return normalized


def normalize_oracle_target(oracle_target: str | None = None) -> str:
    raw_target = (oracle_target or DEFAULT_ORACLE_TARGET).strip().lower().replace("-", "_")
    target = _ORACLE_TARGET_ALIASES.get(raw_target)
    if target is None:
        allowed = ", ".join(sorted(_ORACLE_TARGET_PROVIDERS))
        raise ValueError(f"Unsupported oracle_target: {oracle_target}. Allowed targets: {allowed}")
    return target


def oracle_target_provider(oracle_target: str | None = None) -> str:
    return _ORACLE_TARGET_PROVIDERS[normalize_oracle_target(oracle_target)]


def oracle_target_chat_url(oracle_target: str | None = None) -> str:
    target = normalize_oracle_target(oracle_target)
    if target == GEMINI_BROWSER_TARGET:
        return GEMINI_BROWSER_URL
    return CHATGPT_BROWSER_URL


def oracle_target_home_dir(base_oracle_home_dir: str | Path, oracle_target: str | None = None) -> Path:
    return Path(base_oracle_home_dir).expanduser().resolve() / normalize_oracle_target(oracle_target)


def oracle_target_profile_dir(base_oracle_home_dir: str | Path, oracle_target: str | None = None) -> Path:
    return oracle_target_home_dir(base_oracle_home_dir, oracle_target) / "browser-profile"


def resolve_oracle_model(
    *,
    oracle_target: str | None = None,
    oracle_model: str | None = None,
    mode_label: str = "",
) -> str | None:
    target = normalize_oracle_target(oracle_target)
    model = _normalize_model_name(oracle_model)
    if target == GEMINI_BROWSER_TARGET:
        return _resolve_gemini_browser_model(model)
    if model is not None:
        if not model.startswith("gpt-"):
            raise ValueError("oracle_model for chatgpt_browser must be a GPT browser model")
        return model
    if str(mode_label).strip().lower() == PRO_EXTENDED_MODE_LABEL.lower():
        return "gpt-5.5-pro"
    return None


def resolve_oracle_thinking_time(
    *,
    oracle_target: str | None = None,
    resolved_model: str | None = None,
    mode_label: str = "",
    mode_variant: str | None = None,
) -> str:
    target = normalize_oracle_target(oracle_target)
    requested = _normalize_thinking_time(mode_variant)
    if requested is None:
        requested = _default_thinking_time(target, mode_label)
    if target == GEMINI_BROWSER_TARGET:
        model = resolved_model or resolve_gemini_browser_model(None)
        allowed = {"standard", "extended"} if model == "gemini-3.1-pro" else {"standard"}
        if requested not in allowed:
            allowed_text = ", ".join(sorted(allowed))
            raise ValueError(
                f"Unsupported Gemini browser thinking time '{requested}' for {model}. "
                f"Allowed values: {allowed_text}"
            )
    return requested


def _normalize_thinking_time(mode_variant: str | None) -> str | None:
    if mode_variant is None:
        return None
    normalized = str(mode_variant).strip().lower().replace("_", "-").replace(" ", "-")
    if not normalized:
        return None
    normalized = _THINKING_TIME_ALIASES.get(normalized, normalized)
    if normalized not in BROWSER_THINKING_TIMES:
        allowed = ", ".join(sorted(BROWSER_THINKING_TIMES | frozenset(_THINKING_TIME_ALIASES)))
        raise ValueError(f"Unsupported browser thinking time: {mode_variant}. Allowed values: {allowed}")
    return normalized


def _default_thinking_time(oracle_target: str, mode_label: str) -> str:
    pro_extended = str(mode_label).strip().lower() == PRO_EXTENDED_MODE_LABEL.lower()
    if oracle_target == GEMINI_BROWSER_TARGET:
        return "extended" if pro_extended else "standard"
    return "extended" if pro_extended else "heavy"


def _normalize_model_name(oracle_model: str | None) -> str | None:
    if oracle_model is None:
        return None
    model = str(oracle_model).strip().lower()
    return model or None


def _resolve_gemini_browser_model(model: str | None) -> str:
    return resolve_gemini_browser_model(model)


def _read_output_text(output: Path) -> str:
    if not output.exists():
        return ""
    return output.read_text(encoding="utf-8")


def _ensure_text(value: str | bytes) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _subprocess_timeout_seconds(browser_timeout_seconds: int) -> int:
    browser_timeout = max(int(browser_timeout_seconds or 1), 1)
    grace = max(
        _MIN_SUBPROCESS_GRACE_SECONDS,
        min(_MAX_SUBPROCESS_GRACE_SECONDS, browser_timeout),
    )
    return browser_timeout + grace
