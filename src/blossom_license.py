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
import sys
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
    BUILD_INTEGRITY = str(getattr(_build_info, "BUILD_INTEGRITY", "") or "")
except ImportError:  # pragma: no cover - build info always present in practice
    BUILD_CHANNEL = "stable"
    APP_VERSION = "0.0.0"
    BETA_EXPIRY_DATE = ""
    BUILD_WATERMARK = ""
    BUILD_INTEGRITY = ""

# ----- Configuration (fill these in before shipping a beta build) ----- #
LICENSE_SERVER_URL = (
    os.environ.get("BLOSSOM_LICENSE_SERVER")
    or "https://blossom-license.maxxwashere.workers.dev"
).rstrip("/")
# Ed25519 public key (hex) printed by license-server `npm run keygen`.
ED25519_PUBLIC_KEY_HEX = "956806f494eb70f4abaf931778ca4b85f319680214b143ff1a0b7612fcdc30b5"

GRACE_HOURS = 6
REVALIDATE_INTERVAL_SEC = 6 * 3600
HTTP_TIMEOUT_SEC = 15
_HWID_SALT = "blossom-hwid-v2"
_TOKEN_CHANNEL = "beta"

LICENSE_FILE = APP_DATA_DIR / "license.dat"
LICENSE_FILE_LEGACY = APP_DATA_DIR / "license.json"

_REASON_TEXT = {
    "invalid_key": "That key was not recognised. Check for typos.",
    "revoked": "This key has been revoked.",
    "expired": "This key has expired.",
    "wrong_machine": "This key is already in use. Use /resethwid in Discord if you need to reset it.",
    "not_activated": "This key has not been activated on this device yet.",
    "missing_fields": "Activation request was incomplete.",
    "bad_json": "Server returned an unexpected response.",
    "offline": "Could not reach the activation server. Check your internet connection and try again.",
    "timeout": "The activation server took too long to respond. Try again.",
    "ssl_error": "Could not verify the activation server (TLS error). Check your clock and network.",
    "unconfigured": "This build has no activation server configured.",
    "expired_build": "This beta build has expired. Please update to a newer build.",
    "rate_limited": "Too many activation attempts. Wait a minute and try again.",
    "invalid_nonce": "Activation session expired. Try again.",
    "tampered": "This build failed a security check.",
    "dns_error": "Could not resolve the activation server. Check your internet or DNS settings.",
    "server_error": "The activation server returned an error. Try again in a few minutes.",
    "not_found": "The activation server is missing a required endpoint. Update Blossom or try again later.",
}

_HTTP_USER_AGENT = "BlossomMacro/1.0"
_HTTP_TLS_CONFIGURED = False
_NETWORK_REASONS = frozenset(
    {"offline", "unconfigured", "timeout", "ssl_error", "dns_error", "server_error"}
)

_state_lock = Lock()
_cached: dict | None = None
_tamper_flag = False


# ----------------------------------------------------------------------------- #
# Build / channel helpers
# ----------------------------------------------------------------------------- #
def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _exe_looks_beta() -> bool:
    try:
        name = Path(sys.executable).name.lower()
        return "beta" in name
    except Exception:
        return False


def _managed_channel_beta() -> bool:
    return os.environ.get("BLOSSOM_CHANNEL", "").strip().lower() == "beta"


def _frozen_channel_beta() -> bool:
    if BUILD_CHANNEL == "beta":
        return True
    if _managed_channel_beta():
        return True
    return _exe_looks_beta()


def licensing_required() -> bool:
    """Only packaged beta builds are gated.

    Bypass env vars are honoured ONLY when running from source (developer
    convenience). In a shipped/frozen build they are ignored. Frozen beta is
    detected from BUILD_CHANNEL, managed launcher env, and exe naming so a
    patched build_info alone cannot disable gating.
    """
    if not is_frozen():
        if os.environ.get("BLOSSOM_FORCE_LICENSE") == "1":
            return True
        if os.environ.get("BLOSSOM_SKIP_LICENSE") == "1":
            return False
        return False
    return _frozen_channel_beta()


