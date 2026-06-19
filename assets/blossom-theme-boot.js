/*
 * Early appearance boot — runs before first paint in index.html and bootstrap-splash.
 * Pairs with blossom-appearance.js (full settings UI + config reconcile).
 */
(function () {
  "use strict";

  const LS = "blossom-appearance";
  const ACC = [
    "--accent",
    "--accent-dim",
    "--accent-text",
    "--accent-glow",
    "--border-accent",
    "--shadow-glow",
  ];
  const ZOOM = { compact: "0.9", normal: "", large: "1.1", xlarge: "1.2" };
  const LEGACY = { blush: "pink", solar: "pink", ocean: "dark", arctic: "light" };
  const VALID = ["system", "pink", "dark", "light", "oled", "sakura", "midnight", "forest"];
  const LIGHT = { light: 1, sakura: 1 };

  const isLightTheme = (key) => {
    if (LIGHT[key]) return true;
    if (key === "system") {
      try {
        return window.matchMedia("(prefers-color-scheme: light)").matches;
      } catch {
        return false;
      }
    }
    return false;
  };

  const readLocal = () => {
    try {
      return JSON.parse(localStorage.getItem(LS) || "{}") || {};
    } catch {
      return {};
    }
  };

  const normTheme = (v) => {
    const k = String(v || "system").toLowerCase();
    if (VALID.indexOf(k) >= 0) return k;
    return LEGACY[k] || "system";
  };

  const hex = (v) => {
    const m = /^#?([0-9a-f]{6})$/i.exec(String(v || "").trim());
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  };

  const applyState = (s) => {
    const state = s && typeof s === "object" ? s : {};
    const root = document.documentElement;
    root.classList.toggle("blsm-reduce-motion", !!state.motion);
    const body = document.body;
    if (!body) return;
    const hasCustomCss = !!(state.customCss || state.customCssText);
    const themeKey = hasCustomCss ? "custom" : normTheme(state.theme);
    body.setAttribute("data-theme", themeKey);
    body.classList.remove("blsm-json-theme");
    document.getElementById("blsm-json-theme-style")?.remove();
    root.classList.toggle("blsm-custom-ui-active", hasCustomCss);
    root.classList.toggle("blsm-light-ui", isLightTheme(themeKey));
    ACC.forEach((p) => {
      body.style.removeProperty(p);
      root.style.removeProperty(p);
    });
    if (!hasCustomCss && state.accent && state.accent !== "default") {
      const rgb = hex(state.accent);
      if (rgb) {
        const h = (c) => ("0" + Math.max(0, Math.min(255, Math.round(c))).toString(16)).slice(-2);
        const to = "#" + h(rgb[0]) + h(rgb[1]) + h(rgb[2]);
        const dk = (c) => c * 0.82;
        const lt = (c) => c + (255 - c) * 0.55;
        body.style.setProperty("--accent", to);
        body.style.setProperty("--accent-dim", "#" + h(dk(rgb[0])) + h(dk(rgb[1])) + h(dk(rgb[2])));
        body.style.setProperty(
          "--accent-text",
          isLightTheme(normTheme(state.theme))
            ? "#" + h(dk(rgb[0])) + h(dk(rgb[1])) + h(dk(rgb[2]))
            : "#" + h(lt(rgb[0])) + h(lt(rgb[1])) + h(lt(rgb[2]))
        );
        body.style.setProperty("--text-on-accent", "#ffffff");
        body.style.setProperty("--accent-glow", "rgba(" + rgb[0] + "," + rgb[1] + "," + rgb[2] + ",0.15)");
        body.style.setProperty("--border-accent", "rgba(" + rgb[0] + "," + rgb[1] + "," + rgb[2] + ",0.3)");
        body.style.setProperty("--shadow-glow", "0 0 20px rgba(" + rgb[0] + "," + rgb[1] + "," + rgb[2] + ",0.08)");
      }
    }
    const z = ZOOM[state.scale] || "";
    const frame = document.querySelector(".window-frame");
    if (frame) frame.style.zoom = z;
    if (state.customCssText) {
      let customEl = document.getElementById("blsm-custom-ui");
      if (!customEl) {
        customEl = document.createElement("style");
        customEl.id = "blsm-custom-ui";
        document.head.appendChild(customEl);
      }
      customEl.textContent = state.customCssText;
    } else {
      document.getElementById("blsm-custom-ui")?.remove();
    }
  };

  const applyFromLocal = () => applyState(readLocal());

  const applyFromConfig = (cfg) => {
    if (!cfg || typeof cfg !== "object") {
      applyFromLocal();
      return;
    }
    const s = { ...readLocal() };
    if (typeof cfg.ui_theme === "string" && cfg.ui_theme) s.theme = normTheme(cfg.ui_theme);
    else if (typeof cfg.selected_theme === "string" && cfg.selected_theme) s.theme = normTheme(cfg.selected_theme);
    if (typeof cfg.ui_accent === "string" && cfg.ui_accent) s.accent = cfg.ui_accent;
    if (typeof cfg.ui_reduce_motion === "boolean") s.motion = cfg.ui_reduce_motion;
    const customKey = cfg.ui_custom_css ?? cfg.ui_custom_theme;
    if (typeof customKey === "string") s.customCss = customKey;
    applyState(s);
  };

  window.BlossomThemeBoot = {
    apply: applyFromLocal,
    applyFromLocal,
    applyFromConfig,
    readLocal,
  };

  applyFromLocal();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", applyFromLocal);
  }
})();
