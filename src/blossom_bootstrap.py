"""Fixed-name Blossom launchers that sync app payload + runtime deps from GitHub.

Build outputs:
  Blossom.exe       — stable channel launcher
  Blossom-beta.exe  — beta channel launcher

On start: compare GitHub latest release to %LOCALAPPDATA%\\Blossom\\app\\{channel}\\
current.json, download a newer Blossom-<version>.exe when needed, sync runtime
manifest components, then launch the payload with BLOSSOM_MANAGED=1.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Protocol

from blossom_dirs import app_channel_dir, current_app_json_path, ensure_app_data_dirs, ui_ready_marker_path
from blossom_runtime_deps import sync_runtime_manifest
from blossom_updater import (
    BETA_VERSION,
    GITHUB_OWNER,
    GITHUB_REPO,
    GITHUB_REPO_BETA,
    MIN_DOWNLOAD_BYTES,
    STABLE_VERSION,
    download_file,
    fetch_latest_beta_release,
    fetch_latest_stable_release,
    version_gt,
    versioned_exe_name,
)

ProgressCb = Callable[[int, int], None]

try:
    import blossom_build_info as _build_info

    BOOTSTRAP_CHANNEL = str(_build_info.BUILD_CHANNEL or "stable").strip().lower()
    BOOTSTRAP_VERSION = str(_build_info.APP_VERSION or "").strip()
except ImportError:
    BOOTSTRAP_CHANNEL = "stable"
    BOOTSTRAP_VERSION = ""

UI_READY_TIMEOUT_SEC = 120.0
UI_READY_POLL_SEC = 0.2


class BootstrapReporter(Protocol):
    def set_message(self, message: str) -> None: ...
    def set_version(self, version: str) -> None: ...
    def set_progress(self, downloaded: int, total: int) -> None: ...
    def set_indeterminate(self, active: bool = True) -> None: ...
    def set_phase(self, phase: str) -> None: ...
    def show_error(self, message: str) -> None: ...


class _NullReporter:
    def set_message(self, message: str) -> None:
        print(f"[bootstrap] {message}")

    def set_version(self, version: str) -> None:
        pass

    def set_progress(self, downloaded: int, total: int) -> None:
        if total > 0:
            pct = int((downloaded / total) * 100)
            print(f"[bootstrap] progress {pct}% ({downloaded}/{total})")

    def set_indeterminate(self, active: bool = True) -> None:
        pass

    def set_phase(self, phase: str) -> None:
        pass

    def show_error(self, message: str) -> None:
        print(f"[bootstrap] ERROR: {message}")


def bootstrap_channel() -> str:
    ch = BOOTSTRAP_CHANNEL.lower()
    return "beta" if ch == "beta" else "stable"


def bootstrap_exe_name(channel: str | None = None) -> str:
    return "Blossom-beta.exe" if bootstrap_channel() == "beta" or channel == "beta" else "Blossom.exe"


def github_release_repo(channel: str | None = None) -> str:
    return GITHUB_REPO_BETA if bootstrap_channel() == "beta" or channel == "beta" else GITHUB_REPO


def _read_current(channel: str) -> dict[str, Any]:
    path = current_app_json_path(channel)
    try:
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _write_current(channel: str, *, version: str, exe_name: str) -> None:
    payload_dir = app_channel_dir(channel)
    payload_dir.mkdir(parents=True, exist_ok=True)
    data = {"version": version, "exe": exe_name}
    current_app_json_path(channel).write_text(
        json.dumps(data, indent=2) + "\n", encoding="utf-8"
    )


def _local_payload_path(channel: str, exe_name: str) -> Path:
    return app_channel_dir(channel) / exe_name


def _fetch_release(channel: str) -> dict[str, Any] | None:
    if channel == "beta":
        return fetch_latest_beta_release()
    return fetch_latest_stable_release()


def _needs_app_update(channel: str, release: dict[str, Any]) -> bool:
    remote_version = str(release.get("version") or "").strip()
    if not remote_version:
        return False
    current = _read_current(channel)
    local_version = str(current.get("version") or "").strip()
    if not local_version:
        return True
    return version_gt(remote_version, local_version)


def _make_progress_cb(
    reporter: BootstrapReporter,
    *,
    prefix: str,
) -> ProgressCb:
    def _cb(downloaded: int, total: int) -> None:
        reporter.set_progress(downloaded, total)
        if total > 0:
            pct = int((downloaded / total) * 100)
            reporter.set_message(f"{prefix}… {pct}%")
        else:
            reporter.set_message(f"{prefix}…")

    return _cb


def _clear_ui_ready_marker() -> None:
    try:
        ui_ready_marker_path().unlink(missing_ok=True)
    except OSError:
        pass


def _pid_owns_blossom_window(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    user32 = ctypes.windll.user32
    found = False

    def _callback(hwnd: int, _lparam: int) -> bool:
        nonlocal found
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        if buf.value != "Blossom":
            return True
        window_pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if int(window_pid.value) == pid:
            found = True
            return False
        return True

    enum_proc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(_callback)
    user32.EnumWindows(enum_proc, 0)
    return found


def wait_for_ui_ready(pid: int, *, timeout_sec: float = UI_READY_TIMEOUT_SEC) -> bool:
    """Return True when the main Blossom window or ready marker appears."""
    marker = ui_ready_marker_path()
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if marker.is_file():
            return True
        if _pid_owns_blossom_window(pid):
            return True
        time.sleep(UI_READY_POLL_SEC)
    return _pid_owns_blossom_window(pid)


def sync_app_payload(
    channel: str | None = None,
    *,
    progress_cb: ProgressCb | None = None,
    reporter: BootstrapReporter | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Download/replace the managed app exe when a newer release exists."""
    ui = reporter or _NullReporter()
    ch = (channel or bootstrap_channel()).lower()
    if ch not in ("stable", "beta"):
        ch = "stable"

    ensure_app_data_dirs()
    payload_dir = app_channel_dir(ch)
    payload_dir.mkdir(parents=True, exist_ok=True)

    ui.set_phase("update")
    ui.set_message("Checking for updates…")
    ui.set_indeterminate(True)

    release = _fetch_release(ch)
    if not release:
        current = _read_current(ch)
        exe_name = str(current.get("exe") or "").strip()
        if exe_name:
            path = _local_payload_path(ch, exe_name)
            if path.is_file():
                ui.set_message("Offline — using installed copy")
                return {
                    "ok": True,
                    "updated": False,
                    "offline": True,
                    "version": current.get("version"),
                    "path": str(path),
                }
        return {
            "ok": False,
            "error": "Could not reach GitHub and no local payload is installed.",
            "channel": ch,
        }

    remote_version = str(release.get("version") or "").strip()
    asset_name = str(release.get("asset_name") or versioned_exe_name(remote_version))
    download_url = str(release.get("url") or "")
    current = _read_current(ch)
    local_path = _local_payload_path(ch, asset_name)

    if not force and not _needs_app_update(ch, release):
        exe_name = str(current.get("exe") or asset_name)
        path = _local_payload_path(ch, exe_name)
        if path.is_file():
            ui.set_message("App is up to date")
            ui.set_version(str(current.get("version") or remote_version))
            return {
                "ok": True,
                "updated": False,
                "version": current.get("version") or remote_version,
                "path": str(path),
            }

    if not download_url:
        return {"ok": False, "error": "Release has no download URL.", "channel": ch}

    tmp = payload_dir / f"{asset_name}.download"
    try:
        if tmp.exists():
            tmp.unlink()
        ui.set_phase("update")
        ui.set_message(f"Downloading {asset_name}…")
        ui.set_indeterminate(False)
        download_file(download_url, tmp, progress_cb=progress_cb)
    except Exception as error:  # noqa: BLE001
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        current_exe = str(current.get("exe") or "")
        if current_exe:
            path = _local_payload_path(ch, current_exe)
            if path.is_file():
                ui.set_message("Download failed — using installed copy")
                return {
                    "ok": True,
                    "updated": False,
                    "offline": True,
                    "version": current.get("version"),
                    "path": str(path),
                    "error": str(error),
                }
        return {"ok": False, "error": f"Download failed: {error}", "channel": ch}

    if not tmp.is_file() or tmp.stat().st_size < MIN_DOWNLOAD_BYTES:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "error": "Downloaded payload is missing or too small.", "channel": ch}

    dest = _local_payload_path(ch, asset_name)
    try:
        if dest.exists():
            dest.unlink()
        tmp.replace(dest)
    except OSError as error:
        return {"ok": False, "error": f"Could not install payload: {error}", "channel": ch}

    for old in payload_dir.glob("Blossom-*.exe"):
        if old.name != asset_name:
            try:
                old.unlink()
            except OSError:
                pass

    _write_current(ch, version=remote_version, exe_name=asset_name)
    ui.set_message(f"Installed {remote_version}")
    ui.set_version(remote_version)
    return {
        "ok": True,
        "updated": True,
        "version": remote_version,
        "path": str(dest),
        "channel": ch,
    }


