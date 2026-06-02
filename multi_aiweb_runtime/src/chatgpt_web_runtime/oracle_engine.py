from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Mapping

from .oracle_engine_capabilities import DEFAULT_CAPABILITIES_VERSION

ORACLE_ENGINE_SOURCE_ENV = "MULTI_AIWEB_RUNTIME_ORACLE_ENGINE_SOURCE"
LEGACY_ORACLE_ENGINE_SOURCE_ENV = "CHATGPT_WEB_RUNTIME_ORACLE_ENGINE_SOURCE"
PLUGIN_ROOT_ENV = "MULTI_AIWEB_RUNTIME_PLUGIN_ROOT"
LEGACY_PLUGIN_ROOT_ENV = "CHATGPT_WEB_RUNTIME_PLUGIN_ROOT"
ORACLE_ENGINE_DIR_ENV = "MULTI_AIWEB_RUNTIME_ORACLE_ENGINE_DIR"
LEGACY_ORACLE_ENGINE_DIR_ENV = "CHATGPT_WEB_RUNTIME_ORACLE_ENGINE_DIR"

BUNDLED_ENGINE_SOURCE = "bundled"
UPSTREAM_NPX_ENGINE_SOURCE = "upstream_npx"
CUSTOM_COMMAND_ENGINE_SOURCE = "custom_command"
AUTO_ENGINE_SOURCE = "auto"

BUNDLED_ORACLE_MODULE = "multi_aiweb_runtime.oracle_engine_cli"
LEGACY_BUNDLED_ORACLE_MODULE = "chatgpt_web_runtime.oracle_engine_cli"
UPSTREAM_NPX_COMMAND = ("npx", "-y", "@steipete/oracle@0.13.0")
BUNDLED_ORACLE_COMMAND = (sys.executable, "-P", "-m", BUNDLED_ORACLE_MODULE)

DEFAULT_ORACLE_ENGINE_VERSION = "0.13.0-multi-aiweb-runtime.1"
DEFAULT_ORACLE_UPSTREAM_COMMIT = "6019a19"
NEW_METADATA_FILE = "MULTI_AIWEB_RUNTIME_ENGINE.json"
LEGACY_METADATA_FILE = "CHATGPT_WEB_RUNTIME_ENGINE.json"


def _first_env(source: Mapping[str, str], *names: str) -> str | None:
    for name in names:
        value = source.get(name)
        if value:
            return value
    return None


def default_oracle_command(env: Mapping[str, str] | None = None) -> tuple[str, ...]:
    source = _resolve_engine_source(env)
    if source == BUNDLED_ENGINE_SOURCE:
        return BUNDLED_ORACLE_COMMAND
    return UPSTREAM_NPX_COMMAND


def oracle_engine_identity(
    *,
    source: str | None = None,
    command: tuple[str, ...] | list[str] | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, str]:
    resolved_source = source or _identity_source_from_command(command, env)
    if resolved_source == BUNDLED_ENGINE_SOURCE:
        metadata = _read_bundled_engine_metadata(env)
        return {
            "source": BUNDLED_ENGINE_SOURCE,
            "name": metadata.get("name") or "oracle-custom",
            "version": metadata.get("version") or DEFAULT_ORACLE_ENGINE_VERSION,
            "upstream_commit": metadata.get("upstream_commit") or DEFAULT_ORACLE_UPSTREAM_COMMIT,
            "capabilities_version": metadata.get("capabilities_version") or DEFAULT_CAPABILITIES_VERSION,
        }
    if resolved_source == CUSTOM_COMMAND_ENGINE_SOURCE:
        return {
            "source": CUSTOM_COMMAND_ENGINE_SOURCE,
            "name": "oracle-custom-command",
            "version": "unknown",
            "upstream_commit": "unknown",
            "capabilities_version": DEFAULT_CAPABILITIES_VERSION,
        }
    return {
        "source": UPSTREAM_NPX_ENGINE_SOURCE,
        "name": "@steipete/oracle",
        "version": "0.13.0",
        "upstream_commit": DEFAULT_ORACLE_UPSTREAM_COMMIT,
        "capabilities_version": DEFAULT_CAPABILITIES_VERSION,
    }


def bundled_oracle_engine_dir(env: Mapping[str, str] | None = None) -> Path | None:
    source = dict(env or os.environ)
    explicit = _first_env(source, ORACLE_ENGINE_DIR_ENV, LEGACY_ORACLE_ENGINE_DIR_ENV)
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        return candidate if candidate.exists() else None
    plugin_root = _first_env(source, PLUGIN_ROOT_ENV, LEGACY_PLUGIN_ROOT_ENV)
    candidates: list[Path] = []
    if plugin_root:
        candidates.append(Path(plugin_root).expanduser().resolve() / "engines" / "oracle")
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "engines" / "oracle")
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def _resolve_engine_source(env: Mapping[str, str] | None = None) -> str:
    source = dict(env or os.environ)
    requested = (_first_env(source, ORACLE_ENGINE_SOURCE_ENV, LEGACY_ORACLE_ENGINE_SOURCE_ENV) or AUTO_ENGINE_SOURCE)
    requested = requested.strip().lower().replace("-", "_")
    if requested in {BUNDLED_ENGINE_SOURCE, UPSTREAM_NPX_ENGINE_SOURCE}:
        return requested
    if requested not in {"", AUTO_ENGINE_SOURCE}:
        raise ValueError(
            f"Unsupported {ORACLE_ENGINE_SOURCE_ENV}: {requested}. "
            f"Allowed values: {AUTO_ENGINE_SOURCE}, {BUNDLED_ENGINE_SOURCE}, {UPSTREAM_NPX_ENGINE_SOURCE}."
        )
    return BUNDLED_ENGINE_SOURCE if bundled_oracle_engine_dir(source) is not None else UPSTREAM_NPX_ENGINE_SOURCE


def is_bundled_oracle_command(command: tuple[str, ...] | list[str]) -> bool:
    normalized = tuple(str(part) for part in command)
    return len(normalized) >= 4 and normalized[1:4] in {
        ("-P", "-m", BUNDLED_ORACLE_MODULE),
        ("-P", "-m", LEGACY_BUNDLED_ORACLE_MODULE),
    }


def _identity_source_from_command(
    command: tuple[str, ...] | list[str] | None,
    env: Mapping[str, str] | None = None,
) -> str:
    if command:
        normalized = tuple(str(part) for part in command)
        if is_bundled_oracle_command(normalized):
            return BUNDLED_ENGINE_SOURCE
        if normalized == UPSTREAM_NPX_COMMAND:
            return UPSTREAM_NPX_ENGINE_SOURCE
        return CUSTOM_COMMAND_ENGINE_SOURCE
    return _resolve_engine_source(env)


def _read_bundled_engine_metadata(env: Mapping[str, str] | None = None) -> dict[str, str]:
    engine_dir = bundled_oracle_engine_dir(env)
    if not engine_dir:
        return {}
    for filename in (NEW_METADATA_FILE, LEGACY_METADATA_FILE):
        metadata_path = engine_dir / filename
        if metadata_path.exists():
            try:
                raw = json.loads(metadata_path.read_text(encoding="utf-8"))
                return {str(key): str(value) for key, value in raw.items() if value is not None}
            except (OSError, json.JSONDecodeError, TypeError, ValueError):
                return {}
    package_json = engine_dir / "package.json"
    if package_json.exists():
        try:
            raw = json.loads(package_json.read_text(encoding="utf-8"))
            version = raw.get("version")
            if version:
                return {"version": f"{version}-multi-aiweb-runtime.1"}
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return {}
    return {}
