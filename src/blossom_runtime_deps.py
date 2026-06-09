"""On-demand, hash-verified loader for heavy OPTIONAL runtime dependencies.

To keep the shipped exe lightweight, large optional native packages (currently
OpenCV / ``cv2``) are NOT bundled by PyInstaller. Instead they are downloaded
once, on first use of the feature that needs them, into the per-user cache
``%LOCALAPPDATA%\\Blossom\\runtime`` and imported from there.

SECURITY MODEL (read before editing)
------------------------------------
The cache lives in a user-writable directory and we load *native code* from it,
so the loader is deliberately strict:

* The downloaded archive's SHA-256 is verified against a hash PINNED in this
  (bundled, optionally PyArmor-obfuscated) source file BEFORE the archive is
  extracted and BEFORE the cache dir is ever placed on ``sys.path``.
* On every launch the cached archive is re-hashed; a tampered or truncated
  cached archive is detected, deleted, and re-fetched.
* If verification fails for any reason we refuse to load and return ``None`` so
  the caller falls back to its pure-Python (NumPy) path. We never import
  unverified native code.

This protects against MITM / supply-chain tampering of the download. It does not
(and cannot) stop a user from replacing files on their own machine — but ``cv2``
is not a security component (it only speeds up fishing colour detection and has a
full NumPy fallback), so local self-tampering grants nothing that running from
source wouldn't already.

ABI / VERSION CAVEAT
--------------------
A native extension (``cv2.pyd``) must match the EXACT CPython version + arch of
the frozen build (e.g. CPython 3.14, win-amd64). The cache dir and the download
URL are both keyed by ``py{major}{minor}-{arch}`` so a mismatched cache is never
used, and a hosted bundle built for the wrong interpreter is simply not found.
When the build's Python is upgraded, rebuild + re-host the bundle and update the
pinned hash below.
"""

from __future__ import annotations

import hashlib
import shutil
import sys
import sysconfig
import threading
import zipfile
from pathlib import Path
from typing import Any, Callable

from blossom_dirs import ensure_runtime_deps_dir

ProgressCb = Callable[[int, int], None]

# --------------------------------------------------------------------------- #
# Platform / ABI key
# --------------------------------------------------------------------------- #
def _arch_tag() -> str:
    plat = (sysconfig.get_platform() or "").lower()
    if "amd64" in plat or "x86_64" in plat or "win64" in plat:
        return "win-amd64"
    if "win32" in plat:
        return "win-win32"
    # Fall back to the raw platform string so a mismatch is obvious and unique.
    return plat.replace("-", "_") or "unknown"


def _python_tag() -> str:
    return f"py{sys.version_info.major}{sys.version_info.minor}"


def abi_key() -> str:
    """e.g. 'py314-win-amd64' — uniquely identifies a compatible native build."""
    return f"{_python_tag()}-{_arch_tag()}"


# --------------------------------------------------------------------------- #
# OpenCV (cv2) descriptor
# --------------------------------------------------------------------------- #
# Hosted bundle: a zip whose top level is a ``cv2/`` package directory
# (cv2.pyd + the ffmpeg DLL + cv2 python files). Upload one asset per ABI key.
#
# Release asset URL (user must upload the produced zip here):
#   https://github.com/MaxxWasHere/blossombeta/releases/download/runtime-deps/cv2-runtime-<abi_key>.zip
_CV2_BASE_URL = (
    "https://github.com/MaxxWasHere/blossombeta/releases/download/runtime-deps"
)

# Pinned SHA-256 of the archive, keyed by ABI. Filled in by scripts/make_cv2_runtime.py
# (or by hand) after the bundle is produced. An ABI with no pinned hash is treated
# as "unavailable" and the caller falls back to NumPy.
_CV2_SHA256: dict[str, str] = {
    "py314-win-amd64": "5bcb100e4c49b2f7fa842dd16e2bd781950040f454834c2b0da2329aee41d941",
}


