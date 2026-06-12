"""Deprecated JSON UI themes — retained for reference only.

Blossom 2.2+ uses a single custom CSS file (`blossom_custom_ui.py`) for
power-user theming. JSON theme APIs were removed from the app; existing
`.json` files in the themes folder are left untouched for manual migration.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from blossom_dirs import THEMES_DIR, ensure_app_data_dirs

SAMPLE_THEME_FILENAME = "theme.example.json"
SAMPLE_THEME_MARKER = "Blossom JSON theme template v1"
MAX_THEME_BYTES = 3 * 1024 * 1024  # background image data URIs live inside
MAX_IMAGE_DATA_URI_BYTES = int(2.5 * 1024 * 1024)
MAX_ICON_SVG_CHARS = 4000
THEME_SCHEMA_VERSION = 1

# Theme color keys -> CSS custom properties (the frontend owns the same map).
COLOR_KEYS = {
    "bgRoot": "--bg-root",
    "bgSidebar": "--bg-sidebar",
    "bgMain": "--bg-main",
    "bgCard": "--bg-card",
    "bgCardHover": "--bg-card-hover",
    "bgInput": "--bg-input",
    "bgInputFocus": "--bg-input-focus",
    "accent": "--accent",
    "accentDim": "--accent-dim",
    "accentText": "--accent-text",
    "textPrimary": "--text-primary",
    "textSecondary": "--text-secondary",
    "textMuted": "--text-muted",
    "border": "--border",
    "borderHover": "--border-hover",
    "success": "--success",
    "successDim": "--success-dim",
    "danger": "--danger",
    "dangerDim": "--danger-dim",
    "warning": "--warning",
}

BASE_THEMES = ("pink", "dark", "light", "oled", "sakura", "midnight", "forest")
BACKGROUND_TYPES = ("none", "gradient", "image")
IMAGE_FITS = ("cover", "contain", "center", "tile")
RADIUS_KEYS = ("sm", "md", "lg", "xl")
TAB_STYLES = ("default", "underline", "pill")
BUTTON_STYLES = ("default", "pill", "square")
MAX_EXTRA_CSS_CHARS = 16384

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")
_FUNC_COLOR_RE = re.compile(
    r"^(?:rgb|rgba|hsl|hsla)\(\s*[\d.]+(?:deg|%)?\s*(?:[,\s]\s*[\d.]+%?\s*){2}"
    r"(?:[,/]\s*[\d.]+%?\s*)?\)$"
)
_FONT_FAMILY_RE = re.compile(r"^[A-Za-z0-9 ,'\"\-]{1,120}$")
_IMAGE_DATA_URI_RE = re.compile(
    r"^data:image/(?:png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=]+$"
)
_SVG_FORBIDDEN_RE = re.compile(
    r"(?:<\s*script|<\s*style|<\s*foreignObject|<\s*image|<\s*use|<\s*a\b"
    r"|on[a-z]+\s*=|href|xlink|javascript:|url\s*\(|<!\[CDATA\[|<!--)",
    re.IGNORECASE,
)
_SVG_TAG_RE = re.compile(r"<\s*/?\s*([A-Za-z][A-Za-z0-9]*)")
_SVG_ALLOWED_TAGS = {
    "path", "circle", "rect", "line", "polyline", "polygon", "ellipse", "g",
}
_EXTRA_CSS_UNSAFE_RE = re.compile(
    r"(?:<\s*script|<\s*style|@import\s|javascript:|vbscript:|expression\s*\(|"
    r"behavior\s*:|-moz-binding\s*:|data:text/html|<\s*(?:iframe|object|embed|"
    r"link|meta|base)\b|url\s*\(\s*['\"]?(?!data:)[^'\"]*(?://|https?:|ftp:))",
    re.IGNORECASE,
)


def ensure_themes_dir() -> Path:
    ensure_app_data_dirs()
    return THEMES_DIR


def _is_color(value) -> bool:
    if not isinstance(value, str):
        return False
    v = value.strip()
    return bool(_HEX_COLOR_RE.match(v) or _FUNC_COLOR_RE.match(v))


def _clean_color(value) -> str | None:
    if _is_color(value):
        return str(value).strip()
    return None


def _clean_name(value) -> str:
    name = re.sub(r"[\x00-\x1f<>&\"']", "", str(value or "")).strip()
    return name[:60] or "Custom theme"


def _clamp_num(value, lo, hi, default):
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n:  # NaN
        return default
    return max(lo, min(hi, n))


def _sanitize_extra_css(raw) -> str:
    if not isinstance(raw, str):
        return ""
    text = raw.strip()
    if not text:
        return ""
    if len(text) > MAX_EXTRA_CSS_CHARS:
        text = text[:MAX_EXTRA_CSS_CHARS]
    if _EXTRA_CSS_UNSAFE_RE.search(text):
        return ""
    return text


def _svg_markup_is_safe(markup: str) -> bool:
    if not isinstance(markup, str):
        return False
    if len(markup) > MAX_ICON_SVG_CHARS:
        return False
    if _SVG_FORBIDDEN_RE.search(markup):
        return False
    for tag in _SVG_TAG_RE.findall(markup):
        if tag.lower() not in _SVG_ALLOWED_TAGS:
            return False
    return True


def sanitize_theme(raw) -> dict:
    """Return a normalized, whitelisted theme dict (never raises).

    Unknown keys are dropped; invalid values are dropped or clamped. The
    result is safe to hand to the frontend compiler.
    """
    src = raw if isinstance(raw, dict) else {}
    out: dict = {
        "schema": THEME_SCHEMA_VERSION,
        "name": _clean_name(src.get("name")),
    }

    base = str(src.get("base") or "").strip().lower()
    out["base"] = base if base in BASE_THEMES else "dark"

    colors_src = src.get("colors") if isinstance(src.get("colors"), dict) else {}
    colors = {}
    for key in COLOR_KEYS:
        cleaned = _clean_color(colors_src.get(key))
        if cleaned:
            colors[key] = cleaned
    out["colors"] = colors

    font_src = src.get("font") if isinstance(src.get("font"), dict) else {}
    font = {}
    family = str(font_src.get("family") or "").strip()
    if family and _FONT_FAMILY_RE.match(family):
        font["family"] = family
    size = _clamp_num(font_src.get("size"), 10, 18, 0)
    if size:
        font["size"] = round(size, 1)
    out["font"] = font

    radius_src = src.get("radius") if isinstance(src.get("radius"), dict) else {}
    radius = {}
    for key in RADIUS_KEYS:
        if key in radius_src:
            radius[key] = int(_clamp_num(radius_src.get(key), 0, 32, 0))
    out["radius"] = radius

    bg_src = src.get("background") if isinstance(src.get("background"), dict) else {}
    bg_type = str(bg_src.get("type") or "none").strip().lower()
    background: dict = {"type": bg_type if bg_type in BACKGROUND_TYPES else "none"}
    if background["type"] == "gradient":
        background["angle"] = int(_clamp_num(bg_src.get("angle"), 0, 360, 135))
        grad_colors = bg_src.get("colors")
        cleaned_colors = []
        if isinstance(grad_colors, list):
            for c in grad_colors[:4]:
                cc = _clean_color(c)
                if cc:
                    cleaned_colors.append(cc)
        if len(cleaned_colors) >= 2:
            background["colors"] = cleaned_colors
        else:
            background = {"type": "none"}
    elif background["type"] == "image":
        image = str(bg_src.get("image") or "")
        if (
            len(image) <= MAX_IMAGE_DATA_URI_BYTES
            and _IMAGE_DATA_URI_RE.match(image)
        ):
            background["image"] = image
            fit = str(bg_src.get("imageFit") or "cover").strip().lower()
            background["imageFit"] = fit if fit in IMAGE_FITS else "cover"
            background["overlay"] = round(
                _clamp_num(bg_src.get("overlay"), 0, 0.92, 0.55), 2
            )
        else:
            background = {"type": "none"}
    out["background"] = background

    icons_src = src.get("icons") if isinstance(src.get("icons"), dict) else {}
    icons: dict = {}
    icon_color = _clean_color(icons_src.get("color"))
    if icon_color:
        icons["color"] = icon_color
    stroke = _clamp_num(icons_src.get("strokeWidth"), 1, 3, 0)
    if stroke:
        icons["strokeWidth"] = round(stroke, 2)
    overrides_src = icons_src.get("overrides")
    if isinstance(overrides_src, dict):
        overrides = {}
        for icon_name, markup in list(overrides_src.items())[:80]:
            key = re.sub(r"[^a-z0-9_-]", "", str(icon_name).lower())[:40]
            if key and _svg_markup_is_safe(markup):
                overrides[key] = str(markup)
        if overrides:
            icons["overrides"] = overrides
    out["icons"] = icons

    layout_src = src.get("layout") if isinstance(src.get("layout"), dict) else {}
    layout: dict = {}
    sidebar_width = _clamp_num(layout_src.get("sidebarWidth"), 148, 280, 0)
    if sidebar_width:
        layout["sidebarWidth"] = int(sidebar_width)
    content_padding = _clamp_num(layout_src.get("contentPadding"), 8, 28, 0)
    if content_padding:
        layout["contentPadding"] = int(content_padding)
    out["layout"] = layout

    tabs_src = src.get("tabs") if isinstance(src.get("tabs"), dict) else {}
    tab_style = str(tabs_src.get("style") or "default").strip().lower()
    out["tabs"] = {"style": tab_style if tab_style in TAB_STYLES else "default"}

    buttons_src = src.get("buttons") if isinstance(src.get("buttons"), dict) else {}
    btn_style = str(buttons_src.get("style") or "default").strip().lower()
    out["buttons"] = {
        "style": btn_style if btn_style in BUTTON_STYLES else "default"
    }

    extra_src = src.get("extra") if isinstance(src.get("extra"), dict) else {}
    extra_css = _sanitize_extra_css(extra_src.get("css"))
    out["extra"] = {"css": extra_css} if extra_css else {}

    return out


def _safe_json_basename(name: str) -> str | None:
    base = Path(str(name or "").strip()).name
    if not base or base.startswith("."):
        return None
    if not base.lower().endswith(".json"):
        return None
    if base != Path(name).name or ".." in str(name):
        return None
    if re.search(r'[<>:"/\\|?*\x00-\x1f]', base):
        return None
    if base.lower().endswith(".example.json"):
        return None
    return base


def filename_for_theme_name(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    return (slug or f"theme-{int(time.time())}") + ".json"


def _is_listable_theme(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".json") and not name.endswith(".example.json")


def _sample_theme() -> dict:
    return {
        "_readme": (
            f"{SAMPLE_THEME_MARKER}. Copy to a new name (e.g. my-theme.json), "
            "edit, then pick it under Appearance -> Theme studio. Colors accept "
            "#hex / rgb() / hsl(). background.type: none | gradient | image "
            "(image = data: URI). layout.sidebarWidth (148-280), "
            "layout.contentPadding (8-28). tabs.style: default | underline | "
            "pill. buttons.style: default | pill | square. icons.overrides "
            "maps icon names (play, gear, …) to inner SVG markup. extra.css "
            "adds sanitized CSS rules (no @import or remote URLs). Unsafe "
            "values are dropped."
        ),
        "schema": THEME_SCHEMA_VERSION,
        "name": "Example theme",
        "base": "dark",
        "colors": {
            "bgRoot": "#0b0e14",
            "bgSidebar": "#0e1119",
            "bgMain": "#0c0f16",
            "bgCard": "#131722",
            "bgCardHover": "#1a1f2c",
            "bgInput": "#10141d",
            "bgInputFocus": "#171c28",
            "accent": "#7dd3fc",
            "textPrimary": "#e8ecf4",
            "textSecondary": "#9aa4b8",
            "textMuted": "#5e6779",
            "border": "#1d2330",
            "borderHover": "#2b3344",
        },
        "font": {"family": "Inter", "size": 13},
        "radius": {"sm": 8, "md": 10, "lg": 12, "xl": 14},
        "background": {
            "type": "gradient",
            "angle": 160,
            "colors": ["#0b0e14", "#101726"],
        },
        "icons": {
            "color": "#7dd3fc",
            "strokeWidth": 2,
            "overrides": {
                "play": "<path d=\"M5 5a2 2 0 0 1 3.008-1.728l11.997 6.998a2 2 0 0 1 .003 3.458l-12 7A2 2 0 0 1 5 19z\"/>"
            },
        },
        "layout": {"sidebarWidth": 200, "contentPadding": 14},
        "tabs": {"style": "pill"},
        "buttons": {"style": "pill"},
        "extra": {
            "css": (
                "body.blsm-json-theme .card { box-shadow: 0 2px 16px "
                "rgba(0, 0, 0, 0.25); }"
            )
        },
    }


def ensure_sample_theme_file() -> None:
    ensure_themes_dir()
    sample = THEMES_DIR / SAMPLE_THEME_FILENAME
    try:
        if sample.is_file() and SAMPLE_THEME_MARKER in sample.read_text(
            encoding="utf-8", errors="replace"
        ):
            return
    except OSError:
        pass
    try:
        sample.write_text(
            json.dumps(_sample_theme(), indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def _read_theme_file(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size <= 0 or size > MAX_THEME_BYTES:
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    return sanitize_theme(raw)


def list_json_themes() -> list[dict]:
    ensure_sample_theme_file()
    out: list[dict] = []
    for path in sorted(ensure_themes_dir().glob("*.json")):
        if not _is_listable_theme(path):
            continue
        theme = _read_theme_file(path)
        if theme is None:
            continue
        out.append({"filename": path.name, "name": theme.get("name") or path.stem})
    return out


def read_json_theme(filename: str) -> dict:
    fname = _safe_json_basename(filename)
    if not fname:
        return {"ok": False, "error": "Invalid filename."}
    theme = _read_theme_file(ensure_themes_dir() / fname)
    if theme is None:
        return {"ok": False, "error": f'Could not load "{fname}" (missing, too large, or invalid JSON).'}
    return {"ok": True, "filename": fname, "theme": theme}


def save_json_theme(filename: str, theme) -> dict:
    fname = _safe_json_basename(filename)
    if not fname:
        return {"ok": False, "error": "Invalid filename."}
    clean = sanitize_theme(theme)
    text = json.dumps(clean, indent=2)
    if len(text.encode("utf-8")) > MAX_THEME_BYTES:
        return {"ok": False, "error": "Theme is too large (max 3 MB)."}
    try:
        (ensure_themes_dir() / fname).write_text(text, encoding="utf-8")
    except OSError as error:
        return {"ok": False, "error": f"Could not save theme: {error}"}
    return {"ok": True, "filename": fname, "theme": clean}


def delete_json_theme(filename: str) -> dict:
    fname = _safe_json_basename(filename)
    if not fname:
        return {"ok": False, "error": "Invalid filename."}
    path = ensure_themes_dir() / fname
    if not path.is_file():
        return {"ok": False, "error": f'"{fname}" does not exist.'}
    try:
        path.unlink()
    except OSError as error:
        return {"ok": False, "error": f"Could not delete theme: {error}"}
    return {"ok": True, "filename": fname}
