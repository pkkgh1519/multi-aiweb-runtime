from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Iterable

PERMISSION_SAFE_DEFAULT = "safe_default"
PERMISSION_REVIEW = "review"
PERMISSION_RESEARCH = "research"
PERMISSION_ELEVATED = "elevated"
PERMISSION_LEVELS = {
    PERMISSION_SAFE_DEFAULT,
    PERMISSION_REVIEW,
    PERMISSION_RESEARCH,
    PERMISSION_ELEVATED,
}
GLOB_ENABLED_LEVELS = {PERMISSION_REVIEW, PERMISSION_ELEVATED}

_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_GLOB_CHARS = set("*?[")
_SENSITIVE_EXACT_NAMES = {
    ".env",
    ".env.local",
    ".envrc",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "credentials",
    "credentials.json",
    "cookies",
    "cookies.json",
}
_SENSITIVE_SUFFIXES = {
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    ".keystore",
    ".jks",
}
_SENSITIVE_SEGMENTS = {
    ".git",
    ".oracle",
    ".ssh",
    "cookies",
    "local storage",
    "session storage",
    "profiles",
}


class OraclePolicyError(ValueError):
    """Raised when a requested Oracle scope contains blocked inputs."""


@dataclass(frozen=True)
class BlockedFile:
    input: str
    reason: str
    detail: str = ""

    def to_preview(self) -> dict[str, str]:
        payload = {"input": self.input, "reason": self.reason}
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass
class OracleScope:
    repo_root: Path
    permission_level: str
    allowed_files: list[Path] = field(default_factory=list)
    blocked_files: list[BlockedFile] = field(default_factory=list)

    def raise_if_blocked(self) -> None:
        if self.blocked_files:
            reasons = ", ".join(f"{item.input}: {item.reason}" for item in self.blocked_files)
            raise OraclePolicyError(f"Oracle policy blocked requested files: {reasons}")

    def to_preview(self) -> dict[str, object]:
        return {
            "permission_level": self.permission_level,
            "repo_root": str(self.repo_root),
            "allowed_files": [self._display_path(path) for path in self.allowed_files],
            "blocked_files": [item.to_preview() for item in self.blocked_files],
        }

    def _display_path(self, path: Path) -> str:
        try:
            return path.relative_to(self.repo_root).as_posix()
        except ValueError:
            return str(path)


def resolve_oracle_scope(
    *,
    files: Iterable[str] | None,
    repo_root: str | Path | None,
    permission_level: str = PERMISSION_SAFE_DEFAULT,
    max_files: int = 100,
) -> OracleScope:
    level = str(permission_level or PERMISSION_SAFE_DEFAULT)
    if level not in PERMISSION_LEVELS:
        raise ValueError(f"Unsupported Oracle permission_level: {permission_level}")
    if repo_root is None or not str(repo_root).strip():
        scope = OracleScope(repo_root=Path.cwd().resolve(), permission_level=level)
        scope.blocked_files.append(BlockedFile("", "repo_root_required"))
        return scope
    root = Path(repo_root).expanduser().resolve()
    scope = OracleScope(repo_root=root, permission_level=level)
    if not root.exists():
        scope.blocked_files.append(BlockedFile(str(repo_root or root), "repo_root_not_found"))
        return scope
    if not root.is_dir():
        scope.blocked_files.append(BlockedFile(str(repo_root or root), "repo_root_not_directory"))
        return scope
    if _is_broad_repo_root(root):
        scope.blocked_files.append(BlockedFile(str(root), "repo_root_too_broad"))
        return scope
    if not _has_git_marker(root):
        scope.blocked_files.append(BlockedFile(str(root), "repo_root_not_git_repo", "expected .git file or directory"))
        return scope
    seen: set[Path] = set()
    for raw_entry in files or []:
        raw = str(raw_entry or "").strip()
        if not raw:
            continue
        for allowed in _resolve_one(raw, root, level, scope):
            resolved = allowed.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            scope.allowed_files.append(resolved)
            if len(scope.allowed_files) > max_files:
                scope.blocked_files.append(BlockedFile(raw, "too_many_files", f"max_files={max_files}"))
                scope.allowed_files = scope.allowed_files[:max_files]
                return scope
    return scope


def _resolve_one(raw: str, repo_root: Path, level: str, scope: OracleScope) -> list[Path]:
    if _WINDOWS_ABSOLUTE_RE.match(raw) or raw.startswith("\\\\"):
        scope.blocked_files.append(BlockedFile(raw, "windows_absolute_path"))
        return []
    normalized = raw.replace("\\", "/")
    parts = PurePosixPath(normalized).parts
    if ".." in parts:
        scope.blocked_files.append(BlockedFile(raw, "path_traversal"))
        return []
    if normalized.startswith("~/"):
        scope.blocked_files.append(BlockedFile(raw, "home_path"))
        return []
    if _has_glob(normalized):
        if level not in GLOB_ENABLED_LEVELS:
            scope.blocked_files.append(BlockedFile(raw, "glob_not_allowed"))
            return []
        return _expand_glob(raw, normalized, repo_root, scope)
    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        candidate = repo_root / normalized
    return _accept_candidate(raw, candidate, repo_root, scope)


def _expand_glob(raw: str, normalized: str, repo_root: Path, scope: OracleScope) -> list[Path]:
    if normalized.startswith("/"):
        scope.blocked_files.append(BlockedFile(raw, "absolute_glob_not_allowed"))
        return []
    matches = sorted(path for path in repo_root.glob(normalized) if path.is_file())
    if not matches:
        scope.blocked_files.append(BlockedFile(raw, "no_match"))
        return []
    allowed: list[Path] = []
    for path in matches:
        allowed.extend(_accept_candidate(raw, path, repo_root, scope))
    return allowed


def _accept_candidate(raw: str, candidate: Path, repo_root: Path, scope: OracleScope) -> list[Path]:
    resolved = candidate.resolve()
    if not _is_relative_to(resolved, repo_root):
        scope.blocked_files.append(BlockedFile(raw, "outside_repo"))
        return []
    if not resolved.exists():
        scope.blocked_files.append(BlockedFile(raw, "no_match"))
        return []
    if not resolved.is_file():
        scope.blocked_files.append(BlockedFile(raw, "not_a_file"))
        return []
    rel = resolved.relative_to(repo_root)
    if _is_sensitive_path(rel):
        scope.blocked_files.append(BlockedFile(raw, "sensitive_path"))
        return []
    return [resolved]


def _has_glob(value: str) -> bool:
    return any(char in value for char in _GLOB_CHARS)


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _is_broad_repo_root(root: Path) -> bool:
    try:
        if root == Path(root.anchor).resolve():
            return True
    except OSError:
        return True
    try:
        return root == Path.home().resolve()
    except OSError:
        return False


def _has_git_marker(root: Path) -> bool:
    marker = root / ".git"
    return marker.is_dir() or marker.is_file()


def _is_sensitive_path(relative_path: Path) -> bool:
    lowered_parts = [part.lower() for part in relative_path.parts]
    if any(part in _SENSITIVE_SEGMENTS for part in lowered_parts):
        return True
    name = lowered_parts[-1]
    if name in _SENSITIVE_EXACT_NAMES or name.startswith(".env."):
        return True
    return any(name.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES)
