#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)\."
    r"(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?"
    r"(?:\+[0-9A-Za-z.-]+)?$"
)


def load_json(path: Path, label: str, errors: list[str]) -> dict:
    if not path.is_file():
        errors.append(f"missing {label}: {path}")
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        errors.append(f"invalid JSON in {label}: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} must be a JSON object")
        return {}
    return data


def require_string(obj: dict, key: str, errors: list[str], prefix: str = "plugin.json") -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{prefix}.{key} must be a non-empty string")
        return ""
    return value


def validate_https(value: str, field: str, errors: list[str]) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append(f"{field} must be an https URL")


def reject_todo(value, path: str, errors: list[str]) -> None:
    if isinstance(value, str):
        if "[TODO:" in value:
            errors.append(f"{path} contains a [TODO: ...] marker")
        return
    if isinstance(value, dict):
        for key, child in value.items():
            reject_todo(child, f"{path}.{key}", errors)
    if isinstance(value, list):
        for index, child in enumerate(value):
            reject_todo(child, f"{path}[{index}]", errors)


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    errors: list[str] = []
    manifest = load_json(root / ".codex-plugin" / "plugin.json", ".codex-plugin/plugin.json", errors)
    reject_todo(manifest, "plugin.json", errors)

    name = require_string(manifest, "name", errors)
    if name and name != "multi-aiweb-runtime":
        errors.append("plugin.json.name must remain multi-aiweb-runtime")
    version = require_string(manifest, "version", errors)
    if version and not SEMVER_RE.fullmatch(version):
        errors.append("plugin.json.version must be semver")
    require_string(manifest, "description", errors)

    author = manifest.get("author")
    if not isinstance(author, dict):
        errors.append("plugin.json.author must be an object")
    else:
        require_string(author, "name", errors, "plugin.json.author")
        for key in ("url",):
            if key in author:
                validate_https(str(author[key]), f"plugin.json.author.{key}", errors)

    for key in ("homepage", "repository"):
        if key in manifest:
            validate_https(str(manifest[key]), f"plugin.json.{key}", errors)

    for path_key, expected in (("skills", "skills"), ("mcpServers", ".mcp.json")):
        if path_key in manifest and not (root / expected).exists():
            errors.append(f"plugin.json.{path_key} points to missing {expected}")

    interface = manifest.get("interface")
    if not isinstance(interface, dict):
        errors.append("plugin.json.interface must be an object")
    else:
        for key in ("displayName", "shortDescription", "longDescription", "developerName", "category"):
            require_string(interface, key, errors, "plugin.json.interface")
        prompts = interface.get("defaultPrompt") or interface.get("default_prompt")
        if not isinstance(prompts, list) or not all(isinstance(item, str) and item.strip() for item in prompts):
            errors.append("plugin.json.interface.defaultPrompt must be a non-empty string array")
        caps = interface.get("capabilities")
        if not isinstance(caps, list) or not all(isinstance(item, str) and item.strip() for item in caps):
            errors.append("plugin.json.interface.capabilities must be a string array")
        for key in ("websiteURL", "privacyPolicyURL", "termsOfServiceURL"):
            if key in interface:
                validate_https(str(interface[key]), f"plugin.json.interface.{key}", errors)

    mcp = load_json(root / ".mcp.json", ".mcp.json", errors)
    servers = mcp.get("mcpServers") if isinstance(mcp, dict) else None
    if not isinstance(servers, dict) or "multi_aiweb_runtime" not in servers:
        errors.append(".mcp.json must define mcpServers.multi_aiweb_runtime")

    oracle_package = root / "engines" / "oracle" / "package.json"
    if oracle_package.is_file():
        for required in (
            root / "engines" / "oracle" / "pnpm-lock.yaml",
            root / "engines" / "oracle" / "dist" / "bin" / "oracle-cli.js",
            root / "engines" / "oracle" / "dist" / "bin" / "oracle-mcp.js",
        ):
            if not required.is_file():
                errors.append(f"missing bundled Oracle runtime file: {required.relative_to(root).as_posix()}")

    skill = root / "skills" / "multi-aiweb-runtime" / "SKILL.md"
    if not skill.is_file():
        errors.append("missing skills/multi-aiweb-runtime/SKILL.md")
    else:
        text = skill.read_text(encoding="utf-8")
        if not text.startswith("---\n") or "\n---" not in text[4:]:
            errors.append("skill SKILL.md must contain YAML frontmatter")
        if "name:" not in text[:500] or "description:" not in text[:800]:
            errors.append("skill frontmatter must include name and description")

    if errors:
        print("Plugin validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Plugin validation passed: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