def cv2_archive_name(key: str | None = None) -> str:
    return f"cv2-runtime-{key or abi_key()}.zip"


def cv2_archive_url(key: str | None = None) -> str:
    return f"{_CV2_BASE_URL}/{cv2_archive_name(key)}"


def cv2_pinned_hash(key: str | None = None) -> str:
    return _CV2_SHA256.get(key or abi_key(), "").strip().lower()


# --------------------------------------------------------------------------- #
# Generic verified fetch + extract
# --------------------------------------------------------------------------- #
def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().lower()


def _safe_rmtree(path: Path) -> None:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        elif path.exists():
            path.unlink()
    except OSError:
        pass


def _is_within(base: Path, target: Path) -> bool:
    try:
        target.resolve().relative_to(base.resolve())
        return True
    except ValueError:
        return False


def _extract_zip_safely(archive: Path, dest_dir: Path) -> bool:
    """Extract ``archive`` into ``dest_dir``, rejecting path-traversal entries."""
    try:
        with zipfile.ZipFile(archive) as zf:
            for member in zf.namelist():
                out = dest_dir / member
                if not _is_within(dest_dir, out):
                    print(f"[runtime-deps] refusing unsafe zip entry: {member!r}")
                    return False
            zf.extractall(dest_dir)
        return True
    except (OSError, zipfile.BadZipFile) as error:
        print(f"[runtime-deps] extract failed for {archive.name}: {error}")
        return False


