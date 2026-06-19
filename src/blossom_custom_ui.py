"""User custom UI CSS from %LOCALAPPDATA%\\Blossom\\themes\\ (CSS-only, sandboxed)."""

from __future__ import annotations

import re
from pathlib import Path

from blossom_dirs import THEMES_DIR, ensure_app_data_dirs

SAMPLE_FILENAME = "custom-ui.example.css"
SAMPLE_MARKER = "Blossom full custom UI template v3"
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
  Blossom full custom UI template v3

  Copy this file to a new name (e.g. my-skin.css), edit it, then select it under
  Appearance → Custom UI → Refresh.

  Folder (CSS only — never put HTML or JS here):
  %LOCALAPPDATA%\\Blossom\\themes\\

  ── What Custom UI can do ──
  • Full visual reskin of the existing app — every painted surface if you target
    the selectors documented below.
  • Override design tokens (--accent, --bg-card, radii, fonts, shadows).
  • Layout tweaks on the current DOM (flex order, grid, gaps, hide with
    display:none, pseudo-element decorations, background images via data: URLs).

  ── What it cannot do (requires a Blossom build / fork) ──
  • Add or remove sidebar tabs, macro features, or settings sections.
  • Change React page structure, wire new buttons, or inject HTML/JS.
  • Replace the app with a totally different UI shell.

  When selected, YOUR file controls the whole look. Built-in themes are stored
  as fallback but not applied until Custom UI = None.
  No @import, remote url(), or script-like CSS — unsafe rules are blocked.
*/

/* ═══════════════════════════════════════════════════════════════════════════
   §1  DESIGN TOKENS — fastest way to reskin everything
   Set on body (or body[data-theme="custom"]). Most components read these.
   ═══════════════════════════════════════════════════════════════════════════ */
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
  --text-on-accent: #ffffff;

  /* Status colors */
  --success: #22c55e;
  --success-dim: #16a34a;
  --danger: #ef4444;
  --danger-dim: #dc2626;
  --warning: #f59e0b;

  /* Text */
  /* M3 Expressive roles (see assets/blossom-m3-tokens.css) map --accent/--bg-* → --md-sys-color-* */
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
  font-family: var(--font-body, "Google Sans Flex", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif);
}

/* html.blsm-custom-ui-active — set while Custom UI is active (Appearance card dims) */
/* html.blsm-light-ui — light palette hint; override tokens above for light skins */
/* html.blsm-reduce-motion — user disabled motion in Appearance */

/* ═══════════════════════════════════════════════════════════════════════════
   §2  WINDOW SHELL — outer frame, title bar, native resize handles
   Selectors: .window-frame, .titlebar, .coteab-injected-titlebar,
              .titlebar-btn, .blsm-window-resize, .blsm-window-resize-root
   ═══════════════════════════════════════════════════════════════════════════ */
.window-frame {
  background: var(--bg-root);
}

.titlebar,
.coteab-injected-titlebar {
  background: var(--bg-sidebar);
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
}

/* .titlebar-btn.minimize | .maximize | .close — window chrome buttons */

/* ═══════════════════════════════════════════════════════════════════════════
   §3  LAUNCH / DOWNLOAD OVERLAY — shown at startup and during runtime sync
   Selectors: #blossom-loading-overlay, .blossom-loading-overlay,
              .blossom-loading-card, .blossom-loading-brand,
              .blossom-loading-message, .blossom-loading-indicator,
              .blossom-m3-loading-canvas, .blossom-loading-progress,
              .blossom-loading-aurora
   ═══════════════════════════════════════════════════════════════════════════ */
#blossom-loading-overlay,
.blossom-loading-overlay {
  background: var(--bg-root);
  color: var(--text-primary);
}

.blossom-loading-card {
  /* Center card on the overlay */
}

/* ═══════════════════════════════════════════════════════════════════════════
   §4  SIDEBAR — brand, grouped nav, footer
   Selectors: .sidebar, .sidebar-brand, .sidebar-brand h1, .sidebar-brand .version,
              .sidebar-nav, .sidebar-section-label, .sidebar-group,
              .sidebar-item, .sidebar-item.active, .sidebar-item .icon,
              .sidebar-footer, .sidebar-footer .by-line
   Legacy alias: .nav-item (older React markup — prefer .sidebar-item)
   ═══════════════════════════════════════════════════════════════════════════ */
.sidebar {
  background: var(--bg-sidebar);
  border-right: 1px solid var(--border);
}

