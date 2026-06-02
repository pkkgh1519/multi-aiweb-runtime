from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

from .oracle_client import validate_oracle_command
from .oracle_engine import default_oracle_command
from .safe_paths import validate_name


DEFAULT_STATE_ENV = "MULTI_AIWEB_RUNTIME_STATE_DIR"
LEGACY_STATE_ENV = "CHATGPT_WEB_RUNTIME_STATE_DIR"
ORACLE_COMMAND_ENV = "MULTI_AIWEB_RUNTIME_ORACLE_COMMAND"
LEGACY_ORACLE_COMMAND_ENV = "CHATGPT_WEB_RUNTIME_ORACLE_COMMAND"
ORACLE_HOME_ENV = "MULTI_AIWEB_RUNTIME_ORACLE_HOME_DIR"
LEGACY_ORACLE_HOME_ENV = "CHATGPT_WEB_RUNTIME_ORACLE_HOME_DIR"
DEFAULT_ORACLE_COMMAND = default_oracle_command()


def _first_env(*names: str) -> tuple[str | None, str | None]:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value, name
    return None, None


@dataclass(frozen=True)
class RuntimeConfig:
    state_root: Path
    default_profile_name: str = "default"
    chat_url: str = "https://chatgpt.com/"
    oracle_command: tuple[str, ...] = DEFAULT_ORACLE_COMMAND
    oracle_home_dir: Path | None = None

    @classmethod
    def from_env(cls, state_root: str | Path | None = None) -> "RuntimeConfig":
        raw_root, _ = _first_env(DEFAULT_STATE_ENV, LEGACY_STATE_ENV)
        raw_root = state_root or raw_root
        root = Path(raw_root).expanduser() if raw_root else Path.home() / ".codex" / "state" / "multi-aiweb-runtime"
        resolved_root = root.resolve()
        raw_command, _ = _first_env(ORACLE_COMMAND_ENV, LEGACY_ORACLE_COMMAND_ENV)
        oracle_command = validate_oracle_command(shlex.split(raw_command) if raw_command else default_oracle_command())
        raw_oracle_home, oracle_home_env = _first_env(ORACLE_HOME_ENV, LEGACY_ORACLE_HOME_ENV)
        oracle_home = Path(raw_oracle_home).expanduser().resolve() if raw_oracle_home else resolved_root / "oracle"
        if not _is_relative_to(oracle_home, resolved_root):
            raise ValueError(f"{oracle_home_env or ORACLE_HOME_ENV} must stay under the runtime state directory")
        return cls(state_root=resolved_root, oracle_command=oracle_command, oracle_home_dir=oracle_home)

    @property
    def runs_dir(self) -> Path:
        return self.state_root / "runs"

    @property
    def profiles_dir(self) -> Path:
        return self.state_root / "profiles"

    def profile_dir(self, name: str | None = None) -> Path:
        return self.profiles_dir / validate_name(name or self.default_profile_name, "profile_name")


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
