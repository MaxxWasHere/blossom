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
STABLE_VERSION = "1.5.1"
BETA_VERSION = "1.6.0-beta.1"

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


def fetch_latest_stable_release() -> dict[str, str] | None:
    """Latest non-prerelease GitHub release with a Blossom-*.exe (or legacy BlossomMacro.exe)."""
    try:
        data = _github_request(RELEASE_API_LATEST)
    except (HTTPError, URLError, RuntimeError, json.JSONDecodeError, TimeoutError):
        return None
    if not isinstance(data, dict):
        return None
    version = str(data.get("name") or data.get("tag_name") or "").strip()
    asset = _pick_release_asset(data, "stable", prefer_version=STABLE_VERSION)
    if version and asset:
        return {
            "version": version,
            "url": asset["url"],
            "asset_name": asset["name"],
            "channel": "stable",
        }
    return None


def fetch_latest_beta_release() -> dict[str, str] | None:
    """Latest beta release on blossombeta with Blossom-*beta*.exe."""
    try:
        releases = _github_request(RELEASES_API_BETA)
    except (HTTPError, URLError, RuntimeError, json.JSONDecodeError, TimeoutError):
        return None
    if not isinstance(releases, list):
        return None

    for release in releases:
        if not isinstance(release, dict):
            continue
        version = str(release.get("name") or release.get("tag_name") or "").strip()
        asset = _pick_release_asset(release, "beta", prefer_version=BETA_VERSION)
        if version and asset:
            return {
                "version": version,
                "url": asset["url"],
                "asset_name": asset["name"],
                "channel": "beta",
            }
    return None


def fetch_latest_release(channel: str | None = None) -> dict[str, str] | None:
    ch = (channel or build_channel()).lower()
    if ch == "beta":
        return fetch_latest_beta_release()
    return fetch_latest_stable_release()


def check_newer_than_local(channel: str | None = None) -> dict[str, str] | None:
    """Latest release for this build's channel if remote version is newer than APP_VERSION."""
    ch = (channel or build_channel()).lower()
    release = fetch_latest_release(ch)
    if not release:
        return None
    if version_gt(release["version"], APP_VERSION):
        return release
    return None


def download_file(url: str, output_path: Path) -> None:
    request = Request(
        url,
        headers={
            "Accept": "application/octet-stream",
            "User-Agent": USER_AGENT,
        },
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with urlopen(request, timeout=DOWNLOAD_TIMEOUT_SEC) as response, output_path.open(
        "wb"
    ) as output_file:
        while True:
            chunk = response.read(DOWNLOAD_CHUNK)
            if not chunk:
                break
            output_file.write(chunk)


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
) -> dict[str, Any]:
    """
    Download release exe and schedule swap. Returns {ok, error?, dev_mode?}.
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

    download_path = install_root / DOWNLOAD_NAME
    try:
        if download_path.exists():
            download_path.unlink()
        download_file(download_url, download_path)
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