.sidebar-item {
  color: var(--text-secondary);
  border-radius: var(--radius-md);
}

.sidebar-item.active,
.sidebar-item:hover {
  color: var(--text-primary);
  background: var(--bg-card-hover);
}

.sidebar-section-label {
  color: var(--text-muted);
}

/* ═══════════════════════════════════════════════════════════════════════════
   §5  TOP HEADER BAR — start/stop macro, pin, status dropdown
   Selectors: .header-bar, .header-left, .header-right,
              .btn-start, .btn-stop, .pin-btn,
              .blossom-macro-btn-label, .blossom-dropdown (in header)
   ═══════════════════════════════════════════════════════════════════════════ */
.header-bar {
  background: var(--bg-sidebar);
  border-bottom: 1px solid var(--border);
}

.btn-start {
  background: var(--success);
  color: #fff;
}

.btn-stop {
  background: var(--danger);
  color: #fff;
}

/* ═══════════════════════════════════════════════════════════════════════════
   §6  MAIN CONTENT — page shell and route markers
   Selectors: .page-content, .main-content, .page-header, .page-header h2,
              .page-header p, .fade-in, .info-banner
   Route: .page-content[data-blossom-page="…"] or html.blsm-page-macro-calibrations
          html.blsm-biome-webhooks-active — page-specific overrides
   React mount: #root
   ═══════════════════════════════════════════════════════════════════════════ */
.page-content,
.main-content {
  background: var(--bg-main);
}

.page-header h2 {
  color: var(--text-primary);
}

.page-header p,
.info-banner {
  color: var(--text-muted);
}

/* Example: style one tab only
.page-content[data-blossom-page="Macro"] .card { … }
.page-content[data-blossom-page="Webhook"] .card { … }
.page-content[data-blossom-page="Macro Calibrations"] #blsm-cal-hub { … }
*/

/* ═══════════════════════════════════════════════════════════════════════════
   §7  CARDS — every settings / macro panel
   Selectors: .card, .card-header, .card-header h3, .card-header p, .card-icon,
              .corner-bracket.tl|.tr|.bl|.br (decorated macro cards)
   Blossom-injected cards: #blsm-appearance-card, #blsm-cal-hub,
              #blsm-biome-webhooks-hub, #blossom-runtime-card, .blsm-appearance-card
   ═══════════════════════════════════════════════════════════════════════════ */
.card {
  background: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-card);
}

.card-header h3 {
  color: var(--text-primary);
}

.card-header p,
.form-hint {
  color: var(--text-muted);
}

/* ═══════════════════════════════════════════════════════════════════════════
   §8  FORMS — inputs, labels, toggles, groups
   Selectors: .form-group, .form-label, .form-input, .form-hint,
              .toggle, .toggle-row, .toggle-switch, .toggle-slider,
              textarea.form-input, select.form-input, input[type="checkbox"]
   ═══════════════════════════════════════════════════════════════════════════ */
.form-input,
select.form-input,
textarea.form-input {
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text-primary);
  border-radius: var(--radius-sm);
}

.form-input:focus {
  background: var(--bg-input-focus);
  border-color: var(--border-hover);
}

.form-label {
  color: var(--text-secondary);
}

.toggle-switch input:checked + .toggle-slider {
  background: var(--accent);
}

/* ═══════════════════════════════════════════════════════════════════════════
   §9  BUTTONS
   Selectors: .btn, .btn-accent, .btn-secondary, .btn-danger (if used),
              .blsm-save-feedback-btn, .blsm-rt-btn
   ═══════════════════════════════════════════════════════════════════════════ */
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

/* ═══════════════════════════════════════════════════════════════════════════
   §10  CUSTOM DROPDOWNS — replaces native selects in many panels
   Selectors: .blossom-dropdown, .blossom-dropdown-trigger, .blossom-dropdown-label,
              .blossom-dropdown-chevron, .blossom-dropdown-menu,
              .blossom-dropdown-menu--portal, .blossom-dropdown-list,
              .blossom-dropdown-option, .blossom-dropdown-option.is-selected
   ═══════════════════════════════════════════════════════════════════════════ */
.blossom-dropdown-trigger {
  background: var(--bg-input);
  border: 1px solid var(--border);
  color: var(--text-primary);
}

.blossom-dropdown-option.is-selected {
  background: var(--accent-glow);
  color: var(--accent-text);
}

