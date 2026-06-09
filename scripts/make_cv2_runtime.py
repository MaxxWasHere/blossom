#!/usr/bin/env python3
"""Produce the externalized OpenCV runtime bundle for Blossom.

Zips the installed ``cv2`` package (cv2.pyd + ffmpeg DLL + python files) into
``dist/runtime/cv2-runtime-<abi>.zip``, computes its SHA-256, and prints the
exact constant to paste into ``src/blossom_runtime_deps._CV2_SHA256`` plus the
release asset name to upload.

ABI WARNING: run this with the SAME CPython (version + arch) used to BUILD the
shipped exe, or the bundle's cv2.pyd will not import in the frozen app.

Usage:  py scripts/make_cv2_runtime.py
"""

from __future__ import annotations

import hashlib
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from blossom_runtime_deps import abi_key, cv2_archive_name  # noqa: E402


def main() -> int:
    try:
        import cv2  # type: ignore
    except ImportError:
        print("[make-cv2] ERROR: cv2 is not installed in this interpreter.")
        print("[make-cv2]        pip install opencv-python   (then rerun)")
        return 1

    cv2_pkg = Path(cv2.__file__).resolve().parent
    if cv2_pkg.name != "cv2":
        print(f"[make-cv2] ERROR: unexpected cv2 location: {cv2_pkg}")
        return 1

    key = abi_key()
    out_dir = ROOT / "dist" / "runtime"
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / cv2_archive_name(key)

    print(f"[make-cv2] interpreter ABI : {key}")
    print(f"[make-cv2] source package  : {cv2_pkg}")
    print(f"[make-cv2] writing archive : {archive}")

    if archive.exists():
        archive.unlink()

    file_count = 0
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for path in sorted(cv2_pkg.rglob("*")):
            if path.is_file():
                # Store as 'cv2/...' so the extracted root has cv2/ on it,
                # matching blossom_runtime_deps payload_subpath="cv2".
                arcname = "cv2/" + str(path.relative_to(cv2_pkg)).replace("\\", "/")
                zf.write(path, arcname)
                file_count += 1

    digest = hashlib.sha256()
    with archive.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    sha = digest.hexdigest().lower()
    size_mb = archive.stat().st_size / 1024 / 1024

    print(f"[make-cv2] files zipped    : {file_count}")
    print(f"[make-cv2] archive size    : {size_mb:.1f} MB")
    print(f"[make-cv2] SHA-256         : {sha}")
    print()
    print("=== paste into src/blossom_runtime_deps.py _CV2_SHA256 ===")
    print(f'    "{key}": "{sha}",')
    print()
    print("=== upload as a GitHub release asset (repo: MaxxWasHere/blossombeta) ===")
    print("    tag   : runtime-deps")
    print(f"    asset : {archive.name}")
    print(f"    file  : {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
