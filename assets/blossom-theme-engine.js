/*
 * Blossom theme engine — validates JSON themes and compiles them to CSS.
 *
 * JSON themes are structured data (colors, font, radii, background, icons),
 * never raw CSS. The Python side (blossom_theme_store.py) sanitizes files on
 * disk; this module re-validates everything before any string reaches the
 * DOM, so a hand-edited theme can't inject markup or remote URLs.
 *
 * Schema (v1):
 * {
 *   "schema": 1,
 *   "name": "My theme",
 *   "base": "pink|dark|light|oled|sakura|midnight|forest",
 *   "colors": { "bgRoot": "#0c0c0f", "accent": "#e891a8", ... },
 *   "font": { "family": "Inter", "size": 13 },
 *   "radius": { "sm": 8, "md": 10, "lg": 12, "xl": 14 },
 *   "background": { "type": "none|gradient|image", "angle": 135,
 *                   "colors": ["#111", "#222"], "image": "data:image/...",
 *                   "imageFit": "cover|contain|center|tile", "overlay": 0.55 },
 *   "icons": { "color": "#e891a8", "strokeWidth": 2,
 *              "overrides": { "play": "<path d=\"...\"/>" } },
 *   "layout": { "sidebarWidth": 200, "contentPadding": 14 },
 *   "tabs": { "style": "default|underline|pill" },
 *   "buttons": { "style": "default|pill|square" },
 *   "extra": { "css": "optional sanitized CSS rules" }
 * }
 */
