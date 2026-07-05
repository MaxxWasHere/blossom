"""Hard-coded GitHub release check and Windows exe swap for Blossom."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Latest version numbers (bump when shipping each channel).
STABLE_VERSION = "2.3.8"
BETA_VERSION = "2.3.6-beta.1"

try:
    import blossom_build_info as _build_info

    APP_VERSION = _build_info.APP_VERSION
    BUILD_CHANNEL = _build_info.BUILD_CHANNEL
except ImportError:
    BUILD_CHANNEL = "beta"
    APP_VERSION = BETA_VERSION

DEV_VERSION_SUFFIX = "-dev"

GITHUB_OWNER = "MaxxWasHere"
GITHUB_REPO = "blossom"
GITHUB_REPO_BETA = "blossombeta"
RELEASE_API_LATEST = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
)
RELEASES_API = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases?per_page=30"
)
RELEASES_API_BETA = (
    f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO_BETA}/releases?per_page=30"
)

LEGACY_STABLE_EXE = "BlossomMacro.exe"
LEGACY_BETA_EXE = "BlossomMacro-beta.exe"
_VERSIONED_EXE_RE = re.compile(r"^Blossom-(.+)\.exe$", re.IGNORECASE)

DOWNLOAD_NAME = "BlossomMacro.download.exe"
OLD_EXE_SUFFIX = ".exe.old"
UPDATE_SCRIPT_NAME = "apply_blossom_update.ps1"
USER_AGENT = "BlossomMacro-updater"
MIN_DOWNLOAD_BYTES = 1_000_000
DOWNLOAD_CHUNK = 1024 * 1024
DOWNLOAD_TIMEOUT_SEC = 120
API_TIMEOUT_SEC = 30

_VERSION_RE = re.compile(r"^v?", re.IGNORECASE)


def build_channel() -> str:
    channel = str(BUILD_CHANNEL or "stable").strip().lower()
    return "beta" if channel == "beta" else "stable"


def versioned_exe_name(version: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]', "-", str(version or "").strip())
    return f"Blossom-{cleaned}.exe"


def exe_name_for_channel(channel: str | None = None) -> str:
    ch = (channel or build_channel()).lower()
    if is_frozen_build():
        return Path(sys.executable).name
    if ch == "beta":
        return versioned_exe_name(APP_VERSION) if "beta" in APP_VERSION.lower() else LEGACY_BETA_EXE
    return versioned_exe_name(APP_VERSION) if "beta" not in APP_VERSION.lower() else LEGACY_STABLE_EXE


def asset_name_for_channel(channel: str | None = None) -> str:
    ch = (channel or build_channel()).lower()
    return versioned_exe_name(BETA_VERSION if ch == "beta" else STABLE_VERSION)


def process_name_for_channel(channel: str | None = None) -> str:
    name = exe_name_for_channel(channel)
    return Path(name).stem


def is_frozen_build() -> bool:
    return bool(getattr(sys, "frozen", False))


def display_version(*, dev: bool | None = None, channel: str | None = None) -> str:
    if dev is None:
        dev = not is_frozen_build()
    ch = (channel or build_channel()).lower()
    label = APP_VERSION
    if dev:
        label = f"{label}{DEV_VERSION_SUFFIX}"
    low = label.lower()
    if ch == "beta":
        return label if "beta" in low else f"{label} (beta)"
    return label if "stable" in low else f"{label} (stable)"


def version_info() -> dict[str, str]:
    ch = build_channel()
    return {
        "channel": ch,
        "version": APP_VERSION,
        "display": display_version(),
        "stable_version": STABLE_VERSION,
        "beta_version": BETA_VERSION,
        "exe_name": exe_name_for_channel(ch),
    }


def parse_version(version: str) -> tuple[int, ...]:
    """Normalize v1.5.1 / 1.6.0-beta.1 into comparable integer tuples."""
    cleaned = _VERSION_RE.sub("", str(version or "").strip())
    if not cleaned:
        return (0,)
    parts: list[int] = []
    for segment in cleaned.split("."):
        segment = segment.strip()
        if not segment:
            continue
        match = re.match(r"(\d+)", segment)
        if match:
            parts.append(int(match.group(1)))
        else:
            break
    return tuple(parts) if parts else (0,)


def version_gt(remote: str, local: str | None = None) -> bool:
    local_ver = local if local is not None else APP_VERSION
    return parse_version(remote) > parse_version(local_ver)


def _github_request(url: str, *, timeout: int = API_TIMEOUT_SEC) -> Any:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        },
    )
    with urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"GitHub API returned HTTP {response.status}")
        return json.load(response)


def _asset_url(release: dict[str, Any], asset_name: str) -> str | None:
    for asset in release.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        if asset.get("name") != asset_name:
            continue
        url = asset.get("browser_download_url")
        if url:
            return str(url)
    return None


def _version_from_asset_name(name: str) -> tuple[int, ...]:
    match = _VERSIONED_EXE_RE.match(name)
    if not match:
        return (0,)
    return parse_version(match.group(1))


def _version_label_from_asset_name(name: str) -> str:
    """Version string embedded in a Blossom-<version>.exe asset name, if any."""
    match = _VERSIONED_EXE_RE.match(str(name or ""))
    if not match:
        return ""
    return match.group(1).strip()


def _release_version(release: dict[str, Any], asset: dict[str, str] | None) -> str:
    """Prefer the version baked into the asset filename over the release title.

    Release titles/tags on GitHub are hand-entered and often not clean version
    strings (e.g. "Blossom Beta"), which parse_version reduces to (0,) so nothing
    ever looks newer. The asset name is produced by the build (Blossom-<ver>.exe)
    and is the reliable source of truth.
    """
    if asset:
        asset_version = _version_label_from_asset_name(asset.get("name", ""))
        if asset_version and parse_version(asset_version) != (0,):
            return asset_version
    return str(release.get("name") or release.get("tag_name") or "").strip()


def _pick_release_asset(
    release: dict[str, Any],
    channel: str,
    *,
    prefer_version: str | None = None,
) -> dict[str, str] | None:
    assets = release.get("assets") or []
    prefer_name = versioned_exe_name(prefer_version) if prefer_version else None
    legacy_name = LEGACY_BETA_EXE if channel == "beta" else LEGACY_STABLE_EXE

    if prefer_name:
        url = _asset_url(release, prefer_name)
        if url:
            return {"name": prefer_name, "url": url}

    candidates: list[tuple[tuple[int, ...], str, str]] = []
    legacy_url: str | None = None
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        name = str(asset.get("name") or "")
        url = asset.get("browser_download_url")
        if not url:
            continue
        low = name.lower()
        if name == legacy_name:
            legacy_url = str(url)
            continue
        if not _VERSIONED_EXE_RE.match(name):
            continue
        if channel == "stable" and "beta" in low:
            continue
        if channel == "beta" and "beta" not in low:
            continue
        candidates.append((_version_from_asset_name(name), str(url), name))

    if candidates:
        candidates.sort(key=lambda item: item[0], reverse=True)
        _, url, name = candidates[0]
        return {"name": name, "url": url}
    if legacy_url:
        return {"name": legacy_name, "url": legacy_url}
    return None


# Marker a publisher can put in a GitHub release body/notes to force a manual
# reinstall instead of the silent in-place swap. Either a bare [reinstall] token
# or a "reinstall: true" line (case-insensitive) anywhere in the body works.
_REINSTALL_TOKEN_RE = re.compile(r"\[\s*reinstall\s*\]", re.IGNORECASE)
_REINSTALL_LINE_RE = re.compile(
    r"^\s*reinstall\s*[:=]\s*(true|yes|1|required)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def parse_reinstall_required(body: str | None) -> bool:
    """True when a release body asks for a manual reinstall (see markers above)."""
    text = str(body or "")
    if not text:
        return False
    if _REINSTALL_TOKEN_RE.search(text):
        return True
    return bool(_REINSTALL_LINE_RE.search(text))


# Exceptions that mean "could not reach GitHub" (network/HTTP/rate-limit) as
# opposed to "reached GitHub, nothing newer". Used so the startup check can
# retry transient failures without retrying a successful no-update result.
NETWORK_ERRORS = (HTTPError, URLError, RuntimeError, json.JSONDecodeError, TimeoutError, OSError)


def _fetch_latest_stable_release_raw(*, prefer: bool = True) -> dict[str, Any] | None:
    data = _github_request(RELEASE_API_LATEST)
    if not isinstance(data, dict):
        return None
    asset = _pick_release_asset(
        data, "stable", prefer_version=STABLE_VERSION if prefer else None
    )
    version = _release_version(data, asset)
    if version and asset:
        return {
            "version": version,
            "url": asset["url"],
            "asset_name": asset["name"],
            "channel": "stable",
            "reinstall_required": parse_reinstall_required(data.get("body")),
        }
    return None


def _fetch_latest_beta_release_raw(*, prefer: bool = True) -> dict[str, Any] | None:
    releases = _github_request(RELEASES_API_BETA)
    if not isinstance(releases, list):
        return None
    for release in releases:
        if not isinstance(release, dict):
            continue
        asset = _pick_release_asset(
            release, "beta", prefer_version=BETA_VERSION if prefer else None
        )
        version = _release_version(release, asset)
        if version and asset:
            return {
                "version": version,
                "url": asset["url"],
                "asset_name": asset["name"],
                "channel": "beta",
                "reinstall_required": parse_reinstall_required(release.get("body")),
            }
    return None


def fetch_latest_stable_release(*, prefer: bool = True) -> dict[str, Any] | None:
    """Latest non-prerelease GitHub release with a Blossom-*.exe (or legacy BlossomMacro.exe).

    prefer=False ignores the version baked into the running build and always
    returns the highest-versioned payload the source publishes, so a managed
    launcher tracks the source exactly (upgrade or deliberate rollback).
    """
    try:
        return _fetch_latest_stable_release_raw(prefer=prefer)
    except NETWORK_ERRORS:
        return None


def fetch_latest_beta_release(*, prefer: bool = True) -> dict[str, Any] | None:
    """Latest beta release on blossombeta with Blossom-*beta*.exe."""
    try:
        return _fetch_latest_beta_release_raw(prefer=prefer)
    except NETWORK_ERRORS:
        return None


def fetch_latest_release(channel: str | None = None, *, prefer: bool = True) -> dict[str, Any] | None:
    ch = (channel or build_channel()).lower()
    if ch == "beta":
        return fetch_latest_beta_release(prefer=prefer)
    return fetch_latest_stable_release(prefer=prefer)


def check_newer_than_local(channel: str | None = None) -> dict[str, Any] | None:
    """Latest release for this build's channel if remote version is newer than APP_VERSION."""
    ch = (channel or build_channel()).lower()
    release = fetch_latest_release(ch)
    if not release:
        return None
    if version_gt(release["version"], APP_VERSION):
        return release
    return None


