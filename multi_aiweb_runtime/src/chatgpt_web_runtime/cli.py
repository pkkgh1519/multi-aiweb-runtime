from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runtime import ChatGptWebRuntime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Multi-AI Web Runtime smoke CLI")
    parser.add_argument("--state-root", type=Path, default=None)
    parser.add_argument("--question", default="Reply with exactly: runtime smoke ok")
    parser.add_argument("--dry-run-response", default="runtime smoke ok")
    args = parser.parse_args(argv)
    runtime = ChatGptWebRuntime(state_root=args.state_root)
    result = runtime.start_run(question=args.question, dry_run=True, dry_run_response=args.dry_run_response)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