/* ═══════════════════════════════════════════════════════════════════════════
   §11  CALIBRATIONS HUB — Macro Calibrations tab
   Selectors: #blsm-cal-hub, .blsm-cal-tab-nav, .blsm-cal-tab, .blsm-cal-tab.is-active,
              .blsm-cal-mark-row, .blsm-cal-step-row, .blsm-mouse-cal-card,
              .blsm-cal-preset-card, .blsm-cal-hint-in-hub
   ═══════════════════════════════════════════════════════════════════════════ */
.blsm-cal-tab.is-active {
  color: var(--accent-text);
  border-color: var(--accent);
}

/* ═══════════════════════════════════════════════════════════════════════════
   §12  BIOME NOTIFIER / WEBHOOKS — Webhook tab hub
   Selectors: #blsm-biome-webhooks-hub, .blsm-legacy-biome-config-card (hidden)
   Table rows use inline grid in React — target .card descendants or hub id
   ═══════════════════════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════════════════════
   §13  RUNTIME COMPONENTS CARD — OpenCV / WinOCR sync UI
   Selectors: #blossom-runtime-card, .blsm-rt-card, .blsm-rt-body,
              .blsm-rt-status, .blsm-rt-progress, .blsm-rt-message,
              .blsm-rt-actions, .blsm-rt-btn
   data-state="installed" | "missing" | "downloading" on .blsm-rt-card
   ═══════════════════════════════════════════════════════════════════════════ */
.blsm-rt-card[data-state="installed"] .blsm-rt-status {
  color: var(--success);
}

/* ═══════════════════════════════════════════════════════════════════════════
   §14  APPEARANCE CARD (injected) — theme picker, custom UI controls
   Selectors: #blsm-appearance-card, .blsm-appearance-card, .blsm-app-section,
              .blsm-theme-grid, .blsm-theme-card, .blsm-accent-swatch,
              .blsm-seg, .blsm-seg-btn, .blsm-custom-ui-select
   html.blsm-custom-ui-active dims .blsm-theme-grid and .blsm-accent-section
   ═══════════════════════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════════════════════
   §15  MODALS & OVERLAYS — license gate, intro wizard, update toast, credits
   License: .blsm-license-overlay, .blsm-license-card, .blsm-license-input,
            .blsm-license-actions, .blsm-license-status, .blsm-license-hwid
   Intro:  .blsm-intro-overlay, .blsm-intro-card (first-run setup)
   Update: .blossom-update-overlay, .blossom-update-dialog, .blossom-update-x
           (.update-banner is hidden — Blossom uses the corner dialog)
   Credits / donations: .blsm-credits-card, .blossom-credits-card
   ═══════════════════════════════════════════════════════════════════════════ */
.blossom-update-dialog,
.blsm-license-card,
.blossom-credits-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
}

/* ═══════════════════════════════════════════════════════════════════════════
   §16  COMMAND PALETTE — Ctrl+K quick nav
   Selectors: #blsm-cmdk, .blsm-cmdk-backdrop, .blsm-cmdk-panel, .blsm-cmdk-input,
              .blsm-cmdk-list, .blsm-cmdk-item, .blsm-cmdk-item.is-active
   ═══════════════════════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════════════════════
   §17  ICONS — Lucide vectors injected by blossom-icons.js
   Selectors: .blsm-vec, .blsm-vec.is-solid, svg.blsm-vec path
   ═══════════════════════════════════════════════════════════════════════════ */
.blsm-vec {
  color: var(--text-secondary);
}

.sidebar-item.active .blsm-vec {
  color: var(--accent);
}

/* ═══════════════════════════════════════════════════════════════════════════
   §18  CHANGELOG TAB — rendered from noticetabcontents.txt
   Selectors: .changelog-item, .changelog-item h4, .changelog-item ul
   ═══════════════════════════════════════════════════════════════════════════ */

/* ═══════════════════════════════════════════════════════════════════════════
   §19  SCROLLBARS — WebView2 / Chromium
   ═══════════════════════════════════════════════════════════════════════════ */
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

/* ═══════════════════════════════════════════════════════════════════════════
   §20  ADVANCED — hide surfaces (visual only; features still exist in app)
   Uncomment to experiment. Hiding controls can break workflows.
   ═══════════════════════════════════════════════════════════════════════════ */
/*
.sidebar-footer { display: none !important; }
.header-bar .pin-btn { display: none !important; }
.blsm-theme-fallback-note { display: none !important; }
*/
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
