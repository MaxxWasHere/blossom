"""User custom UI CSS from %LOCALAPPDATA%\\Blossom\\themes\\ (CSS-only, sandboxed)."""

from __future__ import annotations

import re
from pathlib import Path

from blossom_dirs import THEMES_DIR, ensure_app_data_dirs

SAMPLE_FILENAME = "custom-ui.example.css"
SAMPLE_MARKER = "Blossom full custom UI template v2"
MAX_CSS_BYTES = 512 * 1024

_UNSAFE_CSS_PATTERNS = (
    re.compile(r"<script", re.IGNORECASE),
    re.compile(r"</script", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
    re.compile(r"vbscript:", re.IGNORECASE),
    re.compile(r"expression\s*\(", re.IGNORECASE),
    re.compile(r"@import\s", re.IGNORECASE),
    re.compile(r"behavior\s*:", re.IGNORECASE),
    re.compile(r"-moz-binding\s*:", re.IGNORECASE),
    re.compile(r"data:text/html", re.IGNORECASE),
    re.compile(r"<\s*(iframe|object|embed|link|meta|base)\b", re.IGNORECASE),
    re.compile(
        r"url\s*\(\s*['\"]?(?!data:)[^'\"]*(?://|https?:|ftp:)",
        re.IGNORECASE,
    ),
)


def ensure_themes_dir() -> Path:
    ensure_app_data_dirs()
    return THEMES_DIR


def _sample_css_text() -> str:
    return """\
/*
  Blossom full custom UI template v2

  Copy this file to a new name (e.g. my-theme.css), edit it, then select it
  under Appearance -> Full custom theme.

  Folder (CSS only — never put HTML or JS here):
  %LOCALAPPDATA%\\Blossom\\themes\\

  When selected, YOUR file controls the whole look. Built-in Pink/Dark/Light
  are stored as fallback but not applied until you set Custom = None.
  Only CSS variables and selectors — no scripts, imports, or remote URLs.
*/

/* ── Design tokens (set all surfaces here) ── */
body,
body[data-theme="custom"] {
  /* App shell */
  --bg-root: #0a0809;
  --bg-sidebar: #100c0e;
  --bg-main: #0d090b;

  /* Cards & panels */
  --bg-card: #161014;
  --bg-card-hover: #1c1519;
  --card-bg: var(--bg-card);
  --bg-secondary: var(--bg-card);
  --shadow-card: 0 2px 12px rgba(0, 0, 0, 0.3);

  /* Inputs */
  --bg-input: #120e10;
  --bg-input-focus: #1a1418;

  /* Accent & brand */
  --accent: #e891a8;
  --accent-dim: #c46d88;
  --accent-text: #f5c6d4;
  --accent-glow: rgba(232, 145, 168, 0.15);
  --border-accent: rgba(232, 145, 168, 0.3);
  --shadow-glow: 0 0 20px rgba(232, 145, 168, 0.08);

  /* Status colors */
  --success: #22c55e;
  --success-dim: #16a34a;
  --danger: #ef4444;
  --danger-dim: #dc2626;
  --warning: #f59e0b;

  /* Text */
  --text-primary: #ece8ea;
  --text-secondary: #a8a0a4;
  --text-muted: #6e6468;

  /* Borders */
  --border: #241a1e;
  --border-hover: #32242a;
  --border-color: var(--border);

  /* Shape & motion */
  --radius-sm: 0px;
  --radius-md: 0px;
  --radius-lg: 0px;
  --radius-xl: 0px;
  --transition: 0.2s cubic-bezier(0.4, 0, 0.2, 1);

  color: var(--text-primary);
  background: var(--bg-root);
  font-family: Sarpanch, Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

/* ── Shell: title bar, sidebar, main ── */
.window-frame {
  background: var(--bg-root);
}

.titlebar,
.coteab-injected-titlebar {
  background: var(--bg-sidebar);
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
}

.sidebar {
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
}

.page-content,
.main-content {
  background: var(--bg-main);
}

/* ── Cards (macro tabs, Appearance, webhooks, etc.) ── */
.card {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
}

.card-header h3 {
  color: var(--text-primary);
}

.card-header p,
.form-hint,
.page-header p {
  color: var(--text-muted);
}

/* ── Forms & buttons ── */
.form-input,
select.form-input,
textarea.form-input {
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text-primary);
}

.form-input:focus {
  background: var(--bg-input-focus);
  border-color: var(--border-hover);
}

.form-label {
  color: var(--text-secondary);
}

.btn-accent {
  background: var(--accent);
  color: var(--accent-text);
  border-color: var(--accent-dim);
}

.btn-secondary {
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text-primary);
}

/* ── Sidebar nav ── */
.nav-item {
  color: var(--text-secondary);
}

.nav-item.active,
.nav-item:hover {
  color: var(--text-primary);
  background: var(--bg-card-hover);
}

/* ── Modals & overlays (license, intro, update toast) ── */
.blossom-update-dialog,
.blossom-license-card,
.blossom-credits-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
}

/* ── Scrollbars (WebView2 / Chromium) ── */
* {
  scrollbar-color: var(--border-hover) var(--bg-input);
}

*::-webkit-scrollbar {
  width: 10px;
  height: 10px;
}

*::-webkit-scrollbar-thumb {
  background: var(--border-hover);
  border-radius: 4px;
}

*::-webkit-scrollbar-track {
  background: var(--bg-input);
}
"""


def ensure_sample_custom_ui_file() -> None:
    ensure_themes_dir()
    sample = THEMES_DIR / SAMPLE_FILENAME
    if not sample.is_file() or SAMPLE_MARKER not in sample.read_text(encoding="utf-8", errors="replace"):
        sample.write_text(_sample_css_text(), encoding="utf-8")


def _safe_css_basename(name: str) -> str | None:
    base = Path(str(name or "").strip()).name
    if not base or base.startswith("."):
        return None
    if not base.lower().endswith(".css"):
        return None
    if base != Path(name).name or ".." in str(name):
        return None
    if base.lower().endswith(".example.css"):
        return None
    return base


def _is_listable_theme(path: Path) -> bool:
    name = path.name.lower()
    return name.endswith(".css") and not name.endswith(".example.css")


def _css_is_safe(text: str) -> bool:
    for pattern in _UNSAFE_CSS_PATTERNS:
        if pattern.search(text):
            return False
    return True


def _read_css(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size <= 0 or size > MAX_CSS_BYTES:
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    if not _css_is_safe(text):
        return None
    return text


def list_custom_ui_themes() -> list[dict]:
    ensure_sample_custom_ui_file()
    out: list[dict] = []
    for path in sorted(ensure_themes_dir().glob("*.css")):
        if not _is_listable_theme(path):
            continue
        label = path.stem.replace("-", " ").replace("_", " ")
        out.append({"filename": path.name, "label": label})
    return out


def read_custom_ui_css(filename: str) -> dict:
    fname = _safe_css_basename(filename)
    if not fname:
        return {"ok": False, "error": "Invalid filename."}

    path = ensure_themes_dir() / fname
    css = _read_css(path)
    if css is None:
        if not path.is_file():
            return {"ok": False, "error": f'Could not load "{fname}".'}
        return {"ok": False, "error": f'"{fname}" was blocked (unsafe CSS or too large).'}

    return {"ok": True, "css": css, "filename": fname}