def launch_payload(
    exe_path: str | Path,
    *,
    channel: str | None = None,
    extra_env: dict[str, str] | None = None,
    reporter: BootstrapReporter | None = None,
    wait_for_ui: bool = True,
) -> int:
    """Launch the managed payload and exit once the main UI is ready."""
    ui = reporter or _NullReporter()
    path = Path(exe_path).resolve()
    if not path.is_file():
        ui.show_error(f"Payload missing: {path.name}")
        return 1
    ch = (channel or bootstrap_channel()).lower()
    env = os.environ.copy()
    env["BLOSSOM_MANAGED"] = "1"
    env["BLOSSOM_CHANNEL"] = ch
    env["BLOSSOM_BOOTSTRAP_PID"] = str(os.getpid())
    if extra_env:
        env.update(extra_env)

    _clear_ui_ready_marker()
    ui.set_phase("launch")
    ui.set_message("Launching Blossom…")
    ui.set_indeterminate(True)

    creationflags = 0
    if sys.platform == "win32":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    proc = subprocess.Popen(
        [str(path)],
        cwd=str(path.parent),
        env=env,
        creationflags=creationflags,
    )

    if not wait_for_ui:
        return 0

    if wait_for_ui_ready(proc.pid):
        ui.set_message("Blossom is ready")
        return 0

    # Payload started but UI did not signal in time — still detach bootstrap.
    if proc.poll() is None:
        ui.set_message("Blossom started")
        return 0

    ui.show_error("Blossom closed before the interface appeared.")
    return int(proc.returncode or 1)