def _build_expired() -> bool:
    if not BETA_EXPIRY_DATE:
        return False
    try:
        expiry = datetime.strptime(BETA_EXPIRY_DATE, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return datetime.now(timezone.utc) > expiry


# ----------------------------------------------------------------------------- #
# Anti-tamper (frozen beta only — raises cost, not proof)
# ----------------------------------------------------------------------------- #
def _debugger_attached() -> bool:
    if not is_frozen() or sys.platform != "win32":
        return False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        if kernel32.IsDebuggerPresent():
            return True
        remote = ctypes.c_int(0)
        if kernel32.CheckRemoteDebuggerPresent(
            kernel32.GetCurrentProcess(), ctypes.byref(remote)
        ):
            return bool(remote.value)
    except Exception:
        pass
    return False


def guard_startup() -> None:
    """Run once at app start. Sets tamper flag instead of exiting loudly."""
    global _tamper_flag
    if not licensing_required():
        return
    if _debugger_attached():
        _tamper_flag = True


def _tampered() -> bool:
    return _tamper_flag


# ----------------------------------------------------------------------------- #
# DPAPI-protected license blob (Windows)
# ----------------------------------------------------------------------------- #
def _dpapi_protect(plain: bytes) -> bytes | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        in_blob = DATA_BLOB(len(plain), ctypes.cast(ctypes.create_string_buffer(plain), ctypes.POINTER(ctypes.c_char)))
        out_blob = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return None


def _dpapi_unprotect(cipher: bytes) -> bytes | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        in_blob = DATA_BLOB(
            len(cipher),
            ctypes.cast(ctypes.create_string_buffer(cipher), ctypes.POINTER(ctypes.c_char)),
        )
        out_blob = DATA_BLOB()
        if not ctypes.windll.crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, 0, ctypes.byref(out_blob)
        ):
            return None
        try:
            return ctypes.string_at(out_blob.pbData, out_blob.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(out_blob.pbData)
    except Exception:
        return None


def _encode_license_blob(data: dict) -> bytes:
    raw = json.dumps(data, separators=(",", ":")).encode("utf-8")
    protected = _dpapi_protect(raw)
    if protected is not None:
        return b"DPAPI1" + protected
    return b"PLAIN1" + raw


def _decode_license_blob(blob: bytes) -> dict | None:
    if blob.startswith(b"DPAPI1"):
        plain = _dpapi_unprotect(blob[6:])
        if plain is None:
            return None
        try:
            return json.loads(plain.decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return None
    if blob.startswith(b"PLAIN1"):
        try:
            return json.loads(blob[6:].decode("utf-8"))
        except (ValueError, json.JSONDecodeError):
            return None
    try:
        return json.loads(blob.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None


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
        if (node >> 40) & 0x1:
            return ""
        return f"{node:012x}"
    except Exception:
        return ""


def _board_serial() -> str:
    try:
        import subprocess

        out = subprocess.check_output(
            ["wmic", "baseboard", "get", "serialnumber"],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            stderr=subprocess.DEVNULL,
            timeout=4,
        )
        lines = [ln.strip() for ln in out.decode("utf-8", "ignore").splitlines() if ln.strip()]
        for line in lines:
            low = line.lower()
            if low not in ("serialnumber", "to be filled by o.e.m.", "default string", "none"):
                return line
    except Exception:
        pass
    return ""


def compute_hwid() -> str:
    parts = [
        _machine_guid(),
        _volume_serial(),
        _mac_node(),
        _board_serial(),
        os.environ.get("COMPUTERNAME", ""),
        os.environ.get("USERNAME", ""),
    ]
    raw = _HWID_SALT + "|" + "|".join(parts)
    return hashlib.sha256(raw.encode("utf-8", "ignore")).hexdigest()[:32]


# ----------------------------------------------------------------------------- #
# License file
# ----------------------------------------------------------------------------- #
def _load_license_file() -> dict:
    try:
        if LICENSE_FILE.is_file():
            data = _decode_license_blob(LICENSE_FILE.read_bytes())
            if isinstance(data, dict):
                return data
    except OSError:
        pass
    try:
        if LICENSE_FILE_LEGACY.is_file():
            data = json.loads(LICENSE_FILE_LEGACY.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                _save_license_file(data)
                try:
                    LICENSE_FILE_LEGACY.unlink()
                except OSError:
                    pass
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def _save_license_file(data: dict) -> None:
    try:
        ensure_app_data_dirs()
        LICENSE_FILE.write_bytes(_encode_license_blob(data))
    except OSError as error:
        from blossom_logging import get_logger

        get_logger("license").error("Could not save license file: %s", error)


def clear_license() -> None:
    for path in (LICENSE_FILE, LICENSE_FILE_LEGACY):
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass
    _set_cached(None)


def mask_key(key: str) -> str:
    key = (key or "").strip()
    if len(key) <= 6:
        return key
    return key[:5] + "…" + key[-4:]


# ----------------------------------------------------------------------------- #
# Token verification
# ----------------------------------------------------------------------------- #
def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def _verify_token(token: str, *, hwid: str) -> dict | None:
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
    if payload.get("ch") != _TOKEN_CHANNEL:
        return None
    if BUILD_WATERMARK:
        token_wm = str(payload.get("wm") or "")
        if token_wm != BUILD_WATERMARK:
            return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)) or exp < time.time():
        return None

    if ED25519_PUBLIC_KEY_HEX:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(ED25519_PUBLIC_KEY_HEX))
            pub.verify(_b64url_decode(sig_b64), body_b64.encode("ascii"))
        except ImportError:
            if is_frozen():
                return None
        except Exception:
            return None
    return payload


# ----------------------------------------------------------------------------- #
# Server calls
# ----------------------------------------------------------------------------- #
def _configure_tls() -> None:
    """Point HTTPS clients at certifi's CA bundle (needed in some frozen builds)."""
    global _HTTP_TLS_CONFIGURED
    if _HTTP_TLS_CONFIGURED:
        return
    _HTTP_TLS_CONFIGURED = True
    try:
        import certifi

        ca_bundle = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)
    except ImportError:
        pass


