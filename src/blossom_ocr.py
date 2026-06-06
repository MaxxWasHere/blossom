"""Tesseract OCR helper for merchant name / item detection (ported from Coteab macro)."""

from __future__ import annotations

import difflib
import os
import shutil
import sys
from pathlib import Path

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

from blossom_dirs import dev_repo_root

_tesseract_cmd: str | None = None
_init_done = False
_warned_missing = False


def _bundle_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", dev_repo_root()))
    return dev_repo_root()


def _install_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return dev_repo_root()


def _candidate_tesseract_paths() -> list[Path]:
    candidates: list[Path] = []
    for base in (_bundle_dir(), _install_dir()):
        candidates.append(base / "assets" / "tesseract" / "tesseract.exe")
        candidates.append(base / "tesseract" / "tesseract.exe")
    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        candidates.append(Path(local) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
    for env in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        root = os.environ.get(env, "")
        if root:
            candidates.append(Path(root) / "Tesseract-OCR" / "tesseract.exe")
    return candidates


def _locate_tesseract() -> str | None:
    for path in _candidate_tesseract_paths():
        try:
            if path.is_file():
                return str(path)
        except OSError:
            continue
    found = shutil.which("tesseract")
    if found:
        return found
    return None


def init_tesseract() -> bool:
    """Locate Tesseract and configure pytesseract. Safe to call repeatedly."""
    global _tesseract_cmd, _init_done
    if _init_done:
        return _tesseract_cmd is not None
    _init_done = True

    cmd = _locate_tesseract()
    if not cmd:
        # Stay quiet here: init runs from passive readiness/status checks at
        # startup (biome selector, calibration status), and printing the "auto-buy
        # disabled" warning then surfaces as a scary notice before the user has
        # asked for anything OCR-related. The warning is emitted only when OCR is
        # actually attempted — see warn_if_unavailable() / ocr_region().
        return False

    try:
        import pytesseract

        pytesseract.pytesseract.tesseract_cmd = cmd
    except Exception as error:
        print(f"[ocr] pytesseract import failed: {error}")
        return False

    # Point at bundled tessdata when present.
    tess_root = Path(cmd).parent
    tessdata = tess_root / "tessdata"
    if tessdata.is_dir():
        os.environ.setdefault("TESSDATA_PREFIX", str(tess_root))

    _tesseract_cmd = cmd
    print(f"[ocr] Tesseract ready: {cmd}")
    return True


def tesseract_available() -> bool:
    return init_tesseract()


def warn_if_unavailable() -> bool:
    """Warn (once) that OCR is unavailable, only when a feature actually needs it.

    Returns True when Tesseract is ready. Call this from the point a merchant-OCR
    or biome-selector OCR action is genuinely about to run — not from passive
    startup status checks — so the warning never pops on initial load.
    """
    global _warned_missing
    if init_tesseract():
        return True
    if not _warned_missing:
        _warned_missing = True
        print(
            "[ocr] Tesseract not found — merchant OCR auto-buy disabled. "
            "Bundle assets/tesseract/tesseract.exe or install Tesseract-OCR."
        )
    return False


def ocr_region(region: tuple[int, int, int, int], *, psm: int = 6) -> str:
    """Return OCR text for a screen region (left, top, width, height). '' on failure."""
    if not warn_if_unavailable():
        return ""
    try:
        import pyautogui
        import pytesseract

        x, y, w, h = (int(round(v)) for v in region)
        if w <= 0 or h <= 0:
            return ""
        screenshot = pyautogui.screenshot(region=(x, y, w, h))
        text = pytesseract.image_to_string(screenshot, config=f"--psm {psm}")
        return text.strip()
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