def check_update_status(channel: str | None = None) -> dict[str, Any]:
    """Reach GitHub once and report the outcome without swallowing network errors.

    Returns a dict:
      {"ok": True,  "release": <dict>}  newer release available
      {"ok": True,  "release": None}    reached GitHub, nothing newer
      {"ok": False, "release": None, "error": <str>}  could not reach GitHub

    The ok flag lets callers retry only on real failures (timeouts, HTTP 403
    rate limits, offline) instead of retrying a valid "no update" answer.
    """
    ch = (channel or build_channel()).lower()
    try:
        if ch == "beta":
            release = _fetch_latest_beta_release_raw()
        else:
            release = _fetch_latest_stable_release_raw()
    except NETWORK_ERRORS as error:
        return {"ok": False, "release": None, "error": str(error)}
    if release and version_gt(release["version"], APP_VERSION):
        return {"ok": True, "release": release, "error": None}
    return {"ok": True, "release": None, "error": None}


def _content_length(response: Any) -> int:
    """Total bytes from the Content-Length header, or 0 when unknown."""
    raw = ""
    try:
        raw = response.headers.get("Content-Length", "")
    except Exception:
        raw = ""
    raw = str(raw or "").strip()
    if raw.isdigit():
        try:
            return int(raw)
        except ValueError:
            return 0
    return 0


