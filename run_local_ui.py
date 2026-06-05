"""Launch Blossom — root entry shim (implementation in src/run_local_ui.py)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_impl_path = _SRC / "run_local_ui.py"
_spec = importlib.util.spec_from_file_location("blossom_run_local_ui_impl", _impl_path)
if _spec is None or _spec.loader is None:
    raise RuntimeError(f"Could not load Blossom UI from {_impl_path}")
_impl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_impl)
main = _impl.main

if __name__ == "__main__":
    raise SystemExit(main())
