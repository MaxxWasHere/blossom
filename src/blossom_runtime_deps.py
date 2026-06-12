"""On-demand, hash-verified loader for heavy OPTIONAL runtime dependencies.

Large optional native packages (OpenCV / ``cv2``, WinOCR / ``winocr``) are NOT
bundled by PyInstaller. They are downloaded into ``%LOCALAPPDATA%\\Blossom\\runtime``
and imported from there. Component versions and SHA-256 pins live in the bundled
``assets/runtime_manifest.json``; ``sync_runtime_manifest()`` keeps the cache
aligned on boot and after updates.

SECURITY MODEL (read before editing)
------------------------------------
* Downloaded archives are SHA-256 verified against pins in the manifest BEFORE
  extraction and BEFORE the cache dir is placed on ``sys.path``.
* Cached archives are re-hashed on every sync; tampered copies are deleted and
  re-fetched.
* Verification failure returns ``None`` so callers fall back gracefully. We never
  import unverified native code.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import sysconfig
import threading
import zipfile
from pathlib import Path
from typing import Any, Callable

from blossom_dirs import RUNTIME_MANIFEST_STATE, dev_repo_root, ensure_runtime_deps_dir

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
    return plat.replace("-", "_") or "unknown"


def _python_tag() -> str:
    return f"py{sys.version_info.major}{sys.version_info.minor}"


def abi_key() -> str:
    """e.g. 'py314-win-amd64' — uniquely identifies a compatible native build."""
    return f"{_python_tag()}-{_arch_tag()}"


# --------------------------------------------------------------------------- #
# Manifest
# --------------------------------------------------------------------------- #
_manifest_cache: dict[str, Any] | None = None


def _bundle_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", dev_repo_root()))
    return dev_repo_root()


def manifest_path() -> Path:
    return _bundle_root() / "assets" / "runtime_manifest.json"


def load_manifest(*, force_reload: bool = False) -> dict[str, Any]:
    global _manifest_cache
    if _manifest_cache is not None and not force_reload:
        return _manifest_cache
    path = manifest_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(f"[runtime-deps] manifest unreadable ({path}): {error}")
        data = {"version": 0, "components": {}}
    if not isinstance(data, dict):
        data = {"version": 0, "components": {}}
    _manifest_cache = data
    return data


def _component_spec(component_id: str) -> dict[str, Any] | None:
    manifest = load_manifest()
    components = manifest.get("components") or {}
    spec = components.get(component_id)
    return spec if isinstance(spec, dict) else None


def component_archive_name(component_id: str, key: str | None = None) -> str:
    spec = _component_spec(component_id) or {}
    template = str(spec.get("archive") or f"{component_id}-runtime-{{abi}}.zip")
    return template.replace("{abi}", key or abi_key())


def component_archive_url(component_id: str, key: str | None = None) -> str:
    manifest = load_manifest()
    base = str(manifest.get("base_url") or "").rstrip("/")
    return f"{base}/{component_archive_name(component_id, key)}"


def component_pinned_hash(component_id: str, key: str | None = None) -> str:
    spec = _component_spec(component_id) or {}
    hashes = spec.get("sha256") or {}
    if not isinstance(hashes, dict):
        return ""
    return str(hashes.get(key or abi_key(), "")).strip().lower()


def component_cache_subdir(component_id: str, key: str | None = None) -> str:
    spec = _component_spec(component_id) or {}
    template = str(spec.get("cache_subdir") or f"{component_id}-{{abi}}")
    return template.replace("{abi}", key or abi_key())


def component_payload_subpath(component_id: str) -> str:
    spec = _component_spec(component_id) or {}
    return str(spec.get("payload_subpath") or component_id)


def component_label(component_id: str) -> str:
    spec = _component_spec(component_id) or {}
    return str(spec.get("label") or component_id)


# Backward-compatible cv2 helpers (manifest-backed).
def cv2_archive_name(key: str | None = None) -> str:
    return component_archive_name("cv2", key)


def cv2_archive_url(key: str | None = None) -> str:
    return component_archive_url("cv2", key)


def cv2_pinned_hash(key: str | None = None) -> str:
    return component_pinned_hash("cv2", key)


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

    if archive.is_file():
        try:
            if _sha256_file(archive) == pinned_sha256:
                if payload.exists():
                    return extract_root
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
    except Exception as error:  # noqa: BLE001
        print(f"[runtime-deps] {label}: download failed ({error}); using fallback.")
        _safe_rmtree(tmp)
        return None

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


def _read_manifest_state() -> dict[str, Any]:
    try:
        if RUNTIME_MANIFEST_STATE.is_file():
            data = json.loads(RUNTIME_MANIFEST_STATE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {"manifest_version": 0, "components": {}}


def _write_manifest_state(state: dict[str, Any]) -> None:
    try:
        ensure_runtime_deps_dir()
        RUNTIME_MANIFEST_STATE.write_text(
            json.dumps(state, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as error:
        print(f"[runtime-deps] could not write manifest state: {error}")


def _component_needs_sync(component_id: str, *, force: bool) -> bool:
    if force:
        return True
    manifest = load_manifest()
    spec = _component_spec(component_id)
    if not spec:
        return False
    pinned = component_pinned_hash(component_id)
    if not pinned:
        return False
    state = _read_manifest_state()
    installed = (state.get("components") or {}).get(component_id) or {}
    manifest_version = int(manifest.get("version") or 0)
    if int(state.get("manifest_version") or 0) != manifest_version:
        return True
    if str(installed.get("version") or "") != str(spec.get("version") or ""):
        return True
    if str(installed.get("abi") or "") != abi_key():
        return True
    key = abi_key()
    base = ensure_runtime_deps_dir() / component_cache_subdir(component_id, key)
    archive = base / "payload.zip"
    payload = base / "extracted" / component_payload_subpath(component_id)
    if not archive.is_file() or not payload.exists():
        return True
    if component_id == "winocr" and not _winocr_payload_present(payload.parent):
        return True
    try:
        return _sha256_file(archive) != pinned
    except OSError:
        return True


def _sync_component(
    component_id: str,
    *,
    progress_cb: ProgressCb | None,
    force: bool,
) -> dict[str, Any]:
    label = component_label(component_id)
    pinned = component_pinned_hash(component_id)
    if not pinned:
        return {"id": component_id, "state": "unavailable", "abi": abi_key()}

    key = abi_key()
    offline = ensure_runtime_deps_dir() / component_archive_name(component_id, key)
    extract_root = _ensure_verified_payload(
        label=label,
        url=component_archive_url(component_id, key),
        pinned_sha256=pinned,
        cache_subdir=component_cache_subdir(component_id, key),
        payload_subpath=component_payload_subpath(component_id),
        progress_cb=progress_cb,
        offline_zip=offline,
    )
    if extract_root is None:
        return {"id": component_id, "state": "failed", "abi": key}

    spec = _component_spec(component_id) or {}
    state = _read_manifest_state()
    manifest = load_manifest()
    components = dict(state.get("components") or {})
    components[component_id] = {
        "version": str(spec.get("version") or ""),
        "abi": key,
    }
    state["manifest_version"] = int(manifest.get("version") or 0)
    state["components"] = components
    _write_manifest_state(state)
    return {"id": component_id, "state": "installed", "abi": key, "path": str(extract_root)}


def sync_runtime_manifest(
    progress_cb: ProgressCb | None = None,
    *,
    components: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Ensure all manifest components are present and up to date.

    Never raises; returns a summary dict. Optional components that fail to
    download do not block callers.
    """
    manifest = load_manifest()
    all_ids = list((manifest.get("components") or {}).keys())
    target = components if components is not None else all_ids
    results: list[dict[str, Any]] = []
    for component_id in target:
        if component_id not in all_ids:
            continue
        if not _component_needs_sync(component_id, force=force):
            results.append({"id": component_id, "state": "installed", "abi": abi_key()})
            continue
        try:
            results.append(_sync_component(component_id, progress_cb=progress_cb, force=force))
        except Exception as error:  # noqa: BLE001
            print(f"[runtime-deps] sync {component_id} failed: {error}")
            results.append({"id": component_id, "state": "failed", "error": str(error)})
    return {"ok": True, "components": results, "manifest_version": manifest.get("version")}