def apply_managed_update(
    channel: str,
    download_url: str,
    *,
    version: str | None = None,
    asset_name: str | None = None,
    progress_cb: ProgressCb | None = None,
) -> dict[str, Any]:
    """Download a newer payload into AppData for bootstrap-managed installs."""
    ch = channel.lower()
    release_version = str(version or "").strip()
    exe_name = str(asset_name or versioned_exe_name(release_version)).strip()
    if not download_url or not exe_name:
        return {"ok": False, "error": "Missing download URL or asset name."}

    payload_dir = app_channel_dir(ch)
    payload_dir.mkdir(parents=True, exist_ok=True)
    tmp = payload_dir / f"{exe_name}.download"
    try:
        if tmp.exists():
            tmp.unlink()
        download_file(download_url, tmp, progress_cb=progress_cb)
    except Exception as error:  # noqa: BLE001
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        return {"ok": False, "error": f"Download failed: {error}"}

    if not tmp.is_file() or tmp.stat().st_size < MIN_DOWNLOAD_BYTES:
        tmp.unlink(missing_ok=True)
        return {"ok": False, "error": "Downloaded file is missing or too small."}

    dest = _local_payload_path(ch, exe_name)
    try:
        if dest.exists():
            dest.unlink()
        tmp.replace(dest)
    except OSError as error:
        return {"ok": False, "error": f"Could not install payload: {error}"}

    for old in payload_dir.glob("Blossom-*.exe"):
        if old.name != exe_name:
            try:
                old.unlink()
            except OSError:
                pass

    _write_current(ch, version=release_version or exe_name, exe_name=exe_name)
    return {
        "ok": True,
        "managed": True,
        "version": release_version,
        "path": str(dest),
        "restart_launcher": True,
        "launcher": bootstrap_exe_name(ch),
    }


def run_bootstrap(
    *,
    progress_cb: ProgressCb | None = None,
    reporter: BootstrapReporter | None = None,
    skip_runtime: bool = False,
) -> int:
    ui = reporter or _NullReporter()
    ch = bootstrap_channel()
    ui.set_phase("starting")
    ui.set_message(f"Starting {bootstrap_exe_name(ch)}…")
    ui.set_version(BOOTSTRAP_VERSION or (BETA_VERSION if ch == "beta" else STABLE_VERSION))

    app_progress = progress_cb or _make_progress_cb(ui, prefix="Downloading app")
    app_result = sync_app_payload(ch, progress_cb=app_progress, reporter=ui)
    if not app_result.get("ok"):
        error = str(app_result.get("error") or "App sync failed.")
        ui.show_error(error)
        return 1

    if not skip_runtime:
        from blossom_runtime_deps import component_label, load_manifest, sync_runtime_manifest

        ui.set_phase("runtime")
        manifest = load_manifest()
        component_ids = list((manifest.get("components") or {}).keys())
        for component_id in component_ids:
            label = component_label(component_id)
            ui.set_message(f"Syncing {label}…")
            ui.set_indeterminate(True)
            runtime_progress = _make_progress_cb(ui, prefix=f"Downloading {label}")
            try:
                sync_runtime_manifest(components=[component_id], progress_cb=runtime_progress)
            except Exception as error:  # noqa: BLE001
                ui.set_message(f"{label} sync warning: {error}")
        ui.set_message("Runtime components ready")

    payload = str(app_result.get("path") or "")
    if not payload:
        ui.show_error("No app payload to launch.")
        return 1

    code = launch_payload(payload, channel=ch, reporter=ui)
    return code


def _run_with_ui(ui: BootstrapReporter) -> int:
    return run_bootstrap(reporter=ui)


def main() -> int:
    try:
        if sys.platform == "win32" and "--no-ui" not in sys.argv:
            from blossom_bootstrap_ui import BootstrapUI

            ch = bootstrap_channel()
            version = BOOTSTRAP_VERSION or (BETA_VERSION if ch == "beta" else STABLE_VERSION)
            return BootstrapUI(channel=ch, version=version).run(_run_with_ui)
        return run_bootstrap()
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
