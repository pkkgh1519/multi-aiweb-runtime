#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

USER_PATH_RE = re.compile(r"C:[\\/]+Users[\\/]+([^\\/\s\"'`]+)", re.IGNORECASE)
ALLOWED_USER_PLACEHOLDERS = {"<user>", "<username>", "<your_windows_user>", "<you>"}
FORBIDDEN_TEXT = tuple(
    part.replace("|", "")
    for part in (
        ".codex/|plugins/cache",
        ".codex" + "\\" + "plugins" + "\\" + "cache",
        ".codex/|.tmp",
        ".codex" + "\\" + ".tmp",
    )
)
FORBIDDEN_DIRS = {"node_modules", "__pycache__", ".pytest_cache"}
TEXT_SUFFIXES = {
    "", ".json", ".md", ".py", ".ps1", ".toml", ".yaml", ".yml", ".txt", ".lock",
    ".gitignore", ".npmignore", ".tsx", ".ts", ".js", ".mjs", ".cjs",
}
SKIP_DIRS = {".git", ".venv", "venv"}


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {"LICENSE", "CHANGELOG"}


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    errors: list[str] = []

    for path in root.rglob("*"):
        rel = path.relative_to(root)
        parts = set(rel.parts)
        if parts & SKIP_DIRS:
            continue
        if path.is_dir() and path.name in FORBIDDEN_DIRS:
            errors.append(f"forbidden generated directory present: {rel}")
            continue
        if not path.is_file() or not is_text_candidate(path):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for marker in FORBIDDEN_TEXT:
            if marker in text:
                errors.append(f"forbidden local marker `{marker}` found in {rel}")
        for match in USER_PATH_RE.finditer(text):
            user_part = match.group(1).lower()
            if user_part not in ALLOWED_USER_PLACEHOLDERS:
                errors.append(f"forbidden concrete Windows user path `{match.group(0)}` found in {rel}")

    plugin_json = root / ".codex-plugin" / "plugin.json"
    if plugin_json.exists():
        manifest = json.loads(plugin_json.read_text(encoding="utf-8"))
        version = str(manifest.get("version", ""))
        if "+codex." in version:
            errors.append("source plugin version must not contain a local Codex cachebuster suffix")

    mcp_json = root / ".mcp.json"
    if mcp_json.exists():
        mcp_text = mcp_json.read_text(encoding="utf-8")
        if "C:/" in mcp_text or "C:\\" in mcp_text:
            errors.append("source .mcp.json must not contain an absolute Windows path")

    installer = root / "install.ps1"
    if installer.exists():
        installer_text = installer.read_text(encoding="utf-8")
        if "pnpm" in installer_text and "--prod" in installer_text and "--ignore-scripts" not in installer_text:
            errors.append("install.ps1 must use --ignore-scripts for Oracle production dependency restore")

    if errors:
        print("Portability validation failed:")
        for error in errors:
            print(f"- {error}")
        return 1
    print(f"Portability validation passed: {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