def download_file(
    url: str,
    output_path: Path,
    *,
    progress_cb: Any | None = None,
) -> None:
    """Stream a download to disk, optionally reporting progress.

    progress_cb, if given, is called as progress_cb(downloaded, total) where
    total is the Content-Length in bytes or 0 when the server does not report a
    size. It fires once at the start, after each chunk, and once at the end. The
    callback must never raise or block for long; exceptions are swallowed so a
    misbehaving UI bridge can't abort the download.
    """
    request = Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": USER_AGENT,
        },
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)

    def _report(downloaded: int, total: int) -> None:
        if progress_cb is None:
            return
        try:
            progress_cb(downloaded, total)
        except Exception:
            pass

    with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SEC) as response, output_path.open(
        "wb"
    ) as output_file:
        total = _content_length(response)
        downloaded = 0
        _report(0, total)
        while True:
            chunk = response.read(DOWNLOAD_CHUNK)
            if not chunk:
                break
            output_file.write(chunk)
            downloaded += len(chunk)
            _report(downloaded, total)
        _report(downloaded, total or downloaded)


def write_update_script(
    install_root: Path,
    *,
    channel: str | None = None,
    target_exe_name: str | None = None,
) -> Path:
    """PowerShell script: wait for exe exit, swap download into place, relaunch."""
    ch = (channel or build_channel()).lower()
    if is_frozen_build():
        current_exe = Path(sys.executable).resolve()
        running_proc = current_exe.stem
        current_exe_name = current_exe.name
        exe_name = target_exe_name or current_exe_name
    else:
        running_proc = Path(
            target_exe_name
            or versioned_exe_name(BETA_VERSION if ch == "beta" else STABLE_VERSION)
        ).stem
        current_exe_name = None
        exe_name = target_exe_name or versioned_exe_name(
            BETA_VERSION if ch == "beta" else STABLE_VERSION
        )
    script_path = install_root / UPDATE_SCRIPT_NAME
    root = str(install_root.resolve()).replace("'", "''")
    remove_old = ""
    if current_exe_name and current_exe_name != exe_name:
        remove_old = f"""
$prev = Join-Path $root '{current_exe_name.replace("'", "''")}'
if (Test-Path -LiteralPath $prev) {{ Remove-Item -LiteralPath $prev -Force -ErrorAction SilentlyContinue }}
"""
    script = f"""$ErrorActionPreference = 'Stop'
$root = '{root}'
$exe = Join-Path $root '{exe_name.replace("'", "''")}'
$download = Join-Path $root '{DOWNLOAD_NAME}'
$old = $exe + '{OLD_EXE_SUFFIX}'
$deadline = (Get-Date).AddSeconds(90)
while ((Get-Process -Name '{running_proc.replace("'", "''")}' -ErrorAction SilentlyContinue) -and (Get-Date) -lt $deadline) {{
    Start-Sleep -Milliseconds 400
}}
if (-not (Test-Path -LiteralPath $download)) {{ exit 1 }}
if (Test-Path -LiteralPath $old) {{ Remove-Item -LiteralPath $old -Force }}
if (Test-Path -LiteralPath $exe) {{
    Move-Item -LiteralPath $exe -Destination $old -Force
}}
Move-Item -LiteralPath $download -Destination $exe -Force
{remove_old}Start-Process -FilePath $exe -WorkingDirectory $root
Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue
"""
    script_path.write_text(script, encoding="utf-8")
    return script_path