def _ensure_verified_payload(
    *,
    label: str,
    url: str,
    pinned_sha256: str,
    cache_subdir: str,
    payload_subpath: str,
    progress_cb: ProgressCb | None,
    offline_zip: Path | None = None,
) -> Path | None:
    """Return a verified, extracted payload dir, downloading if needed.

    ``cache_subdir`` is created under the runtime deps dir and holds the
    downloaded ``<name>.zip`` plus its extracted contents. ``payload_subpath`` is
    the path (relative to the extracted root) that must exist for success, e.g.
    ``"cv2"``. Returns the extracted root dir (the one to put on sys.path), or
    ``None`` on any failure (caller should fall back).

    ``offline_zip`` is an optional user-supplied archive (e.g. dropped into the
    runtime folder for an air-gapped install). It is consumed ONLY if its
    SHA-256 matches ``pinned_sha256`` exactly — the same security gate as the
    network path — so an unverified local file is never trusted.
    """
    if not pinned_sha256:
        print(
            f"[runtime-deps] {label}: no pinned hash for this Python/arch "
            f"({abi_key()}); skipping download, using fallback."
        )
        return None

    try:
        base = ensure_runtime_deps_dir() / cache_subdir
        base.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        print(f"[runtime-deps] {label}: cannot create cache dir: {error}")
        return None

    archive = base / "payload.zip"
    extract_root = base / "extracted"
    payload = extract_root / payload_subpath

    # Fast path: cached archive still matches the pinned hash and is extracted.
    if archive.is_file():
        try:
            if _sha256_file(archive) == pinned_sha256:
                if payload.exists():
                    return extract_root
                # Verified archive present but extraction missing/partial: redo it.
                _safe_rmtree(extract_root)
                extract_root.mkdir(parents=True, exist_ok=True)
                if _extract_zip_safely(archive, extract_root) and payload.exists():
                    return extract_root
                print(f"[runtime-deps] {label}: re-extract failed; refetching.")
            else:
                print(f"[runtime-deps] {label}: cached archive hash mismatch; refetching.")
        except OSError:
            pass
        _safe_rmtree(archive)
        _safe_rmtree(extract_root)

    # Offline install: a user-supplied archive next to the cache. Verified by the
    # SAME pinned hash as the download, then promoted into the cache so the normal
    # extract path runs. A mismatched local file is ignored (we still try network).
    if offline_zip is not None:
        try:
            if offline_zip.is_file() and _sha256_file(offline_zip) == pinned_sha256:
                _safe_rmtree(extract_root)
                shutil.copyfile(offline_zip, archive)
                extract_root.mkdir(parents=True, exist_ok=True)
                if _extract_zip_safely(archive, extract_root) and payload.exists():
                    print(f"[runtime-deps] {label}: installed from local archive {offline_zip.name}")
                    return extract_root
                print(f"[runtime-deps] {label}: local archive extract failed; trying download.")
                _safe_rmtree(archive)
                _safe_rmtree(extract_root)
            elif offline_zip.is_file():
                print(
                    f"[runtime-deps] {label}: local archive {offline_zip.name} hash "
                    f"mismatch; ignoring it and trying download."
                )
        except OSError as error:
            print(f"[runtime-deps] {label}: local archive unusable ({error}); trying download.")

    # Download (lazy import so a missing updater never breaks the fallback path).
    try:
        from blossom_updater import download_file
    except Exception as error:  # noqa: BLE001
        print(f"[runtime-deps] {label}: updater unavailable ({error}); using fallback.")
        return None

    tmp = base / "payload.zip.part"
    _safe_rmtree(tmp)
    print(f"[runtime-deps] {label}: downloading from {url}")
    try:
        download_file(url, tmp, progress_cb=progress_cb)
    except Exception as error:  # noqa: BLE001 - offline / 404 / network all fall back
        print(f"[runtime-deps] {label}: download failed ({error}); using fallback.")
        _safe_rmtree(tmp)
        return None

    # MANDATORY: verify before extracting or touching sys.path.
    try:
        actual = _sha256_file(tmp)
    except OSError as error:
        print(f"[runtime-deps] {label}: cannot hash download ({error}); using fallback.")
        _safe_rmtree(tmp)
        return None

    if actual != pinned_sha256:
        print(
            f"[runtime-deps] {label}: SHA-256 mismatch (got {actual}, "
            f"expected {pinned_sha256}); refusing to load, deleting, using fallback."
        )
        _safe_rmtree(tmp)
        return None

    try:
        tmp.replace(archive)
    except OSError as error:
        print(f"[runtime-deps] {label}: cannot finalize archive ({error}); using fallback.")
        _safe_rmtree(tmp)
        return None

    _safe_rmtree(extract_root)
    extract_root.mkdir(parents=True, exist_ok=True)
    if not _extract_zip_safely(archive, extract_root) or not payload.exists():
        print(f"[runtime-deps] {label}: extraction incomplete; using fallback.")
        _safe_rmtree(extract_root)
        return None

    print(f"[runtime-deps] {label}: verified and cached -> {extract_root}")
    return extract_root


# --------------------------------------------------------------------------- #
# OpenCV public API
# --------------------------------------------------------------------------- #
_cv2_lock = threading.Lock()
_cv2_module: Any | None = None
_cv2_attempted = False


def _cv2_cache_dirs(key: str | None = None) -> tuple[Path, Path, Path]:
    """Return (cache_base, cached_archive, extracted_payload) for the ABI key."""
    base = ensure_runtime_deps_dir() / f"cv2-{key or abi_key()}"
    return base, base / "payload.zip", base / "extracted" / "cv2"


def _cv2_offline_zip(key: str | None = None) -> Path:
    """User-droppable offline archive: <runtime-deps>/cv2-runtime-<abi>.zip."""
    return ensure_runtime_deps_dir() / cv2_archive_name(key)


