from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

from .oracle_engine import bundled_oracle_engine_dir


def build_engine_command(args: Sequence[str], env: dict[str, str] | None = None) -> tuple[list[str], Path]:
    engine_dir = bundled_oracle_engine_dir(env)
    if engine_dir is None:
        raise FileNotFoundError(
            "Bundled Oracle engine is missing. Install/stage the plugin with engines/oracle or set MULTI_AIWEB_RUNTIME_ORACLE_COMMAND to a validated fallback command."
        )
    dist_entry = engine_dir / "dist" / "bin" / "oracle-cli.js"
    if dist_entry.exists():
        return ["node", str(dist_entry), *map(str, args)], engine_dir
    source_entry = engine_dir / "bin" / "oracle-cli.ts"
    if source_entry.exists():
        return ["corepack", "pnpm", "exec", "tsx", "bin/oracle-cli.ts", *map(str, args)], engine_dir
    raise FileNotFoundError(
        f"Bundled Oracle engine entrypoint not found under {engine_dir}. Expected dist/bin/oracle-cli.js or bin/oracle-cli.ts."
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        command, cwd = build_engine_command(args)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 127
    try:
        completed = subprocess.run(command, cwd=str(cwd), env=os.environ.copy(), shell=False)
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 127
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
