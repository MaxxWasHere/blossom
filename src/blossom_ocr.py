"""WinOCR helper for merchant name / item detection (ported from Coteab macro)."""

from __future__ import annotations

import asyncio
import difflib
import subprocess
import threading

# OCR misdetection corrections (from the original Noteab Merchant_Handler).
OCR_MISDETECT_KEY: dict[str, str] = {
    "heovenly potion": "heavenly potion",
    "heovenly potion!": "heavenly potion",
    "heavenly potion": "heavenly potion",
    "heavenly potion!": "heavenly potion",
    "rune of goloxy": "rune of galaxy",
    "rune of roinstorm": "rune of rainstorm",
    "stronge potion": "strange potion",
    "stello's condle": "stella's candle",
    "merchont trocker": "merchant tracker",
    "rondom potion sock": "random potion sack",
    "geor a": "gear a",
    "geor b": "gear b",
}

_ocr_lock = threading.Lock()
_init_done = False
_ocr_ready = False
_warned_missing = False
_windows_ocr_checked = False
_windows_ocr_ready = False


def _check_windows_ocr_language() -> bool:
    """True when the en-US Windows OCR language capability is installed."""
    global _windows_ocr_checked, _windows_ocr_ready
    if _windows_ocr_checked:
        return _windows_ocr_ready
    _windows_ocr_checked = True
    try:
        script = (
            "(Get-WindowsCapability -Online | "
            "Where-Object { $_.Name -like 'Language.OCR*en-US*' }).State"
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            text=True,
            timeout=45,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _windows_ocr_ready = "Installed" in (result.stdout or "")
    except Exception as error:
        print(f"[ocr] Windows OCR language check failed: {error}")
        _windows_ocr_ready = False
    if not _windows_ocr_ready:
        print(
            "[ocr] Windows OCR language pack (en-US) is not installed. "
            "Run in an elevated PowerShell: "
            "Add-WindowsCapability -Online -Name Language.OCR~~~en-US~0.0.1.0"
        )
    return _windows_ocr_ready


def _recognize_pil(image, *, lang: str = "en") -> str:
    import winocr

    async def _run() -> str:
        result = await winocr.recognize_pil(image, lang)
        return str(getattr(result, "text", "") or "").strip()

    try:
        return asyncio.run(_run())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()


def init_ocr() -> bool:
    """Ensure WinOCR is available. Safe to call repeatedly."""
    global _init_done, _ocr_ready
    if _init_done:
        return _ocr_ready
    with _ocr_lock:
        if _init_done:
            return _ocr_ready
        _init_done = True
        if not _check_windows_ocr_language():
            return False
        try:
            from blossom_runtime_deps import ensure_winocr

            if not ensure_winocr():
                return False
        except Exception as error:
            print(f"[ocr] WinOCR runtime setup failed: {error}")
            return False
        _ocr_ready = True
        print("[ocr] WinOCR ready.")
        return True


def ocr_available() -> bool:
    return init_ocr()


def tesseract_available() -> bool:
    """Backward-compatible alias for code that still checks Tesseract naming."""
    return ocr_available()


def ocr_status() -> dict:
    """Status for UI: installed, language_missing, runtime_missing, unavailable."""
    from blossom_runtime_deps import winocr_status

    runtime = winocr_status()
    runtime_state = str(runtime.get("state") or "")

    if init_ocr():
        return {"state": "installed", "runtime": runtime}

    if runtime_state == "installed":
        lang_ok = _windows_ocr_checked and _windows_ocr_ready
        if not _windows_ocr_checked:
            lang_ok = _check_windows_ocr_language()
        if not lang_ok:
            return {
                "state": "language_missing",
                "runtime": runtime,
                "message": (
                    "Windows OCR language pack (en-US) is not installed. "
                    "Install it with: Add-WindowsCapability -Online "
                    "-Name Language.OCR~~~en-US~0.0.1.0"
                ),
            }
        return {
            "state": "installed",
            "runtime": runtime,
            "message": "WinOCR runtime is installed.",
        }

    lang_ok = _windows_ocr_checked and _windows_ocr_ready
    if not _windows_ocr_checked:
        lang_ok = _check_windows_ocr_language()
    if not lang_ok:
        return {
            "state": "language_missing",
            "runtime": runtime,
            "message": (
                "Windows OCR language pack (en-US) is not installed. "
                "Install it with: Add-WindowsCapability -Online "
                "-Name Language.OCR~~~en-US~0.0.1.0"
            ),
        }
    if runtime_state == "unavailable":
        return {
            "state": "unavailable",
            "runtime": runtime,
            "message": runtime.get("message")
            or "WinOCR bundle is not published for this build yet.",
        }
    return {
        "state": "not_installed",
        "runtime": runtime,
        "message": "WinOCR runtime is not installed yet.",
    }


def warn_if_unavailable() -> bool:
    global _warned_missing
    if init_ocr():
        return True
    if not _warned_missing:
        _warned_missing = True
        status = ocr_status()
        print(
            "[ocr] WinOCR unavailable — merchant OCR auto-buy disabled. "
            f"{status.get('message', '')}"
        )
    return False


def ocr_region(region: tuple[int, int, int, int], *, psm: int = 6) -> str:
    """Return OCR text for a screen region (left, top, width, height). '' on failure."""
    del psm  # WinOCR has no Tesseract PSM equivalent; kept for call-site compatibility.
    if not warn_if_unavailable():
        return ""
    try:
        import pyautogui

        x, y, w, h = (int(round(v)) for v in region)
        if w <= 0 or h <= 0:
            return ""
        screenshot = pyautogui.screenshot(region=(x, y, w, h))
        return _recognize_pil(screenshot, lang="en")
    except Exception as error:
        print(f"[ocr] region OCR failed for {region}: {error}")
        return ""


def fuzzy_match_any(text: str, candidates: tuple[str, ...] | list[str], *, threshold: float = 0.75) -> bool:
    """True when OCR text fuzzy-matches any candidate (original Noteab merchant detection)."""
    probe = (text or "").strip().lower()
    if not probe:
        return False
    for candidate in candidates:
        if difflib.SequenceMatcher(None, candidate.lower(), probe).ratio() >= threshold:
            return True
    return False


def correct_item_text(raw_text: str) -> str:
    """Apply the original OCR misdetection corrections; returns lowercased name."""
    name = (raw_text or "").split("|")[0].strip().lower()
    for misdetect, correct in OCR_MISDETECT_KEY.items():
        if misdetect in name:
            print(f"[ocr] corrected misdetection: {name!r} -> {correct!r}")
            return correct
    return name