def launch_update_script(script_path: Path) -> None:
    subprocess.Popen(
        [
            "powershell",
            "-WindowStyle",
            "Hidden",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ],
        cwd=str(script_path.parent),
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def apply_exe_update(
    install_root: Path,
    download_url: str,
    *,
    frozen: bool,
    channel: str | None = None,
    target_exe_name: str | None = None,
    progress_cb: Any | None = None,
    reinstall_required: bool = False,
) -> dict[str, Any]:
    """
    Download release exe and either swap in place or stage for manual reinstall.

    Returns {ok, error?, dev_mode?}. When reinstall_required is True the new exe
    is downloaded to a clearly named file and left in place (no swap/relaunch);
    the result carries reinstall=True and path so the caller can open the file
    location and tell the user to run it. progress_cb is forwarded to
    download_file (downloaded, total) for the download progress UI.
    """
    if not frozen:
        return {
            "ok": False,
            "dev_mode": True,
            "error": (
                f"Auto-install only works in {exe_name_for_channel(channel)}. "
                "Open the release page to update."
            ),
        }

    if reinstall_required:
        staged_name = target_exe_name or DOWNLOAD_NAME
        download_path = install_root / staged_name
        try:
            if download_path.exists():
                download_path.unlink()
            download_file(download_url, download_path, progress_cb=progress_cb)
        except (HTTPError, URLError, OSError, TimeoutError) as error:
            return {"ok": False, "error": f"Download failed: {error}"}

        if not download_path.is_file() or download_path.stat().st_size < MIN_DOWNLOAD_BYTES:
            if download_path.exists():
                download_path.unlink(missing_ok=True)
            return {"ok": False, "error": "Downloaded file is missing or too small."}

        return {
            "ok": True,
            "reinstall": True,
            "path": str(download_path),
            "channel": build_channel(),
        }

    download_path = install_root / DOWNLOAD_NAME
    try:
        if download_path.exists():
            download_path.unlink()
        download_file(download_url, download_path, progress_cb=progress_cb)
    except (HTTPError, URLError, OSError, TimeoutError) as error:
        return {"ok": False, "error": f"Download failed: {error}"}

    if not download_path.is_file() or download_path.stat().st_size < MIN_DOWNLOAD_BYTES:
        if download_path.exists():
            download_path.unlink(missing_ok=True)
        return {"ok": False, "error": "Downloaded file is missing or too small."}

    try:
        script_path = write_update_script(
            install_root,
            channel=channel,
            target_exe_name=target_exe_name,
        )
        launch_update_script(script_path)
    except OSError as error:
        return {"ok": False, "error": f"Could not start update script: {error}"}

    return {"ok": True, "channel": build_channel()}