def _classify_request_error(error: Exception) -> str:
    try:
        import requests

        if isinstance(error, requests.exceptions.Timeout):
            return "timeout"
        if isinstance(error, requests.exceptions.SSLError):
            return "ssl_error"
        if isinstance(error, requests.exceptions.ConnectionError):
            msg = str(error).lower()
            if "getaddrinfo" in msg or "nameresolution" in msg or "nodename" in msg:
                return "dns_error"
            return "offline"
    except ImportError:
        pass
    msg = str(error).lower()
    if "timed out" in msg:
        return "timeout"
    if "ssl" in msg or "certificate" in msg:
        return "ssl_error"
    if "getaddrinfo" in msg or "nodename" in msg:
        return "dns_error"
    return "offline"


def _parse_http_response(status_code: int, body: str) -> dict:
    try:
        data = json.loads(body)
    except (ValueError, json.JSONDecodeError):
        if status_code == 404:
            return {"ok": False, "reason": "not_found"}
        if status_code >= 500:
            return {"ok": False, "reason": "server_error"}
        return {"ok": False, "reason": f"http_{status_code}"}
    if not isinstance(data, dict):
        return {"ok": False, "reason": "bad_json"}
    if status_code >= 500:
        data.setdefault("reason", "server_error")
    return data


def _client_meta() -> dict:
    meta = {
        "version": APP_VERSION,
        "channel": _TOKEN_CHANNEL,
    }
    if BUILD_WATERMARK:
        meta["wm"] = BUILD_WATERMARK
    if BUILD_INTEGRITY:
        meta["integrity"] = BUILD_INTEGRITY
    return meta