def cv2_status() -> dict[str, Any]:
    """Report whether the verified cv2 runtime is present, WITHOUT downloading.

    Returns a dict with ``state`` in ``{"installed", "not_installed",
    "unavailable"}`` plus optional ``version``, ``path``, ``size`` and
    ``message``. ``unavailable`` means no SHA-256 is pinned for this Python/arch,
    so no verified component can be installed (fishing uses its NumPy fallback).
    """
    key = abi_key()
    pinned = cv2_pinned_hash(key)

    # Already imported this process (dev cv2, or installed earlier this session).
    if _cv2_module is not None:
        return {
            "state": "installed",
            "abi": key,
            "version": getattr(_cv2_module, "__version__", None),
            "path": getattr(_cv2_module, "__file__", None),
        }

    if not pinned:
        # Maybe a system/dev cv2 is importable even though we have no pinned build.
        try:
            import cv2 as _dev  # type: ignore

            return {
                "state": "installed",
                "abi": key,
                "version": getattr(_dev, "__version__", None),
                "path": getattr(_dev, "__file__", None),
                "message": "Using OpenCV from this Python environment.",
            }
        except ImportError:
            pass
        return {
            "state": "unavailable",
            "abi": key,
            "message": "No verified vision component is published for this build yet.",
        }

    # Cached + verified archive already extracted? -> installed (no download).
    try:
        _base, archive, payload = _cv2_cache_dirs(key)
        if archive.is_file() and payload.exists() and _sha256_file(archive) == pinned:
            try:
                size = archive.stat().st_size
            except OSError:
                size = None
            return {"state": "installed", "abi": key, "path": str(payload), "size": size}
    except OSError:
        pass

    # A dev cv2 may still be importable even with a pinned build defined.
    try:
        import cv2 as _dev2  # type: ignore

        return {
            "state": "installed",
            "abi": key,
            "version": getattr(_dev2, "__version__", None),
            "path": getattr(_dev2, "__file__", None),
            "message": "Using OpenCV from this Python environment.",
        }
    except ImportError:
        pass

    return {"state": "not_installed", "abi": key}


def ensure_opencv(
    progress_cb: ProgressCb | None = None, *, force: bool = False
) -> Any | None:
    """Return the ``cv2`` module, downloading + verifying it on first use.

    Thread-safe and idempotent: the heavy work (download/verify/extract/import)
    happens at most once per process. Returns ``None`` on any failure so callers
    can use their NumPy fallback. Never imports unverified native code.

    ``progress_cb(downloaded, total)`` is forwarded to the downloader so a UI can
    show a "downloading vision component" state; it must not raise or block.

    ``force=True`` clears the "already tried and failed" guard so the explicit
    in-app installer can retry a download that previously 404'd (e.g. before the
    asset was uploaded) without restarting the app.
    """
    global _cv2_module, _cv2_attempted

    if _cv2_module is not None:
        return _cv2_module

    with _cv2_lock:
        if _cv2_module is not None:
            return _cv2_module

        # If cv2 is importable already (running from source / dev with cv2
        # installed, or a future build that bundles it), just use it.
        try:
            import cv2 as _already  # type: ignore

            _cv2_module = _already
            _cv2_attempted = True
            return _cv2_module
        except ImportError:
            pass

        if _cv2_attempted and not force:
            return None
        _cv2_attempted = True

        extract_root = _ensure_verified_payload(
            label="OpenCV",
            url=cv2_archive_url(),
            pinned_sha256=cv2_pinned_hash(),
            cache_subdir=f"cv2-{abi_key()}",
            payload_subpath="cv2",
            progress_cb=progress_cb,
            offline_zip=_cv2_offline_zip(),
        )
        if extract_root is None:
            return None

        root_str = str(extract_root)
        if root_str not in sys.path:
            sys.path.insert(0, root_str)
        try:
            import cv2 as _loaded  # type: ignore

            _cv2_module = _loaded
            print("[runtime-deps] OpenCV loaded from AppData cache.")
            return _cv2_module
        except Exception as error:  # noqa: BLE001 - import/ABI failure -> fallback
            print(
                f"[runtime-deps] OpenCV import failed after verify "
                f"({error}); using NumPy fallback. (ABI {abi_key()})"
            )
            try:
                sys.path.remove(root_str)
            except ValueError:
                pass
            return None