def _prepend_sys_path(extract_root: Path) -> None:
    root_str = str(extract_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


# --------------------------------------------------------------------------- #
# OpenCV public API
# --------------------------------------------------------------------------- #
_cv2_lock = threading.Lock()
_cv2_module: Any | None = None
_cv2_attempted = False


def _cv2_cache_dirs(key: str | None = None) -> tuple[Path, Path, Path]:
    base = ensure_runtime_deps_dir() / component_cache_subdir("cv2", key)
    return base, base / "payload.zip", base / "extracted" / "cv2"


def _cv2_offline_zip(key: str | None = None) -> Path:
    return ensure_runtime_deps_dir() / cv2_archive_name(key)


def cv2_status() -> dict[str, Any]:
    key = abi_key()
    pinned = cv2_pinned_hash(key)

    if _cv2_module is not None:
        return {
            "state": "installed",
            "abi": key,
            "version": getattr(_cv2_module, "__version__", None),
            "path": getattr(_cv2_module, "__file__", None),
        }

    if not pinned:
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
    global _cv2_module, _cv2_attempted

    if _cv2_module is not None:
        return _cv2_module

    with _cv2_lock:
        if _cv2_module is not None:
            return _cv2_module

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
            cache_subdir=component_cache_subdir("cv2"),
            payload_subpath="cv2",
            progress_cb=progress_cb,
            offline_zip=_cv2_offline_zip(),
        )
        if extract_root is None:
            return None

        _prepend_sys_path(extract_root)
        try:
            import cv2 as _loaded  # type: ignore

            _cv2_module = _loaded
            print("[runtime-deps] OpenCV loaded from AppData cache.")
            return _cv2_module
        except Exception as error:  # noqa: BLE001
            print(
                f"[runtime-deps] OpenCV import failed after verify "
                f"({error}); using NumPy fallback. (ABI {abi_key()})"
            )
            try:
                sys.path.remove(str(extract_root))
            except ValueError:
                pass
            return None