def _http_json(method: str, path: str, payload: dict | None = None) -> dict:
    if not LICENSE_SERVER_URL:
        return {"ok": False, "reason": "unconfigured"}
    _configure_tls()
    url = f"{LICENSE_SERVER_URL}{path}"
    headers = {"User-Agent": _HTTP_USER_AGENT}
    request_error: Exception | None = None

    try:
        import requests

        if method.upper() == "GET":
            resp = requests.get(url, timeout=HTTP_TIMEOUT_SEC, headers=headers)
        else:
            resp = requests.post(
                url, json=payload or {}, timeout=HTTP_TIMEOUT_SEC, headers=headers
            )
        return _parse_http_response(resp.status_code, resp.text)
    except ImportError:
        pass
    except Exception as error:
        request_error = error

    try:
        from urllib import error as urlerror
        from urllib import request as urlrequest

        data_bytes = (
            json.dumps(payload or {}).encode("utf-8") if method.upper() != "GET" else None
        )
        req = urlrequest.Request(
            url,
            data=data_bytes,
            headers={**headers, "Content-Type": "application/json"},
            method=method.upper(),
        )
        with urlrequest.urlopen(req, timeout=HTTP_TIMEOUT_SEC) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return _parse_http_response(getattr(resp, "status", 200), body)
    except urlerror.HTTPError as error:
        try:
            body = error.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        return _parse_http_response(error.code, body)
    except Exception as error:
        if request_error is not None:
            return {"ok": False, "reason": _classify_request_error(request_error)}
        return {"ok": False, "reason": _classify_request_error(error)}

    if request_error is not None:
        return {"ok": False, "reason": _classify_request_error(request_error)}
    return {"ok": False, "reason": "offline"}


def _fetch_challenge() -> str | None:
    """Return a one-time nonce when the server supports GET /challenge."""
    result = _http_json("GET", "/challenge")
    if result.get("ok") and result.get("nonce"):
        return str(result["nonce"])
    reason = str(result.get("reason") or "")
    # Older workers accept POST /activate and /validate without a nonce.
    if reason in ("not_found", "http_404"):
        return None
    return None


def _post(path: str, payload: dict) -> dict:
    body = {**payload, **_client_meta()}
    nonce = _fetch_challenge()
    if nonce:
        body["nonce"] = nonce
    result = _http_json("POST", path, body)
    if result.get("reason") == "invalid_nonce" and nonce:
        # Server rejected the nonce — retry once without it (legacy compatibility).
        retry_body = {**payload, **_client_meta()}
        return _http_json("POST", path, retry_body)
    return result


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
        "state": state,
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


def _deny_status(reason: str = "tampered") -> dict:
    return _status("invalid", reason=reason)


# ----------------------------------------------------------------------------- #
# Public API
# ----------------------------------------------------------------------------- #
def is_licensed() -> bool:
    if not licensing_required():
        return True
    if _tampered():
        return False
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

    last = float(data.get("last_validated") or 0)
    within_grace = (time.time() - last) < GRACE_HOURS * 3600
    return bool(within_grace)


def get_status(*, refresh: bool = True) -> dict:
    if not licensing_required():
        status = _not_required_status()
        _set_cached(status)
        return status

    if _tampered():
        status = _deny_status("tampered")
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
    if reason in _NETWORK_REASONS:
        return _evaluate_offline(key, hwid, data)

    status = _status("invalid", reason=reason, key=key)
    _set_cached(status)
    return status


def activate(key: str) -> dict:
    key = (key or "").strip().upper()
    if not licensing_required():
        return _not_required_status()
    if _tampered():
        return _deny_status("tampered")
    if not key:
        return _status("unlicensed", reason="invalid_key")
    if _build_expired():
        return _status("expired_build", reason="expired_build")

    hwid = compute_hwid()
    result = _post("/activate", {"key": key, "hwid": hwid})
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
    state = "offline" if reason in _NETWORK_REASONS else "invalid"
    status = _status(state, reason=reason, key=key)
    _set_cached(status)
    try:
        from blossom_logging import get_logger

        get_logger("license").warning(
            "Activation failed — state=%s reason=%s",
            state,
            reason,
        )
    except Exception:
        pass
    return status