(function () {
  "use strict";

  var SCHEMA_VERSION = 1;
  var BASE_THEMES = ["pink", "dark", "light", "oled", "sakura", "midnight", "forest"];
  var LIGHT_BASES = { light: 1, sakura: 1 };
  var BACKGROUND_TYPES = ["none", "gradient", "image"];
  var IMAGE_FITS = ["cover", "contain", "center", "tile"];
  var RADIUS_KEYS = ["sm", "md", "lg", "xl"];
  var TAB_STYLES = ["default", "underline", "pill"];
  var BUTTON_STYLES = ["default", "pill", "square"];
  var MAX_ICON_SVG_CHARS = 4000;
  var MAX_EXTRA_CSS_CHARS = 16384;

  var COLOR_VARS = {
    bgRoot: "--bg-root",
    bgSidebar: "--bg-sidebar",
    bgMain: "--bg-main",
    bgCard: "--bg-card",
    bgCardHover: "--bg-card-hover",
    bgInput: "--bg-input",
    bgInputFocus: "--bg-input-focus",
    accent: "--accent",
    accentDim: "--accent-dim",
    accentText: "--accent-text",
    textPrimary: "--text-primary",
    textSecondary: "--text-secondary",
    textMuted: "--text-muted",
    border: "--border",
    borderHover: "--border-hover",
    success: "--success",
    successDim: "--success-dim",
    danger: "--danger",
    dangerDim: "--danger-dim",
    warning: "--warning",
  };

  var HEX_RE = /^#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;
  var FUNC_RE = /^(?:rgb|rgba|hsl|hsla)\(\s*[\d.]+(?:deg|%)?\s*(?:[,\s]\s*[\d.]+%?\s*){2}(?:[,/]\s*[\d.]+%?\s*)?\)$/;
  var FONT_RE = /^[A-Za-z0-9 ,'"\-]{1,120}$/;
  var IMAGE_DATA_URI_RE = /^data:image\/(?:png|jpeg|jpg|gif|webp);base64,[A-Za-z0-9+/=]+$/;

  var SVG_ALLOWED_TAGS = { path: 1, circle: 1, rect: 1, line: 1, polyline: 1, polygon: 1, ellipse: 1, g: 1 };
  var SVG_ALLOWED_ATTRS = {
    d: 1, cx: 1, cy: 1, r: 1, rx: 1, ry: 1, x: 1, y: 1, x1: 1, x2: 1, y1: 1, y2: 1,
    width: 1, height: 1, points: 1, fill: 1, stroke: 1, "stroke-width": 1,
    "stroke-linecap": 1, "stroke-linejoin": 1, transform: 1, opacity: 1,
  };
  var SVG_SAFE_ATTR_VALUE_RE = /^[A-Za-z0-9 .,#()%\-]*$/;

  var isColor = function (v) {
    if (typeof v !== "string") return false;
    var s = v.trim();
    return HEX_RE.test(s) || FUNC_RE.test(s);
  };
  var cleanColor = function (v) {
    return isColor(v) ? String(v).trim() : null;
  };
  var clampNum = function (v, lo, hi, dflt) {
    var n = Number(v);
    if (!isFinite(n)) return dflt;
    return Math.max(lo, Math.min(hi, n));
  };
  var cleanName = function (v) {
    var name = String(v == null ? "" : v).replace(/[\x00-\x1f<>&"']/g, "").trim();
    return name.slice(0, 60) || "Custom theme";
  };

  var EXTRA_CSS_UNSAFE_RE =
    /(?:<\s*script|<\s*style|@import\s|javascript:|vbscript:|expression\s*\(|behavior\s*:|-moz-binding\s*:|data:text\/html|<\s*(?:iframe|object|embed|link|meta|base)\b|url\s*\(\s*['"]?(?!data:)[^'"]*(?:\/\/|https?:|ftp:))/i;

  var sanitizeExtraCss = function (raw) {
    if (typeof raw !== "string") return "";
    var text = raw.trim();
    if (!text) return "";
    if (text.length > MAX_EXTRA_CSS_CHARS) text = text.slice(0, MAX_EXTRA_CSS_CHARS);
    if (EXTRA_CSS_UNSAFE_RE.test(text)) return "";
    return text;
  };

  /* ---- icon SVG sanitization (DOM-based whitelist) ---- */

  var sanitizeIconSvg = function (markup) {
    if (typeof markup !== "string" || !markup || markup.length > MAX_ICON_SVG_CHARS) return null;
    if (/(?:<\s*script|on[a-z]+\s*=|javascript:|url\s*\(|href|xlink)/i.test(markup)) return null;
    var doc;
    try {
      doc = new DOMParser().parseFromString(
        '<svg xmlns="http://www.w3.org/2000/svg">' + markup + "</svg>",
        "image/svg+xml"
      );
    } catch (e) {
      return null;
    }
    if (doc.querySelector("parsererror")) return null;
    var root = doc.documentElement;
    var nodes = root.querySelectorAll("*");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (!SVG_ALLOWED_TAGS[el.tagName.toLowerCase()]) return null;
      for (var j = 0; j < el.attributes.length; j++) {
        var attr = el.attributes[j];
        var an = attr.name.toLowerCase();
        if (an === "fill" && attr.value === "currentColor") continue;
        if (!SVG_ALLOWED_ATTRS[an]) return null;
        if (!SVG_SAFE_ATTR_VALUE_RE.test(attr.value) && attr.value !== "currentColor") return null;
      }
    }
    return root.innerHTML;
  };

  /* ---- sanitize: mirrors blossom_theme_store.sanitize_theme ---- */

  var sanitize = function (raw) {
    var src = raw && typeof raw === "object" ? raw : {};
    var out = { schema: SCHEMA_VERSION, name: cleanName(src.name) };

    var base = String(src.base || "").trim().toLowerCase();
    out.base = BASE_THEMES.indexOf(base) >= 0 ? base : "dark";

    var colorsSrc = src.colors && typeof src.colors === "object" ? src.colors : {};
    var colors = {};
    Object.keys(COLOR_VARS).forEach(function (key) {
      var c = cleanColor(colorsSrc[key]);
      if (c) colors[key] = c;
    });
    out.colors = colors;

    var fontSrc = src.font && typeof src.font === "object" ? src.font : {};
    var font = {};
    var family = String(fontSrc.family || "").trim();
    if (family && FONT_RE.test(family)) font.family = family;
    var size = clampNum(fontSrc.size, 10, 18, 0);
    if (size) font.size = Math.round(size * 10) / 10;
    out.font = font;

    var radiusSrc = src.radius && typeof src.radius === "object" ? src.radius : {};
    var radius = {};
    RADIUS_KEYS.forEach(function (key) {
      if (radiusSrc[key] != null) radius[key] = Math.round(clampNum(radiusSrc[key], 0, 32, 0));
    });
    out.radius = radius;

    var bgSrc = src.background && typeof src.background === "object" ? src.background : {};
    var bgType = String(bgSrc.type || "none").trim().toLowerCase();
    var background = { type: BACKGROUND_TYPES.indexOf(bgType) >= 0 ? bgType : "none" };
    if (background.type === "gradient") {
      background.angle = Math.round(clampNum(bgSrc.angle, 0, 360, 135));
      var gradColors = [];
      (Array.isArray(bgSrc.colors) ? bgSrc.colors.slice(0, 4) : []).forEach(function (c) {
        var cc = cleanColor(c);
        if (cc) gradColors.push(cc);
      });
      if (gradColors.length >= 2) background.colors = gradColors;
      else background = { type: "none" };
    } else if (background.type === "image") {
      var image = String(bgSrc.image || "");
      if (image.length <= 2621440 && IMAGE_DATA_URI_RE.test(image)) {
        background.image = image;
        var fit = String(bgSrc.imageFit || "cover").trim().toLowerCase();
        background.imageFit = IMAGE_FITS.indexOf(fit) >= 0 ? fit : "cover";
        background.overlay = Math.round(clampNum(bgSrc.overlay, 0, 0.92, 0.55) * 100) / 100;
      } else {
        background = { type: "none" };
      }
    }
    out.background = background;

    var iconsSrc = src.icons && typeof src.icons === "object" ? src.icons : {};
    var icons = {};
    var iconColor = cleanColor(iconsSrc.color);
    if (iconColor) icons.color = iconColor;
    var stroke = clampNum(iconsSrc.strokeWidth, 1, 3, 0);
    if (stroke) icons.strokeWidth = Math.round(stroke * 100) / 100;
    if (iconsSrc.overrides && typeof iconsSrc.overrides === "object") {
      var overrides = {};
      var names = Object.keys(iconsSrc.overrides).slice(0, 80);
      names.forEach(function (rawName) {
        var key = String(rawName).toLowerCase().replace(/[^a-z0-9_-]/g, "").slice(0, 40);
        if (!key) return;
        var clean = sanitizeIconSvg(iconsSrc.overrides[rawName]);
        if (clean) overrides[key] = clean;
      });
      if (Object.keys(overrides).length) icons.overrides = overrides;
    }
    out.icons = icons;

    var layoutSrc = src.layout && typeof src.layout === "object" ? src.layout : {};
    var layout = {};
    var sidebarWidth = clampNum(layoutSrc.sidebarWidth, 148, 280, 0);
    if (sidebarWidth) layout.sidebarWidth = Math.round(sidebarWidth);
    var contentPadding = clampNum(layoutSrc.contentPadding, 8, 28, 0);
    if (contentPadding) layout.contentPadding = Math.round(contentPadding);
    out.layout = layout;

    var tabsSrc = src.tabs && typeof src.tabs === "object" ? src.tabs : {};
    var tabStyle = String(tabsSrc.style || "default").trim().toLowerCase();
    out.tabs = { style: TAB_STYLES.indexOf(tabStyle) >= 0 ? tabStyle : "default" };

    var buttonsSrc = src.buttons && typeof src.buttons === "object" ? src.buttons : {};
    var btnStyle = String(buttonsSrc.style || "default").trim().toLowerCase();
    out.buttons = { style: BUTTON_STYLES.indexOf(btnStyle) >= 0 ? btnStyle : "default" };

    var extraSrc = src.extra && typeof src.extra === "object" ? src.extra : {};
    var extraCss = sanitizeExtraCss(extraSrc.css);
    out.extra = extraCss ? { css: extraCss } : {};

    return out;
  };

  /* ---- color math for derived accent tokens ---- */

  var hexToRgb = function (hex) {
    var m = /^#?([0-9a-f]{6})$/i.exec(String(hex || "").trim());
    if (!m) return null;
    var n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  };
  var clampByte = function (n) { return Math.max(0, Math.min(255, Math.round(n))); };
  var toHex = function (rgb) {
    return "#" + rgb.map(function (c) { return clampByte(c).toString(16).padStart(2, "0"); }).join("");
  };
  var rgbaStr = function (rgb, a) {
    return "rgba(" + clampByte(rgb[0]) + ", " + clampByte(rgb[1]) + ", " + clampByte(rgb[2]) + ", " + a + ")";
  };
  var withAlpha = function (color, alpha) {
    var rgb = hexToRgb(color);
    return rgb ? rgbaStr(rgb, alpha) : color;
  };
  var luminance = function (rgb) {
    return (0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]) / 255;
  };

  var deriveMissingColors = function (colors) {
    var c = Object.assign({}, colors || {});
    var tint = function (hex, amt) {
      var rgb = hexToRgb(hex);
      if (!rgb) return null;
      return toHex(luminance(rgb) > 0.6 ? rgb.map(function (v) { return v * (1 - amt); }) : rgb.map(function (v) { return v + (255 - v) * amt; }));
    };
    if (c.bgCard && !c.bgCardHover) {
      var h = tint(c.bgCard, 0.06);
      if (h) c.bgCardHover = h;
    }
    if (c.bgInput && !c.bgInputFocus) {
      var f = tint(c.bgInput, 0.06);
      if (f) c.bgInputFocus = f;
    }
    if (c.border && !c.borderHover) {
      var b = tint(c.border, 0.1);
      if (b) c.borderHover = b;
    }
    if (c.success && !c.successDim) {
      var s = tint(c.success, 0.16);
      if (s) c.successDim = s;
    }
    if (c.danger && !c.dangerDim) {
      var d = tint(c.danger, 0.16);
      if (d) c.dangerDim = d;
    }
    return c;
  };

  var surfaceLuminance = function (colors) {
    var keys = ["bgRoot", "bgMain", "bgCard", "bgSidebar"];
    var total = 0;
    var count = 0;
    keys.forEach(function (key) {
      var rgb = colors[key] ? hexToRgb(colors[key]) : null;
      if (rgb) {
        total += luminance(rgb);
        count += 1;
      }
    });
    return count ? total / count : 0;
  };

  var deriveReadableText = function (colors, base) {
    var c = Object.assign({}, colors || {});
    var lightBase = !!LIGHT_BASES[base];
    var lightSurface = lightBase || surfaceLuminance(c) > 0.58;
    if (!lightSurface) return c;

    var darkPrimary = "#18181b";
    var darkSecondary = "#52525b";
    var darkMuted = "#71717a";

    var needsDarkText = function (key) {
      if (!c[key]) return true;
      var rgb = hexToRgb(c[key]);
      return !rgb || luminance(rgb) > 0.72;
    };

    if (needsDarkText("textPrimary")) c.textPrimary = darkPrimary;
    if (needsDarkText("textSecondary")) c.textSecondary = darkSecondary;
    if (needsDarkText("textMuted")) c.textMuted = darkMuted;

    if (c.accent) {
      var accentRgb = hexToRgb(c.accent);
      if (accentRgb && !c.accentDim) {
        c.accentDim = toHex(accentRgb.map(function (v) { return v * 0.82; }));
      }
      if (!c.accentText || needsDarkText("accentText")) {
        c.accentText = c.accentDim || c.accent;
      }
    }
    return c;
  };

  /* ---- compile sanitized theme -> CSS text ----
   * Applied as `body.blsm-json-theme[data-theme=<base>]` so any token the
   * theme doesn't define falls back to the base built-in theme. */

  var compile = function (theme) {
    var t = sanitize(theme);
    t.colors = deriveMissingColors(t.colors);
    t.colors = deriveReadableText(t.colors, t.base);
    var sel = "body.blsm-json-theme[data-theme]";
    var decls = [];

    Object.keys(t.colors).forEach(function (key) {
      decls.push(COLOR_VARS[key] + ": " + t.colors[key] + ";");
    });
    decls.push("--text-on-accent: #ffffff;");

    // Derived accent tokens (only when accent is a plain hex we can math on).
    var accentRgb = t.colors.accent ? hexToRgb(t.colors.accent) : null;
    if (accentRgb) {
      if (!t.colors.accentDim) {
        decls.push("--accent-dim: " + toHex(accentRgb.map(function (c) { return c * 0.82; })) + ";");
      }
      if (!t.colors.accentText) {
        var lightUi = !!LIGHT_BASES[t.base] || surfaceLuminance(t.colors) > 0.58;
        decls.push(
          "--accent-text: " +
            (lightUi
              ? (t.colors.accentDim || toHex(accentRgb.map(function (c) { return c * 0.82; })))
              : luminance(accentRgb) > 0.62
                ? "#1a1218"
                : toHex(accentRgb.map(function (c) { return c + (255 - c) * 0.55; }))) +
            ";"
        );
      }
      decls.push("--accent-glow: " + rgbaStr(accentRgb, 0.15) + ";");
      decls.push("--border-accent: " + rgbaStr(accentRgb, 0.3) + ";");
      decls.push("--shadow-glow: 0 0 20px " + rgbaStr(accentRgb, 0.08) + ";");
    }

    RADIUS_KEYS.forEach(function (key) {
      if (t.radius[key] != null) decls.push("--radius-" + key + ": " + t.radius[key] + "px;");
    });

    if (t.font.family) {
      decls.push(
        "font-family: " + t.font.family + ', "Google Sans Flex", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;'
      );
    }
    if (t.font.size) decls.push("font-size: " + t.font.size + "px;");
    if (t.colors.textPrimary) decls.push("color: " + t.colors.textPrimary + ";");
    if (t.colors.bgRoot) decls.push("background: " + t.colors.bgRoot + ";");
    if (t.layout.sidebarWidth) decls.push("--blsm-sidebar-width: " + t.layout.sidebarWidth + "px;");
    if (t.layout.contentPadding) decls.push("--blsm-content-padding: " + t.layout.contentPadding + "px;");

    var css = sel + " {\n  " + decls.join("\n  ") + "\n}\n";
    if (t.layout.contentPadding) {
      css += "body.blsm-json-theme .window-frame .page-content { padding: " + t.layout.contentPadding + "px !important; }\n";
    }
    if (t.font.family) {
      css += sel + " * { font-family: inherit; }\n";
    }

    // Background layer: painted on the window frame; key surfaces go
    // translucent so the gradient/image shows through.
    if (t.background.type !== "none") {
      var bgValue = "";
      if (t.background.type === "gradient") {
        bgValue = "linear-gradient(" + t.background.angle + "deg, " + t.background.colors.join(", ") + ")";
      } else {
        var overlay = t.background.overlay;
        var fit = t.background.imageFit;
        var sizing =
          fit === "cover" ? "center / cover no-repeat" :
          fit === "contain" ? "center / contain no-repeat" :
          fit === "tile" ? "left top repeat" : "center no-repeat";
        bgValue =
          "linear-gradient(rgba(0, 0, 0, " + overlay + "), rgba(0, 0, 0, " + overlay + ")), " +
          'url("' + t.background.image + '") ' + sizing;
      }
      css += "body.blsm-json-theme .window-frame { background: " + bgValue + "; }\n";
      var glass = [];
      if (t.colors.bgMain) glass.push("--bg-main: " + withAlpha(t.colors.bgMain, 0.72) + ";");
      if (t.colors.bgSidebar) glass.push("--bg-sidebar: " + withAlpha(t.colors.bgSidebar, 0.8) + ";");
      if (t.colors.bgCard) glass.push("--bg-card: " + withAlpha(t.colors.bgCard, 0.82) + ";");
      if (t.colors.bgRoot) glass.push("--bg-root: " + withAlpha(t.colors.bgRoot, 0) + ";");
      if (glass.length) css += sel + " {\n  " + glass.join("\n  ") + "\n}\n";
      css += "body.blsm-json-theme, body.blsm-json-theme #root { background: transparent; }\n";
    }

    if (t.extra && t.extra.css) css += "\n/* theme extra */\n" + t.extra.css + "\n";

    return { css: css, theme: t };
  };

  var applyBodyClasses = function (theme) {
    var body = document.body;
    if (!body) return;
    var tab = theme && theme.tabs ? theme.tabs.style : "default";
    var btn = theme && theme.buttons ? theme.buttons.style : "default";
    body.classList.toggle("blsm-tabs-underline", tab === "underline");
    body.classList.toggle("blsm-tabs-pill", tab === "pill");
    body.classList.toggle("blsm-btns-pill", btn === "pill");
    body.classList.toggle("blsm-btns-square", btn === "square");
  };

  var clearBodyClasses = function () {
    var body = document.body;
    if (!body) return;
    body.classList.remove("blsm-tabs-underline", "blsm-tabs-pill", "blsm-btns-pill", "blsm-btns-square");
  };

  /* ---- export / import helpers ---- */

  var exportText = function (theme) {
    return JSON.stringify(sanitize(theme), null, 2);
  };

  var parseImport = function (text) {
    var raw;
    try {
      raw = JSON.parse(String(text || ""));
    } catch (e) {
      return { ok: false, error: "Not valid JSON." };
    }
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
      return { ok: false, error: "Theme must be a JSON object." };
    }
    return { ok: true, theme: sanitize(raw) };
  };

  window.BlossomThemeEngine = {
    SCHEMA_VERSION: SCHEMA_VERSION,
    BASE_THEMES: BASE_THEMES,
    COLOR_VARS: COLOR_VARS,
    sanitize: sanitize,
    sanitizeIconSvg: sanitizeIconSvg,
    compile: compile,
    applyBodyClasses: applyBodyClasses,
    clearBodyClasses: clearBodyClasses,
    sanitizeExtraCss: sanitizeExtraCss,
    exportText: exportText,
    parseImport: parseImport,
    isColor: isColor,
  };
})();
