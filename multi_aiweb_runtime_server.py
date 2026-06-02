from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
os.environ.setdefault("MULTI_AIWEB_RUNTIME_PLUGIN_ROOT", str(_HERE))
_INSTALLED_SRC = _HERE / "multi_aiweb_runtime" / "src"
if _INSTALLED_SRC.exists():
    sys.path.insert(0, str(_INSTALLED_SRC))

from multi_aiweb_runtime.mcp_server import main  # noqa: E402

if __name__ == "__main__":
    main()
