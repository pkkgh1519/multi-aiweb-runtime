from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .event_model import RuntimeEvent


def make_run_id(prefix: str | None = None) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:8]
    return f"{prefix + '-' if prefix else ''}{stamp}_{suffix}"


def atomic_write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


class RunArtifacts:
    def __init__(self, run_dir: Path) -> None:
        self.run_dir = run_dir

    @property
    def run_json(self) -> Path:
        return self.run_dir / "run.json"

    @property
    def status_json(self) -> Path:
        return self.run_dir / "status.json"

    @property
    def prompt_txt(self) -> Path:
        return self.run_dir / "prompt.txt"

    @property
    def response_md(self) -> Path:
        return self.run_dir / "response.md"

    @property
    def events_jsonl(self) -> Path:
        return self.run_dir / "events.jsonl"

    def to_dict(self) -> dict[str, str]:
        return {
            "run_dir": str(self.run_dir),
            "run": str(self.run_json),
            "status": str(self.status_json),
            "prompt": str(self.prompt_txt),
            "response": str(self.response_md),
            "events": str(self.events_jsonl),
        }

    def append_event(self, event: RuntimeEvent) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=True)
        with self.events_jsonl.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
