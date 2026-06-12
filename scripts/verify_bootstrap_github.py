#!/usr/bin/env python3
"""Verify bootstrap GitHub release URLs and expected asset names."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from blossom_bootstrap import bootstrap_channel, github_release_repo  # noqa: E402
from blossom_updater import (  # noqa: E402
    BETA_VERSION,
    GITHUB_OWNER,
    GITHUB_REPO,
    GITHUB_REPO_BETA,
    STABLE_VERSION,
    fetch_latest_beta_release,
    fetch_latest_stable_release,
    versioned_exe_name,
)
from blossom_runtime_deps import component_archive_name, load_manifest, abi_key  # noqa: E402

APP_SUBDIR = "app"
LAUNCHERS_SUBDIR = "launchers"


def _check_release(label: str, release: dict | None, expected_version: str) -> list[str]:
    issues: list[str] = []
    expected_asset = versioned_exe_name(expected_version)
    if not release:
        issues.append(f"{label}: no release found on GitHub")
        return issues
    version = str(release.get("version") or "")
    asset = str(release.get("asset_name") or "")
    url = str(release.get("url") or "")
    print(f"[verify] {label} release version={version!r} asset={asset!r}")
    if not url:
        issues.append(f"{label}: missing download URL")
    if asset != expected_asset:
        issues.append(
            f"{label}: expected asset {expected_asset!r}, got {asset!r} "
            f"(upload Blossom-{expected_version}.exe to the release)"
        )
    return issues


def _check_runtime() -> list[str]:
    issues: list[str] = []
    manifest = load_manifest()
    base = str(manifest.get("base_url") or "").rstrip("/")
    key = abi_key()
    print(f"[verify] runtime base_url={base!r} abi={key!r}")
    if "blossombeta" not in base or "runtime-deps" not in base:
        issues.append(f"runtime base_url should point at blossombeta runtime-deps tag, got {base!r}")
    for component_id in ("cv2", "winocr"):
        name = component_archive_name(component_id, key)
        url = f"{base}/{name}"
        print(f"[verify] runtime asset {component_id}: {name}")
        print(f"         {url}")
    return issues


def main() -> int:
    issues: list[str] = []
    print(f"[verify] stable repo: {GITHUB_OWNER}/{GITHUB_REPO}")
    print(f"[verify] beta repo:   {GITHUB_OWNER}/{GITHUB_REPO_BETA}")
    issues.extend(_check_release("stable", fetch_latest_stable_release(), STABLE_VERSION))
    issues.extend(_check_release("beta", fetch_latest_beta_release(), BETA_VERSION))
    issues.extend(_check_runtime())

    print("\n[verify] GitHub upload checklist:")
    print(f"  Stable ({GITHUB_REPO}) payload: {APP_SUBDIR}/Blossom-{STABLE_VERSION}.exe")
    print(f"  Stable ({GITHUB_REPO}) launcher: {LAUNCHERS_SUBDIR}/Blossom.exe")
    print(f"  Beta ({GITHUB_REPO_BETA}) payload: {APP_SUBDIR}/Blossom-{BETA_VERSION}.exe")
    print(f"  Beta ({GITHUB_REPO_BETA}) launcher: {LAUNCHERS_SUBDIR}/Blossom-beta.exe")
    print("  Runtime (blossombeta tag runtime-deps):")
    for component_id in ("cv2", "winocr"):
        print(f"    - {component_archive_name(component_id, abi_key())}")

    if issues:
        print("\n[verify] ISSUES:")
        for item in issues:
            print(f"  - {item}")
        return 1

    print("\n[verify] OK — bootstrap GitHub config looks consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
