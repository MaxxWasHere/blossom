#!/usr/bin/env python3
"""Produce the externalized WinOCR runtime bundle for Blossom.

Installs ``winocr==0.0.15`` (and its ``winrt_*`` dependencies) if needed,
zips those packages into ``dist/runtime/winocr-runtime-<abi>.zip``, computes
SHA-256, and updates ``assets/runtime_manifest.json``.

ABI WARNING: run this with the SAME CPython (version + arch) used to BUILD the
shipped exe, or the bundle may not import in the frozen app.

Usage:  py scripts/make_winocr_runtime.py
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "assets" / "runtime_manifest.json"
WINOCR_VERSION = "0.0.15"

sys.path.insert(0, str(ROOT / "src"))

from blossom_runtime_deps import abi_key, component_archive_name  # noqa: E402


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def _update_manifest(key: str, sha: str) -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    comp = manifest.setdefault("components", {}).setdefault("winocr", {})
    hashes = comp.setdefault("sha256", {})
    if not isinstance(hashes, dict):
        raise SystemExit("[make-winocr] ERROR: manifest winocr.sha256 is not an object")
    hashes[key] = sha
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"[make-winocr] updated {MANIFEST_PATH}")


def _ensure_winocr() -> None:
    try:
        import winocr  # type: ignore  # noqa: F401
    except ImportError:
        print(f"[make-winocr] installing winocr=={WINOCR_VERSION} …")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", f"winocr=={WINOCR_VERSION}"],
            check=True,
        )


def _winocr_archive_entries() -> list[tuple[Path, str]]:
    """Return (source_path, arcname) pairs for the runtime zip."""
    import winocr  # type: ignore

    entries: list[tuple[Path, str]] = []
    winocr_file = Path(winocr.__file__).resolve()
    site_packages = winocr_file.parent

    if winocr_file.name == "winocr.py":
        # Single-module wheel: store as winocr/__init__.py so payload_subpath
        # "winocr" exists and ``import winocr`` works from the extract root.
        entries.append((winocr_file, "winocr/__init__.py"))
    elif winocr_file.parent.name == "winocr":
        winocr_pkg = winocr_file.parent
        for path in sorted(winocr_pkg.rglob("*")):
            if path.is_file():
                rel = path.relative_to(winocr_pkg)
                entries.append((path, f"winocr/{rel.as_posix()}"))
    else:
        print(f"[make-winocr] ERROR: unexpected winocr location: {winocr_file}")
        return []

    for child in sorted(site_packages.iterdir()):
        name = child.name.lower()
        if child.is_dir() and (name == "winrt" or name.startswith("winrt_")):
            top_name = child.name
            for path in sorted(child.rglob("*")):
                if path.is_file():
                    rel = path.relative_to(child)
                    entries.append((path, f"{top_name}/{rel.as_posix()}"))
    return entries


def main() -> int:
    _ensure_winocr()
    entries = _winocr_archive_entries()
    if not entries:
        print("[make-winocr] ERROR: no winocr/winrt packages found")
        return 1

    key = abi_key()
    out_dir = ROOT / "dist" / "runtime"
    out_dir.mkdir(parents=True, exist_ok=True)
    archive = out_dir / component_archive_name("winocr", key)

    top_levels = sorted({arc.split("/", 1)[0] for _, arc in entries})
    print(f"[make-winocr] interpreter ABI : {key}")
    print(f"[make-winocr] zip top-levels  : {', '.join(top_levels)}")
    print(f"[make-winocr] writing archive : {archive}")

    if archive.exists():
        archive.unlink()

    file_count = 0
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for source, arcname in entries:
            zf.write(source, arcname)
            file_count += 1

    sha = _sha256_file(archive)
    size_mb = archive.stat().st_size / 1024 / 1024

    print(f"[make-winocr] files zipped    : {file_count}")
    print(f"[make-winocr] archive size    : {size_mb:.1f} MB")
    print(f"[make-winocr] SHA-256         : {sha}")

    _update_manifest(key, sha)

    print()
    print("=== upload as a GitHub release asset (repo: MaxxWasHere/blossombeta) ===")
    print("    tag   : runtime-deps")
    print(f"    asset : {archive.name}")
    print(f"    file  : {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