# --------------------------------------------------------------------------- #
# WinOCR public API
# --------------------------------------------------------------------------- #
_winocr_lock = threading.Lock()
_winocr_ready = False
_winocr_attempted = False


def _winocr_cache_dirs(key: str | None = None) -> tuple[Path, Path, Path]:
    base = ensure_runtime_deps_dir() / component_cache_subdir("winocr", key)
    extract_root = base / "extracted"
    payload = extract_root / component_payload_subpath("winocr")
    return base, base / "payload.zip", payload


def _winocr_payload_present(extract_root: Path) -> bool:
    """True when a verified WinOCR tree exists under the extract root."""
    payload = extract_root / component_payload_subpath("winocr")
    if payload.is_file():
        return True
    if payload.is_dir():
        if (payload / "__init__.py").is_file():
            return True
        return any(payload.iterdir())
    init_only = extract_root / "winocr" / "__init__.py"
    return init_only.is_file()


def _winocr_offline_zip(key: str | None = None) -> Path:
    return ensure_runtime_deps_dir() / component_archive_name("winocr", key)


def winocr_status() -> dict[str, Any]:
    key = abi_key()
    pinned = component_pinned_hash("winocr")

    if _winocr_ready:
        return {"state": "installed", "abi": key}

    if not pinned:
        try:
            import winocr  # type: ignore

            return {
                "state": "installed",
                "abi": key,
                "version": getattr(winocr, "__version__", None),
                "message": "Using WinOCR from this Python environment.",
            }
        except ImportError:
            pass
        return {
            "state": "unavailable",
            "abi": key,
            "message": "No verified WinOCR bundle is published for this build yet.",
        }

    try:
        _base, archive, payload = _winocr_cache_dirs(key)
        extract_root = payload.parent
        if (
            archive.is_file()
            and _winocr_payload_present(extract_root)
            and _sha256_file(archive) == pinned
        ):
            try:
                size = archive.stat().st_size
            except OSError:
                size = None
            return {"state": "installed", "abi": key, "path": str(payload), "size": size}
    except OSError:
        pass

    state = _read_manifest_state()
    installed = (state.get("components") or {}).get("winocr") or {}
    if str(installed.get("abi") or "") == key and str(installed.get("version") or ""):
        try:
            _base, archive, payload = _winocr_cache_dirs(key)
            if archive.is_file() and _winocr_payload_present(payload.parent):
                return {
                    "state": "installed",
                    "abi": key,
                    "path": str(payload),
                    "message": "WinOCR runtime synced.",
                }
        except OSError:
            pass

    try:
        import winocr as _dev  # type: ignore

        return {
            "state": "installed",
            "abi": key,
            "version": getattr(_dev, "__version__", None),
            "message": "Using WinOCR from this Python environment.",
        }
    except ImportError:
        pass

    return {"state": "not_installed", "abi": key}


def ensure_winocr(
    progress_cb: ProgressCb | None = None, *, force: bool = False
) -> bool:
    """Return True when winocr is importable (cached or dev install)."""
    global _winocr_ready, _winocr_attempted

    if _winocr_ready:
        return True

    with _winocr_lock:
        if _winocr_ready:
            return True

        try:
            import winocr  # type: ignore  # noqa: F401

            _winocr_ready = True
            _winocr_attempted = True
            return True
        except ImportError:
            pass

        if _winocr_attempted and not force:
            return False
        _winocr_attempted = True

        extract_root = _ensure_verified_payload(
            label="WinOCR",
            url=component_archive_url("winocr"),
            pinned_sha256=component_pinned_hash("winocr"),
            cache_subdir=component_cache_subdir("winocr"),
            payload_subpath="winocr",
            progress_cb=progress_cb,
            offline_zip=_winocr_offline_zip(),
        )
        if extract_root is None:
            return False

        _prepend_sys_path(extract_root)
        try:
            import winocr  # type: ignore  # noqa: F401

            _winocr_ready = True
            print("[runtime-deps] WinOCR loaded from AppData cache.")
            return True
        except Exception as error:  # noqa: BLE001
            print(f"[runtime-deps] WinOCR import failed after verify ({error}).")
            try:
                sys.path.remove(str(extract_root))
            except ValueError:
                pass
            return False
