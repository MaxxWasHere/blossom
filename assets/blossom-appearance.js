(function () {
  const { observeMain, pageHeaderTitle } = window.Blossom || {};
  const CARD_ID = "blossom-appearance-card";
  const LS_KEY = "blossom-appearance";
  const MIGRATION_LS_KEY = "blossom-appearance-json-migrated";
  const CUSTOM_STYLE_ID = "blsm-custom-ui";
  const APPEARANCE_PAGE = "Appearance";
  const THEMES_FOLDER_HINT = "%LOCALAPPDATA%\\Blossom\\themes\\";

  const ACCENT_PRESETS = [
    { color: "#e891a8", label: "Rose" },
    { color: "#a78bfa", label: "Violet" },
    { color: "#38bdf8", label: "Ocean" },
    { color: "#34d399", label: "Emerald" },
    { color: "#fbbf24", label: "Amber" },
    { color: "#f87171", label: "Crimson" },
  ];

  const SCALES = [
    { key: "compact", zoom: 0.9, label: "Compact" },
    { key: "normal", zoom: 1, label: "Normal" },
    { key: "large", zoom: 1.1, label: "Large" },
    { key: "xlarge", zoom: 1.2, label: "X-Large" },
  ];

  const WINDOW_PRESETS = [
    { key: "small", label: "Small", width: 860, height: 540 },
    { key: "medium", label: "Medium", width: 980, height: 640 },
    { key: "large", label: "Large", width: 1200, height: 760 },
    { key: "custom", label: "Custom" },
  ];

  const THEMES = [
    { key: "system", label: "Match system", hint: "Follows Windows light/dark", swatch: "linear-gradient(135deg,#18181b 50%,#fafafa 50%)" },
    { key: "pink", label: "Pink", hint: "Rose accent, dark base", swatch: "#e891a8" },
    { key: "dark", label: "Dark", hint: "Neutral dark palette", swatch: "#3f3f46" },
    { key: "light", label: "Light", hint: "Bright surfaces", swatch: "#fafafa" },
    { key: "oled", label: "OLED", hint: "True black for AMOLED panels", swatch: "linear-gradient(135deg,#000 60%,#f2a3b9 60%)" },
    { key: "sakura", label: "Sakura", hint: "Warm petal pinks, light base", swatch: "linear-gradient(135deg,#f9eef3 50%,#d4537e 50%)" },
    { key: "midnight", label: "Midnight", hint: "Deep navy, indigo accent", swatch: "linear-gradient(135deg,#070b14 55%,#818cf8 55%)" },
    { key: "forest", label: "Forest", hint: "Mossy greens, emerald accent", swatch: "linear-gradient(135deg,#0a0f0b 55%,#5fd49a 55%)" },
  ];

  const VALID_THEMES = new Set(THEMES.map((t) => t.key));
  const LIGHT_THEMES = new Set(["light", "sakura"]);

  const isLightVisualTheme = (themeKey) => {
    const key = String(themeKey || "").toLowerCase();
    if (LIGHT_THEMES.has(key)) return true;
    if (key === "system") {
      try {
        return window.matchMedia("(prefers-color-scheme: light)").matches;
      } catch {
        return false;
      }
    }
    return false;
  };

  const syncLightUiClass = (s) => {
    const key = visualThemeKey(s || state);
    document.documentElement.classList.toggle("blsm-light-ui", isLightVisualTheme(key));
  };

  const LEGACY_THEME_MAP = {
    blush: "pink",
    solar: "pink",
    lavender: "pink",
    sunset: "pink",
    cyberpunk: "pink",
    ocean: "dark",
    neon: "dark",
    arctic: "light",
  };

  const ACCENT_PROPS = [
    "--accent",
    "--accent-dim",
    "--accent-text",
    "--accent-glow",
    "--border-accent",
    "--shadow-glow",
  ];

  const DEFAULTS = {
    theme: "system",
    accent: "default",
    customCss: "",
    customCssText: "",
    scale: "normal",
    motion: false,
    windowPreset: "medium",
    windowWidth: 980,
    windowHeight: 640,
  };

  const api = () => window.pywebview?.api;
  const accentEl = () => document.body || document.documentElement;
  const scaleEl = () =>
    document.querySelector(".window-frame") || document.body || document.documentElement;
  const motionEl = () => document.documentElement;

  const HEX_RE = /^#?([0-9a-f]{6})$/i;
  const hexToRgb = (hex) => {
    const m = HEX_RE.exec(String(hex || "").trim());
    if (!m) return null;
    const n = parseInt(m[1], 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  };
  const clamp = (n) => Math.max(0, Math.min(255, Math.round(n)));
  const toHex = (rgb) =>
    "#" + rgb.map((c) => clamp(c).toString(16).padStart(2, "0")).join("");
  const normHex = (hex) => {
    const rgb = hexToRgb(hex);
    return rgb ? toHex(rgb) : null;
  };
  const darken = (rgb, amt) => rgb.map((c) => c * (1 - amt));
  const lighten = (rgb, amt) => rgb.map((c) => c + (255 - c) * amt);
  const rgba = (rgb, a) => `rgba(${clamp(rgb[0])}, ${clamp(rgb[1])}, ${clamp(rgb[2])}, ${a})`;
  const escAttr = (s) =>
    String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  const normalizeThemeKey = (raw) => {
    const key = String(raw || "").trim().toLowerCase();
    if (VALID_THEMES.has(key)) return key;
    if (LEGACY_THEME_MAP[key]) return LEGACY_THEME_MAP[key];
    return DEFAULTS.theme;
  };

  function PathBasename(name) {
    const parts = String(name).replace(/\\/g, "/").split("/");
    return parts[parts.length - 1] || "";
  }

  const normalizeCustomCss = (raw) => {
    const name = PathBasename(String(raw || "").trim());
    return name && name.toLowerCase().endsWith(".css") && !name.toLowerCase().endsWith(".example.css")
      ? name
      : "";
  };

  const clearAccentInline = (el) => {
    if (!el) return;
    ACCENT_PROPS.forEach((p) => el.style.removeProperty(p));
  };

  const applyAccent = (value) => {
    const body = accentEl();
    const root = document.documentElement;
    clearAccentInline(body);
    clearAccentInline(root);
    if (!value || value === "default") return;
    const rgb = hexToRgb(value);
    if (!rgb) return;
    const dim = toHex(darken(rgb, 0.18));
    body.style.setProperty("--accent", toHex(rgb));
    body.style.setProperty("--accent-dim", dim);
    body.style.setProperty(
      "--accent-text",
      isLightVisualTheme(visualThemeKey(state)) ? dim : toHex(lighten(rgb, 0.55))
    );
    body.style.setProperty("--text-on-accent", "#ffffff");
    body.style.setProperty("--accent-glow", rgba(rgb, 0.15));
    body.style.setProperty("--border-accent", rgba(rgb, 0.3));
    body.style.setProperty("--shadow-glow", `0 0 20px ${rgba(rgb, 0.08)}`);
  };

  const applyTheme = (themeKey) => {
    const key = normalizeThemeKey(themeKey);
    const body = document.body;
    if (!body) return key;
    body.setAttribute("data-theme", key);
    return key;
  };

  const hasCustomUi = (s) => !!normalizeCustomCss(s?.customCss);

  const visualThemeKey = (s) => (hasCustomUi(s) ? "custom" : normalizeThemeKey(s.theme));

  const applyVisualTheme = (s) => {
    const body = document.body;
    if (!body) return;
    body.setAttribute("data-theme", visualThemeKey(s));
    body.classList.remove("blsm-json-theme");
    document.documentElement.classList.toggle("blsm-custom-ui-active", hasCustomUi(s));
    syncLightUiClass(s);
  };

  const injectStyleText = (id, css) => {
    let el = document.getElementById(id);
    if (!css) {
      el?.remove();
      return;
    }
    if (!el) {
      el = document.createElement("style");
      el.id = id;
      document.head.appendChild(el);
    }
    el.textContent = css;
  };

  const injectCustomCssText = (css) => injectStyleText(CUSTOM_STYLE_ID, css);

  const applyCustomCss = async (filename, { cachedText } = {}) => {
    const fname = normalizeCustomCss(filename);
    if (!fname) {
      injectCustomCssText("");
      state.customCssText = "";
      applyVisualTheme(state);
      return true;
    }

    state.customCss = fname;

    const bridge = api();
    if (bridge?.read_custom_ui_css) {
      try {
        const res = await bridge.read_custom_ui_css(fname);
        if (res?.ok && res.css) {
          injectCustomCssText(res.css);
          state.customCssText = res.css;
          applyVisualTheme(state);
          cacheAppearanceState();
          return true;
        }
        if (res && !res.ok) {
          applyVisualTheme(state);
          return false;
        }
      } catch (err) {
        console.warn("[appearance] custom UI load failed");
      }
    }

    const fallback = cachedText || state.customCssText;
    if (fallback) {
      injectCustomCssText(fallback);
      applyVisualTheme(state);
      cacheAppearanceState();
      return true;
    }

    applyVisualTheme(state);
    return false;
  };

  const applyScale = (key) => {
    const spec = SCALES.find((s) => s.key === key) || SCALES.find((s) => s.key === "normal");
    const zoom = spec.zoom === 1 ? "" : String(spec.zoom);
    const el = scaleEl();
    el.style.zoom = zoom;
    if (el !== document.documentElement) document.documentElement.style.zoom = "";
  };

  const applyMotion = (on) => {
    motionEl().classList.toggle("blsm-reduce-motion", !!on);
  };

  const applyAll = async (s) => {
    if (hasCustomUi(s)) {
      clearAccentInline(accentEl());
      clearAccentInline(document.documentElement);
    }

    await applyCustomCss(s.customCss, { cachedText: s.customCssText });

    if (!hasCustomUi(state)) {
      applyVisualTheme(state);
      applyAccent(state.accent);
    } else {
      applyVisualTheme(state);
    }
    applyScale(s.scale);
    applyMotion(s.motion);
    cacheAppearanceState();
  };

  const stripLegacyJsonThemeFields = (raw) => {
    const out = { ...raw };
    const hadJson =
      !!normalizeCustomTheme(out.customTheme) ||
      !!out.customThemeCss ||
      !!out.customThemeBase;
    delete out.customTheme;
    delete out.customThemeBase;
    delete out.customThemeCss;
    delete out.customThemeIcons;
    delete out.themeFile;
    delete out.showCorners;
    if (hadJson) {
      try {
        if (!localStorage.getItem(MIGRATION_LS_KEY)) {
          out._jsonMigrationNotice = true;
          localStorage.setItem(MIGRATION_LS_KEY, "1");
        }
      } catch {}
    }
    return out;
  };

  const normalizeCustomTheme = (raw) => {
    const name = PathBasename(String(raw || "").trim());
    return name && name.toLowerCase().endsWith(".json") && !name.toLowerCase().endsWith(".example.json")
      ? name
      : "";
  };

  const readLocal = () => {
    try {
      const raw = stripLegacyJsonThemeFields({
        ...DEFAULTS,
        ...(JSON.parse(localStorage.getItem(LS_KEY)) || {}),
      });
      raw.theme = normalizeThemeKey(raw.theme);
      raw.customCss = normalizeCustomCss(raw.customCss);
      return raw;
    } catch {
      return { ...DEFAULTS };
    }
  };

  const writeLocal = (s) => {
    try {
      const payload = { ...s };
      delete payload._jsonMigrationNotice;
      delete payload._needsJsonConfigClear;
      localStorage.setItem(LS_KEY, JSON.stringify(payload));
    } catch {}
  };

  const cacheAppearanceState = () => {
    writeLocal(state);
  };

  let state = readLocal();
  let systemMq = null;
  let customCatalog = [];
  let needsJsonConfigClear = false;

  const normalizeFromConfig = (cfg) => {
    if (!cfg || typeof cfg !== "object") return null;
    const out = { ...DEFAULTS };
    let found = false;

    if (typeof cfg.ui_theme === "string" && cfg.ui_theme) {
      out.theme = normalizeThemeKey(cfg.ui_theme);
      found = true;
    } else if (typeof cfg.selected_theme === "string" && cfg.selected_theme) {
      out.theme = normalizeThemeKey(cfg.selected_theme);
      found = true;
    }

    const customKey = cfg.ui_custom_css ?? cfg.ui_custom_theme;
    if (typeof customKey === "string") {
      out.customCss = normalizeCustomCss(customKey);
      found = true;
    }

    if (typeof cfg.ui_custom_theme_json === "string" && cfg.ui_custom_theme_json) {
      needsJsonConfigClear = true;
      try {
        if (!localStorage.getItem(MIGRATION_LS_KEY)) {
          out._jsonMigrationNotice = true;
          localStorage.setItem(MIGRATION_LS_KEY, "1");
        }
      } catch {}
    }

    if (typeof cfg.ui_accent === "string" && cfg.ui_accent) {
      out.accent = cfg.ui_accent;
      found = true;
    }
    if (typeof cfg.ui_scale === "string" && SCALES.some((s) => s.key === cfg.ui_scale)) {
      out.scale = cfg.ui_scale;
      found = true;
    }
    if (typeof cfg.ui_reduce_motion === "boolean") {
      out.motion = cfg.ui_reduce_motion;
      found = true;
    }
    const w = cfg.ui_window_width;
    const h = cfg.ui_window_height;
    if (w != null && h != null) {
      out.windowWidth = Number(w) || DEFAULTS.windowWidth;
      out.windowHeight = Number(h) || DEFAULTS.windowHeight;
      out.windowPreset = "custom";
      for (const p of WINDOW_PRESETS) {
        if (p.width === out.windowWidth && p.height === out.windowHeight) {
          out.windowPreset = p.key;
          break;
        }
      }
      found = true;
    }
    return found ? out : null;
  };

  const buildAppearancePatch = () => {
    const patch = {
      ui_theme: state.theme,
      selected_theme: state.theme,
      ui_custom_css: state.customCss || "",
      ui_accent: state.accent,
      ui_scale: state.scale,
      ui_reduce_motion: state.motion,
      ui_window_width: state.windowWidth,
      ui_window_height: state.windowHeight,
    };
    if (needsJsonConfigClear) {
      patch.ui_custom_theme_json = "";
      needsJsonConfigClear = false;
    }
    return patch;
  };

  let persistInFlight = null;
  let persistTimer = null;

  const persistNow = async () => {
    const bridge = api();
    if (!bridge) return false;
    const patch = buildAppearancePatch();
    try {
      if (typeof bridge.save_appearance_settings === "function") {
        await bridge.save_appearance_settings(patch);
        return true;
      }
      if (typeof bridge.get_config === "function" && typeof bridge.save_config === "function") {
        const cfg = (await bridge.get_config()) || {};
        Object.assign(cfg, patch);
        await bridge.save_config(cfg);
        return true;
      }
    } catch (err) {
      console.warn("[appearance] save failed", err);
    }
    return false;
  };

  const runPersist = () => {
    persistTimer = null;
    persistInFlight = persistNow().finally(() => {
      persistInFlight = null;
    });
    return persistInFlight;
  };

  const persist = async ({ immediate = false, feedback = false } = {}) => {
    const doSave = () => {
      if (persistInFlight) return persistInFlight;
      return runPersist();
    };

    if (immediate) {
      clearTimeout(persistTimer);
      persistTimer = null;
      if (feedback) showCardSaveFeedback("saving");
      const ok = await doSave();
      if (feedback) showCardSaveFeedback(ok ? "saved" : "error");
      return ok;
    }

    clearTimeout(persistTimer);
    if (feedback) showCardSaveFeedback("saving");
    persistTimer = setTimeout(async () => {
      const ok = await doSave();
      if (feedback) showCardSaveFeedback(ok ? "saved" : "error");
    }, 280);
    return true;
  };

  const flushPersist = () => {
    clearTimeout(persistTimer);
    persistTimer = null;
    if (persistInFlight) return persistInFlight;
    return runPersist();
  };

  let cardSaveFeedbackTimer = null;

  const showCardSaveFeedback = (phase) => {
    const el = document.getElementById(CARD_ID)?.querySelector(".blsm-appearance-save-status");
    if (!el) return;
    clearTimeout(cardSaveFeedbackTimer);
    el.classList.remove("is-saving", "is-saved", "is-error");
    if (!phase) {
      el.hidden = true;
      el.querySelector(".blsm-save-status-text").textContent = "";
      return;
    }
    el.hidden = false;
    const text = el.querySelector(".blsm-save-status-text");
    if (phase === "saving") {
      el.classList.add("is-saving");
      if (text) text.textContent = "Saving…";
      return;
    }
    if (phase === "saved") {
      el.classList.add("is-saved");
      if (text) text.textContent = "Saved";
      cardSaveFeedbackTimer = setTimeout(() => showCardSaveFeedback(null), 1600);
      return;
    }
    if (phase === "error") {
      el.classList.add("is-error");
      if (text) text.textContent = "Could not save";
      cardSaveFeedbackTimer = setTimeout(() => showCardSaveFeedback(null), 2600);
    }
  };

  const accentMatches = (a, b) => {
    if (a === b) return true;
    if (a === "default" || b === "default") return false;
    const na = normHex(a);
    const nb = normHex(b);
    return !!(na && nb && na === nb);
  };

  const update = (patch, { save = true, feedback = true } = {}) => {
    if (patch.theme != null) patch.theme = normalizeThemeKey(patch.theme);
    if (patch.customCss != null) patch.customCss = normalizeCustomCss(patch.customCss);
    if (hasCustomUi({ ...state, ...patch }) && patch.accent != null) {
      return;
    }
    state = { ...state, ...patch };
    void applyAll(state).then(async () => {
      writeLocal(state);
      if (save) await persist({ immediate: true, feedback });
      refreshCardFields();
    });
  };

  const applyWindowSize = async (width, height, { save = true } = {}) => {
    const bridge = api();
    if (!bridge?.set_window_size) return;
    try {
      const res = await bridge.set_window_size(Number(width), Number(height), save);
      if (res?.ok) {
        state.windowWidth = res.width;
        state.windowHeight = res.height;
        refreshCardFields();
      }
    } catch (err) {
      console.warn("[appearance] window resize failed", err);
    }
  };

  let reconciled = false;

  const reloadFromConfig = async () => {
    const bridge = api();
    if (!bridge?.get_config) return;
    try {
      await loadCustomCatalog();
      const cfg = await bridge.get_config();
      const fromCfg = normalizeFromConfig(cfg);
      if (fromCfg) {
        state = { ...state, ...fromCfg };
        await applyAll(state);
        writeLocal(state);
        refreshCardFields();
      }
    } catch {}
  };

  const reconcile = async () => {
    if (reconciled) return;
    const bridge = api();
    if (!bridge?.get_config) return;
    reconciled = true;
    try {
      await loadCustomCatalog();
      const cfg = await bridge.get_config();
      const fromCfg = normalizeFromConfig(cfg);
      if (fromCfg) {
        state = { ...state, ...fromCfg };
        await applyAll(state);
        writeLocal(state);
        refreshCardFields();
      } else {
        void persist({ immediate: true });
      }
      const size = bridge.get_window_size ? await bridge.get_window_size() : null;
      if (size?.width && size?.height) {
        state.windowWidth = size.width;
        state.windowHeight = size.height;
        refreshCardFields();
      }
    } catch {
      reconciled = false;
    }
  };

  const loadCustomCatalog = async () => {
    const bridge = api();
    if (!bridge?.list_custom_ui_themes) return;
    try {
      const res = await bridge.list_custom_ui_themes();
      customCatalog = Array.isArray(res?.themes) ? res.themes : [];
      refreshCustomSelect();
    } catch {}
  };

  let themeObserver = null;
  const watchThemeChanges = () => {
    if (themeObserver || !document.body) return;
    themeObserver = new MutationObserver(() => {
      const want = visualThemeKey(state);
      const cur = document.body.getAttribute("data-theme");
      if (cur !== want) applyVisualTheme(state);
      if (!hasCustomUi(state)) applyAccent(state.accent);
    });
    themeObserver.observe(document.body, { attributes: true, attributeFilter: ["data-theme"] });
  };

  const watchSystemScheme = () => {
    if (systemMq || !window.matchMedia) return;
    systemMq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => {
      if (!hasCustomUi(state) && state.theme === "system") applyVisualTheme(state);
    };
    try {
      systemMq.addEventListener("change", onChange);
    } catch {
      systemMq.addListener(onChange);
    }
  };

  const hideLegacyToolbarTheme = () => {
    document.querySelectorAll("span").forEach((span) => {
      if (span.textContent?.trim() !== "Macro Theme:") return;
      span.style.display = "none";
      const sel = span.nextElementSibling;
      if (sel?.tagName === "SELECT") sel.style.display = "none";
    });
  };

  const refreshCustomSelect = () => {
    const card = document.getElementById(CARD_ID);
    const sel = card?.querySelector(".blsm-custom-ui-select");
    if (!sel) return;
    const cur = state.customCss || "";
    const opts = [
      `<option value="">None — use built-in theme below</option>`,
      ...customCatalog.map(
        (t) =>
          `<option value="${escAttr(t.filename)}"${t.filename === cur ? " selected" : ""}>${escAttr(t.label || t.filename)}</option>`
      ),
    ];
    sel.innerHTML = opts.join("");
    const status = card.querySelector(".blsm-custom-ui-status");
    if (!status) return;
    if (state._jsonMigrationNotice) {
      status.textContent =
        "JSON themes were retired — pick a built-in theme or create a custom-ui.css file. Your old .json files are still in the themes folder.";
      status.hidden = false;
      state._jsonMigrationNotice = false;
      writeLocal(state);
      return;
    }
    if (cur && !customCatalog.some((t) => t.filename === cur)) {
      status.textContent = `"${cur}" is missing or blocked. Using your saved built-in theme.`;
      status.hidden = false;
    } else {
      status.hidden = true;
      status.textContent = "";
    }
  };

  const refreshCardFields = () => {
    const card = document.getElementById(CARD_ID);
    if (!card) return;

    card.querySelectorAll(".blsm-theme-card").forEach((btn) => {
      btn.classList.toggle("is-selected", btn.dataset.theme === state.theme);
    });
    card.querySelectorAll(".blsm-accent-swatch").forEach((btn) => {
      btn.classList.toggle("is-selected", accentMatches(btn.dataset.accent, state.accent));
    });
    card.querySelectorAll('[data-field="scale"]').forEach((btn) => {
      btn.classList.toggle("is-selected", btn.dataset.scale === state.scale);
    });
    card.querySelectorAll('[data-field="window"]').forEach((btn) => {
      btn.classList.toggle("is-selected", btn.dataset.window === state.windowPreset);
    });

    const motion = card.querySelector(".blsm-appearance-motion");
    if (motion) motion.checked = !!state.motion;

    const custom = card.querySelector(".blsm-accent-custom");
    if (custom) {
      const nh = normHex(state.accent);
      if (nh) custom.value = nh;
    }

    const wIn = card.querySelector(".blsm-window-width");
    const hIn = card.querySelector(".blsm-window-height");
    if (wIn) wIn.value = String(state.windowWidth || DEFAULTS.windowWidth);
    if (hIn) hIn.value = String(state.windowHeight || DEFAULTS.windowHeight);

    const customRow = card.querySelector(".blsm-window-custom-row");
    if (customRow) customRow.hidden = state.windowPreset !== "custom";

    refreshCustomSelect();
    document.documentElement.classList.toggle("blsm-custom-ui-active", hasCustomUi(state));
  };

  const refreshWindowFields = () => {
    const bridge = api();
    if (!bridge?.get_window_size) return;
    void bridge.get_window_size().then((size) => {
      if (!size?.width || !size?.height) return;
      state.windowWidth = size.width;
      state.windowHeight = size.height;
      state.windowPreset = "custom";
      for (const p of WINDOW_PRESETS) {
        if (p.width === size.width && p.height === size.height) {
          state.windowPreset = p.key;
          break;
        }
      }
      writeLocal(state);
      refreshCardFields();
    });
  };

  const applyWindowPreset = async (key) => {
    const preset = WINDOW_PRESETS.find((p) => p.key === key);
    if (!preset) return;
    if (key === "custom") {
      state.windowPreset = "custom";
      refreshCardFields();
      return;
    }
    state.windowPreset = key;
    state.windowWidth = preset.width;
    state.windowHeight = preset.height;
    writeLocal(state);
    refreshCardFields();
    await applyWindowSize(preset.width, preset.height);
    void persist({ immediate: true, feedback: true });
  };

  const applyCustomWindowSize = async () => {
    const card = document.getElementById(CARD_ID);
    if (!card) return;
    const w = parseInt(card.querySelector(".blsm-window-width")?.value, 10);
    const h = parseInt(card.querySelector(".blsm-window-height")?.value, 10);
    if (!Number.isFinite(w) || !Number.isFinite(h)) return;
    state.windowPreset = "custom";
    state.windowWidth = w;
    state.windowHeight = h;
    writeLocal(state);
    refreshCardFields();
    await applyWindowSize(w, h);
    void persist({ immediate: true, feedback: true });
  };

  const wireCard = (card) => {
    card.querySelectorAll(".blsm-theme-card").forEach((btn) => {
      btn.addEventListener("click", () => update({ theme: btn.dataset.theme, customCss: "" }));
    });
    card.querySelectorAll(".blsm-accent-swatch").forEach((btn) => {
      btn.addEventListener("click", () => update({ accent: btn.dataset.accent }));
    });
    card.querySelectorAll('[data-field="scale"]').forEach((btn) => {
      btn.addEventListener("click", () => update({ scale: btn.dataset.scale }));
    });
    card.querySelectorAll('[data-field="window"]').forEach((btn) => {
      btn.addEventListener("click", () => void applyWindowPreset(btn.dataset.window));
    });

    const custom = card.querySelector(".blsm-accent-custom");
    custom.addEventListener("input", () => update({ accent: custom.value }, { save: false }));
    custom.addEventListener("change", () => update({ accent: custom.value }));

    card.querySelector(".blsm-appearance-motion").addEventListener("change", (e) => {
      update({ motion: !!e.target.checked });
    });

    card.querySelector(".blsm-custom-ui-select").addEventListener("change", (e) => {
      update({ customCss: e.target.value || "" });
    });

    card.querySelector(".blsm-custom-ui-refresh").addEventListener("click", () => {
      void loadCustomCatalog().then(async () => {
        if (state.customCss) {
          await applyCustomCss(state.customCss);
          await persist({ immediate: true, feedback: true });
        }
        refreshCardFields();
      });
    });

    card.querySelector(".blsm-custom-ui-folder").addEventListener("click", () => {
      void api()?.open_themes_folder?.();
    });

    card.querySelector(".blsm-window-apply").addEventListener("click", () => {
      void applyCustomWindowSize();
    });

    card.querySelectorAll(".blsm-window-dim").forEach((input) => {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") void applyCustomWindowSize();
      });
    });
  };

  const buildCard = () => {
    const themeCards = THEMES.map(
      (t) =>
        `<button type="button" class="blsm-theme-card" data-theme="${t.key}" title="${t.hint}">
          <span class="blsm-theme-swatch" style="background:${t.swatch};"></span>
          <span class="blsm-theme-label">${t.label}</span>
        </button>`
    ).join("");

    const swatches = ACCENT_PRESETS.map(
      (p) =>
        `<button type="button" class="blsm-accent-swatch" data-accent="${p.color}" title="${p.label}" aria-label="${p.label}" style="--blsm-swatch:${p.color};"></button>`
    ).join("");
    const scaleSeg = SCALES.map(
      (s) =>
        `<button type="button" class="blsm-seg-btn" data-field="scale" data-scale="${s.key}">${s.label}</button>`
    ).join("");
    const windowSeg = WINDOW_PRESETS.map(
      (p) =>
        `<button type="button" class="blsm-seg-btn" data-field="window" data-window="${p.key}">${p.label}</button>`
    ).join("");

    const card = document.createElement("div");
    card.id = CARD_ID;
    card.className = "card blsm-appearance-card";
    card.innerHTML = `
      <div class="card-header blsm-appearance-header">
        <div class="card-icon">🎨</div>
        <div>
          <h3>Appearance</h3>
          <p>Theme, custom UI, colors, layout, window, and motion</p>
        </div>
        <div class="blsm-appearance-save-status" hidden aria-live="polite">
          <span class="blsm-save-status-icon" aria-hidden="true"></span>
          <span class="blsm-save-status-text"></span>
        </div>
      </div>
      <div class="blsm-appearance-body">
        <section class="blsm-app-section">
          <header class="blsm-app-section-head">
            <h4>Custom UI</h4>
            <p>Full visual reskin — not just colors. One CSS file can reshape every surface the app already renders (sidebar, tabs, cards, modals, loading screen). Stored in <code class="blsm-app-code">${THEMES_FOLDER_HINT}</code>.</p>
          </header>
          <div class="blsm-custom-ui-row">
            <label class="blsm-app-field blsm-custom-ui-field">
              <span class="blsm-app-label">Custom stylesheet</span>
              <select class="form-input blsm-custom-ui-select"></select>
            </label>
            <button type="button" class="btn btn-secondary blsm-custom-ui-refresh" title="Rescan themes folder and re-apply">Refresh</button>
            <button type="button" class="btn btn-secondary blsm-custom-ui-folder" title="Open the themes folder in Explorer">Open folder</button>
          </div>
          <p class="blsm-app-hint">Copy <code class="blsm-app-code">custom-ui.example.css</code> as a starter — it lists every major selector. Built-in themes only swap palette tokens; Custom UI can hide, reorder (flex/grid), round corners, change fonts, and reskin the whole shell. You cannot add tabs, remove features, or replace HTML — that needs a Blossom build. CSS only; unsafe rules are blocked. Refresh after edits — no restart.</p>
          <p class="blsm-app-hint blsm-custom-ui-status" hidden role="status"></p>
        </section>

        <section class="blsm-app-section">
          <header class="blsm-app-section-head">
            <h4>Built-in theme</h4>
            <p class="blsm-theme-fallback-note">Not applied while Custom UI is active — your saved choice is kept as fallback.</p>
            <p>Eight looks, from true-black OLED to light Sakura — or Match system to follow Windows light/dark.</p>
          </header>
          <div class="blsm-theme-grid">${themeCards}</div>
        </section>

        <section class="blsm-app-section blsm-accent-section">
          <header class="blsm-app-section-head">
            <h4>Colors</h4>
            <p>Optional accent override when using a built-in theme (disabled for custom UI).</p>
          </header>
          <div class="blsm-accent-row">
            <button type="button" class="blsm-accent-swatch blsm-accent-default" data-accent="default" title="Theme default" aria-label="Theme default"></button>
            ${swatches}
            <label class="blsm-accent-custom-wrap" title="Custom color">
              <input type="color" class="blsm-accent-custom" value="#e891a8" aria-label="Custom accent" />
            </label>
          </div>
        </section>

        <section class="blsm-app-section">
          <header class="blsm-app-section-head">
            <h4>Layout</h4>
            <p>Interface scale zooms content inside the window.</p>
          </header>
          <label class="blsm-app-field">
            <span class="blsm-app-label">Interface scale</span>
            <div class="blsm-seg">${scaleSeg}</div>
          </label>
        </section>

        <section class="blsm-app-section">
          <header class="blsm-app-section-head">
            <h4>Window</h4>
            <p>Native app window size. Drag edges to resize; size saves automatically.</p>
          </header>
          <label class="blsm-app-field">
            <span class="blsm-app-label">Window size preset</span>
            <div class="blsm-seg">${windowSeg}</div>
          </label>
          <div class="blsm-window-custom-row" hidden>
            <label class="blsm-app-field blsm-app-field-inline">
              <span class="blsm-app-label">Width</span>
              <input type="number" class="form-input blsm-window-dim blsm-window-width" min="860" max="2560" step="1" />
            </label>
            <label class="blsm-app-field blsm-app-field-inline">
              <span class="blsm-app-label">Height</span>
              <input type="number" class="form-input blsm-window-dim blsm-window-height" min="540" max="1600" step="1" />
            </label>
            <button type="button" class="btn btn-secondary blsm-window-apply">Apply size</button>
          </div>
        </section>

        <section class="blsm-app-section blsm-app-section-last">
          <header class="blsm-app-section-head">
            <h4>Motion</h4>
          </header>
          <label class="blsm-app-toggle">
            <input type="checkbox" class="blsm-appearance-motion" />
            <span>Reduce motion</span>
          </label>
          <p class="blsm-app-hint">Disables animations and transitions across the app.</p>
        </section>
      </div>
    `;
    wireCard(card);
    return card;
  };

  const findAppearanceParent = () => {
    const header = Array.from(document.querySelectorAll(".page-header")).find(
      (h) => h.querySelector("h2")?.textContent?.trim() === APPEARANCE_PAGE
    );
    return header?.parentElement || null;
  };

  const mountCard = () => {
    const existing = document.getElementById(CARD_ID);
    if (existing?.isConnected) {
      refreshCardFields();
      return;
    }
    if (existing) existing.remove();
    const parent = findAppearanceParent();
    if (!parent) return;
    const card = buildCard();
    const header = parent.querySelector(".page-header");
    if (header?.nextSibling) parent.insertBefore(card, header.nextSibling);
    else parent.appendChild(card);
    refreshCardFields();
  };

  const onAppearancePage = () =>
    (pageHeaderTitle ? pageHeaderTitle() : document.querySelector(".page-header h2")?.textContent?.trim()) ===
    APPEARANCE_PAGE;

  const bootApply = async () => {
    await applyAll(state);
    watchThemeChanges();
    watchSystemScheme();
    hideLegacyToolbarTheme();
  };

  const sync = () => {
    hideLegacyToolbarTheme();
    void reconcile();
    if (!onAppearancePage()) {
      document.getElementById(CARD_ID)?.remove();
      return;
    }
    mountCard();
  };

  const chainConfigUpdated = () => {
    const prev = window.onConfigUpdated;
    window.onConfigUpdated = () => {
      void reloadFromConfig();
      if (typeof prev === "function") prev();
    };
  };

  void bootApply();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => void bootApply());
  }

  window.BlossomAppearance = {
    apply: applyAll,
    getState: () => ({ ...state }),
    reloadFromConfig,
    refreshWindowFields,
    applyTheme,
  };

  if (observeMain) observeMain(sync, 0, APPEARANCE_PAGE);
  else window.addEventListener("pywebviewready", sync);

  window.addEventListener("pywebviewready", () => {
    void reconcile();
    chainConfigUpdated();
    void bootApply();
    sync();
  });
  void reconcile();

  window.addEventListener("pagehide", () => {
    writeLocal(state);
    void flushPersist();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") {
      writeLocal(state);
      void flushPersist();
    }
  });
})();
