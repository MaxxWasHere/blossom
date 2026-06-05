"""Client-side license gating for Blossom beta builds.

Beta builds require a key issued through the Blossom Discord. The key is bound to
one machine (HWID) by the activation server and can be revoked. A short signed
token is cached locally so brief offline periods are tolerated (grace window).

Licensing only applies to FROZEN (packaged) BETA builds. Running from source or
the stable channel is never gated, so development is unaffected.

License server lives in ../license-server.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

from blossom_dirs import APP_DATA_DIR, ensure_app_data_dirs

try:
    import blossom_build_info as _build_info

    BUILD_CHANNEL = str(getattr(_build_info, "BUILD_CHANNEL", "stable")).lower()
    APP_VERSION = str(getattr(_build_info, "APP_VERSION", "0.0.0"))
    BETA_EXPIRY_DATE = str(getattr(_build_info, "BETA_EXPIRY_DATE", "") or "")
    BUILD_WATERMARK = str(getattr(_build_info, "BUILD_WATERMARK", "") or "")
except ImportError:  # pragma: no cover - build info always present in practice
    BUILD_CHANNEL = "stable"
    APP_VERSION = "0.0.0"
    BETA_EXPIRY_DATE = ""
    BUILD_WATERMARK = ""

# ----- Configuration (fill these in before shipping a beta build) ----- #
# Deployed Cloudflare worker URL, e.g. "https://blossom-license.yourname.workers.dev"
LICENSE_SERVER_URL = (
    os.environ.get("BLOSSOM_LICENSE_SERVER")
    or "https://blossom-license.maxxwashere.workers.dev"
).rstrip("/")
# Ed25519 public key (hex) printed by license-server `npm run keygen`.
ED25519_PUBLIC_KEY_HEX = "956806f494eb70f4abaf931778ca4b85f319680214b143ff1a0b7612fcdc30b5"

GRACE_HOURS = 12          # tolerate this long offline after last good validation
REVALIDATE_INTERVAL_SEC = 6 * 3600
HTTP_TIMEOUT_SEC = 15
_HWID_SALT = "blossom-hwid-v1"

LICENSE_FILE = APP_DATA_DIR / "license.json"

# Human-readable copy for each server deny reason.
_REASON_TEXT = {
    "invalid_key": "That key was not recognised. Check for typos.",
    "revoked": "This key has been revoked.",
    "expired": "This key has expired.",
    "wrong_machine": "This key is already in use. Use /resethwid in Discord if you need to reset it.",
    "not_activated": "This key has not been activated on this device yet.",
    "missing_fields": "Activation request was incomplete.",
    "bad_json": "Server returned an unexpected response.",
    "offline": "Could not reach the activation server. Check your internet.",
    "unconfigured": "This build has no activation server configured.",
    "expired_build": "This beta build has expired. Please update to a newer build.",
}

_state_lock = Lock()
# Cached status so the UI / macro gate can read without hitting the network.
_cached: dict | None = None


# ----------------------------------------------------------------------------- #
# Build / channel helpers
# ----------------------------------------------------------------------------- #
def is_frozen() -> bool:
    import sys

    return bool(getattr(sys, "frozen", False))


def licensing_required() -> bool:
    """Only packaged beta builds are gated.

    Bypass env vars are honoured ONLY when running from source (developer
    convenience). In a shipped/frozen build they are ignored, so a tester cannot
    disable gating with BLOSSOM_SKIP_LICENSE=1.
    """
    if not is_frozen():
        if os.environ.get("BLOSSOM_FORCE_LICENSE") == "1":
            return True
        if os.environ.get("BLOSSOM_SKIP_LICENSE") == "1":
            return False
        return False
    return BUILD_CHANNEL == "beta"


def _build_expired() -> bool:
    if not BETA_EXPIRY_DATE:
        return False
    try:
        expiry = datetime.strptime(BETA_EXPIRY_DATE, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return datetime.now(timezone.utc) > expiry


# ----------------------------------------------------------------------------- #
# HWID
# ----------------------------------------------------------------------------- #
def _machine_guid() -> str:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as handle:
            value, _ = winreg.QueryValueEx(handle, "MachineGuid")
            return str(value)
    except OSError:
        return ""


def _volume_serial() -> str:
    try:
        import ctypes

        root = os.environ.get("SystemDrive", "C:") + "\\"
        serial = ctypes.c_ulong(0)
        ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p(root), None, 0, ctypes.byref(serial), None, None, None, 0
        )
        return str(serial.value)
    except Exception:
        return ""


def _mac_node() -> str:
    try:
        import uuid

        node = uuid.getnode()
        # getnode returns a random multicast bit-set value when it can't read a MAC.
        if (node >> 40) & 0x1:
            return ""
        return f"{node:012x}"
    except Exception:
        return ""


def compute_hwid() -> str:
    parts = [_machine_guid(), _volume_serial(), _mac_node(), os.environ.get("COMPUTERNAME", "")]
    raw = _HWID_SALT + "|" + "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:32]


# ----------------------------------------------------------------------------- #
# License file
# ----------------------------------------------------------------------------- #
def _load_license_file() -> dict:
    try:
        if LICENSE_FILE.is_file():
            return json.loads(LICENSE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_license_file(data: dict) -> None:
    try:
        ensure_app_data_dirs()
        LICENSE_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError as error:
        print(f"[license] could not save license file: {error}")


def clear_license() -> None:
    try:
        if LICENSE_FILE.is_file():
            LICENSE_FILE.unlink()
    except OSError:
        pass
    _set_cached(None)


def mask_key(key: str) -> str:
    key = (key or "").strip()
    if len(key) <= 6:
        return key
    return key[:5] + "…" + key[-4:]


# ----------------------------------------------------------------------------- #
# Token verification (best-effort; the live server check is the real gate)
# ----------------------------------------------------------------------------- #
def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def _verify_token(token: str, *, hwid: str) -> dict | None:
    """Return the payload if the signature + claims check out, else None."""
    try:
        body_b64, sig_b64 = token.split(".", 1)
    except ValueError:
        return None
    try:
        payload = json.loads(_b64url_decode(body_b64))
    except (ValueError, json.JSONDecodeError):
        return None

    if payload.get("hwid") != hwid:
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or exp < time.time():
        return None

    if ED25519_PUBLIC_KEY_HEX:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import (
                Ed25519PublicKey,
            )

            pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(ED25519_PUBLIC_KEY_HEX))
            pub.verify(_b64url_decode(sig_b64), body_b64.encode("ascii"))
        except ImportError:
            # In a shipped build cryptography is bundled, so a missing module means
            # tampering -> fail closed. In source/dev runs, fall back to the live
            # server check instead of blocking development.
            if is_frozen():
                return None
        except Exception:
            return None
    return payload


# ----------------------------------------------------------------------------- #
# Server calls
# ----------------------------------------------------------------------------- #
def _post(path: str, payload: dict) -> dict:
    if not LICENSE_SERVER_URL:
        return {"ok": False, "reason": "unconfigured"}
    try:
        import requests

        resp = requests.post(
            f"{LICENSE_SERVER_URL}{path}", json=payload, timeout=HTTP_TIMEOUT_SEC
        )
        try:
            return resp.json()
        except ValueError:
            return {"ok": False, "reason": f"http_{resp.status_code}"}
    except Exception:
        return {"ok": False, "reason": "offline"}


# ----------------------------------------------------------------------------- #
# Status model
# ----------------------------------------------------------------------------- #
def _set_cached(status: dict | None) -> None:
    global _cached
    with _state_lock:
        _cached = status


def _status(
    state: str,
    *,
    reason: str | None = None,
    key: str | None = None,
    extra: dict | None = None,
) -> dict:
    licensed = state == "licensed"
    out = {
        "required": True,
        "licensed": licensed,
        "state": state,  # licensed | unlicensed | invalid | offline | expired_build | unconfigured
        "reason": reason,
        "message": _REASON_TEXT.get(reason or "", "") if not licensed else "Activated.",
        "key_masked": mask_key(key) if key else "",
        "server_configured": bool(LICENSE_SERVER_URL),
        "hwid": compute_hwid(),
        "expiry": BETA_EXPIRY_DATE or None,
    }
    if extra:
        out.update(extra)
    return out


def _not_required_status() -> dict:
    return {
        "required": False,
        "licensed": True,
        "state": "not_required",
        "reason": None,
        "message": "",
        "key_masked": "",
        "server_configured": bool(LICENSE_SERVER_URL),
        "hwid": compute_hwid(),
        "expiry": None,
    }


# ----------------------------------------------------------------------------- #
# Public API
# ----------------------------------------------------------------------------- #
def is_licensed() -> bool:
    """Cryptographic, offline-capable gate used to allow the macro to run.

    Does NOT trust a cached boolean (that would be trivial to patch). Every call
    re-derives the answer from the on-disk, server-signed token: it must verify
    against the embedded public key, be bound to *this* machine's HWID, be
    unexpired, and fall inside the offline grace window. Revocation is enforced
    separately by the periodic server re-validation guard.
    """
    if not licensing_required():
        return True
    if _build_expired():
        return False

    data = _load_license_file()
    key = data.get("key") or ""
    if not key:
        return False

    hwid = compute_hwid()
    token = data.get("token") or ""
    payload = _verify_token(token, hwid=hwid) if token else None
    if not payload:
        return False

    # The signed token's own `exp` (set by the server) caps the offline window;
    # `last_validated` cannot be edited to extend it because exp is signed.
    last = float(data.get("last_validated") or 0)
    within_grace = (time.time() - last) < GRACE_HOURS * 3600
    return bool(within_grace)


def get_status(*, refresh: bool = True) -> dict:
    """Resolve current license status. With refresh, contacts the server."""
    if not licensing_required():
        status = _not_required_status()
        _set_cached(status)
        return status

    if _build_expired():
        status = _status("expired_build", reason="expired_build")
        _set_cached(status)
        return status

    data = _load_license_file()
    key = data.get("key") or ""
    hwid = compute_hwid()

    if not key:
        status = _status("unlicensed", reason="not_activated")
        _set_cached(status)
        return status

    if refresh:
        return _refresh_from_server(key, hwid, data)

    # Offline / cached path: trust a still-valid signed token within the grace window.
    return _evaluate_offline(key, hwid, data)


def _evaluate_offline(key: str, hwid: str, data: dict) -> dict:
    token = data.get("token") or ""
    last = float(data.get("last_validated") or 0)
    payload = _verify_token(token, hwid=hwid) if token else None
    within_grace = (time.time() - last) < GRACE_HOURS * 3600
    if payload and within_grace:
        status = _status("licensed", key=key, extra={"offline": True})
    else:
        status = _status("offline", reason="offline", key=key)
    _set_cached(status)
    return status


def _refresh_from_server(key: str, hwid: str, data: dict) -> dict:
    result = _post("/validate", {"key": key, "hwid": hwid})
    if result.get("ok"):
        data.update(
            {
                "key": key,
                "hwid": hwid,
                "token": result.get("token") or data.get("token"),
                "last_validated": time.time(),
            }
        )
        _save_license_file(data)
        status = _status("licensed", key=key)
        _set_cached(status)
        return status

    reason = result.get("reason", "offline")
    if reason in ("offline", "unconfigured"):
        # Network/config problem -> fall back to the grace window so a flaky
        # connection doesn't lock out a legitimate, already-activated user.
        return _evaluate_offline(key, hwid, data)

    # Hard denial (revoked / wrong_machine / invalid) -> lock out.
    status = _status("invalid", reason=reason, key=key)
    _set_cached(status)
    return status


def activate(key: str) -> dict:
    """Activate a key on this machine. Returns a status dict."""
    key = (key or "").strip().upper()
    if not licensing_required():
        return _not_required_status()
    if not key:
        return _status("unlicensed", reason="invalid_key")
    if _build_expired():
        return _status("expired_build", reason="expired_build")

    hwid = compute_hwid()
    result = _post("/activate", {"key": key, "hwid": hwid, "version": APP_VERSION})
    if result.get("ok"):
        data = {
            "key": key,
            "hwid": hwid,
            "token": result.get("token"),
            "discord_id": result.get("discordId"),
            "last_validated": time.time(),
            "activated_at": time.time(),
        }
        _save_license_file(data)
        status = _status("licensed", key=key)
        _set_cached(status)
        return status

    reason = result.get("reason", "offline")
    state = "offline" if reason in ("offline", "unconfigured") else "invalid"
    status = _status(state, reason=reason, key=key)
    _set_cached(status)
    return status
