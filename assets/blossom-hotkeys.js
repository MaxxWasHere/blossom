(function () {
  const HOTKEY_ID = "blossom-macro-hotkeys";
  const HOTKEY_PAGES = new Set(["Macro Calibrations", "Settings & extras"]);
  const CLEAR_KEYS = new Set(["Delete", "Backspace"]);

  const KEY_ALIASES = {
    arrowup: "up",
    arrowdown: "down",
    arrowleft: "left",
    arrowright: "right",
    " ": "space",
    spacebar: "space",
    escape: "esc",
    return: "enter",
    del: "delete",
    pageup: "page up",
    pagedown: "page down",
    meta: "windows",
    os: "windows",
    control: "ctrl",
    command: "windows",
  };

  const CODE_ALIASES = {
    Space: "space",
    Escape: "esc",
    Enter: "enter",
    Tab: "tab",
    Backspace: "delete",
    Delete: "delete",
    PageUp: "page up",
    PageDown: "page down",
    ArrowUp: "up",
    ArrowDown: "down",
    ArrowLeft: "left",
    ArrowRight: "right",
  };

  const api = () => window.pywebview?.api;

  let mountedPage = "";
  let view = {
    start: "",
    stop: "",
    start_display: "No bind",
    stop_display: "No bind",
    default_start_display: "F1",
    default_stop_display: "F2",
  };
  let listeningSlot = null;
  let keyHandler = null;
  let capturePaused = false;

  const canonicalKeyPart = (part) => {
    const token = String(part || "").trim().toLowerCase();
    return KEY_ALIASES[token] || token;
  };

  const keyFromCode = (code) => {
    if (!code) return "";
    if (CODE_ALIASES[code]) return CODE_ALIASES[code];
    if (/^Key[A-Z]$/.test(code)) return code.slice(3).toLowerCase();
    if (/^Digit[0-9]$/.test(code)) return code.slice(5);
    if (/^F([1-9]|1[0-2])$/.test(code)) return code.toLowerCase();
    if (/^Numpad[0-9]$/.test(code)) return `num ${code.slice(6)}`;
    return "";
  };

  const formatHotkeyEvent = (event) => {
    if (!event) return "";
    let raw = event.key && event.key.length === 1 ? event.key.toLowerCase() : event.key || "";
    if (["Control", "Shift", "Alt", "Meta"].includes(raw)) return "";
    if (!raw || raw === "Unidentified") {
      raw = keyFromCode(event.code);
    }
    if (!raw) return "";
    const parts = [];
    if (event.ctrlKey) parts.push("ctrl");
    if (event.altKey) parts.push("alt");
    if (event.shiftKey) parts.push("shift");
    if (event.metaKey) parts.push("windows");
    parts.push(canonicalKeyPart(raw));
    return parts.join("+");
  };

  const displayHotkey = (key, display) => {
    if (display) return display;
    if (!key) return "No bind";
    return String(key)
      .split("+")
      .map((p) => p.charAt(0).toUpperCase() + p.slice(1))
      .join(" + ");
  };

  const pageTitle = () =>
    window.Blossom?.pageHeaderTitle?.() ||
    document.querySelector(".page-header h2")?.textContent?.trim() ||
    "";

  const findInsertTarget = (title) => {
    const headers = Array.from(document.querySelectorAll(".page-header"));
    const header = headers.find((h) => h.querySelector("h2")?.textContent?.trim() === title);
    if (!header?.parentElement) return null;
    const parent = header.parentElement;
    const firstCard = Array.from(parent.children).find(
      (n) => n.classList?.contains("card") && n.id !== HOTKEY_ID
    );
    if (title === "Settings & extras") {
      const shortcuts = document.getElementById("blossom-settings-extras");
      return { parent, before: shortcuts || firstCard, compact: false };
    }
    return { parent, before: firstCard, compact: true };
  };

  const panel = () => document.getElementById(HOTKEY_ID);

  const setStatus = (text) => {
    const el = panel()?.querySelector(".blossom-hotkey-status");
    if (el) el.textContent = text || "";
  };

  const applyView = (hotkeys) => {
    view = { ...view, ...hotkeys };
    view.start = view.start || "";
    view.stop = view.stop || "";
  };

  const paintPanel = () => {
    const root = panel();
    if (!root) return;
    root.querySelectorAll(".blossom-hotkey-slot").forEach((btn) => {
      const slot = btn.getAttribute("data-slot");
      const label = btn.querySelector(".blossom-hotkey-label");
      if (!slot || !label) return;
      label.textContent = displayHotkey(view[slot], view[`${slot}_display`]);
      btn.classList.toggle("btn-accent", listeningSlot === slot);
    });
    const resetBtn = root.querySelector(".blossom-hotkey-reset");
    if (resetBtn) {
      const ds = view.default_start_display || "F1";
      const dst = view.default_stop_display || "F2";
      resetBtn.textContent = `Reset to defaults (${ds} / ${dst})`;
    }
  };

  const pauseGlobalHotkeys = async () => {
    const bridge = api();
    if (!bridge?.pause_macro_hotkeys) return false;
    try {
      await bridge.pause_macro_hotkeys();
      capturePaused = true;
      return true;
    } catch (error) {
      console.warn("[blossom-hotkeys] pause failed", error);
      return false;
    }
  };

  const resumeGlobalHotkeys = async () => {
    const bridge = api();
    if (!bridge?.resume_macro_hotkeys) return false;
    try {
      await bridge.resume_macro_hotkeys();
      capturePaused = false;
      return true;
    } catch (error) {
      console.warn("[blossom-hotkeys] resume failed", error);
      return false;
    }
  };

  const endListening = () => {
    if (keyHandler) {
      window.removeEventListener("keydown", keyHandler, true);
      keyHandler = null;
    }
    listeningSlot = null;
    paintPanel();
  };

  const stopListening = async (resumeGlobal = true) => {
    endListening();
    if (resumeGlobal && capturePaused) {
      await resumeGlobalHotkeys();
    } else if (!resumeGlobal) {
      capturePaused = false;
    }
  };

  const commitBinds = async () => {
    const bridge = api();
    if (!bridge?.set_macro_hotkeys) return null;
    return bridge.set_macro_hotkeys({
      rewrite: true,
      start_key: view.start || "none",
      stop_key: view.stop || "none",
    });
  };

  const applyServerBinds = (result) => {
    if (!result?.ok) {
      setStatus(result?.error || "Could not save hotkeys");
      return false;
    }
    applyView(result);
    paintPanel();
    window.BlossomMacroLabels?.refresh?.();
    return true;
  };

  const saveBinds = async (message) => {
    try {
      const result = await commitBinds();
      if (!result) {
        setStatus("Hotkey API not available — restart the app");
        return;
      }
      if (applyServerBinds(result) && message) setStatus(message);
    } catch (error) {
      setStatus(String(error));
    }
  };

  const beginListening = async (slot) => {
    await stopListening(true);
    listeningSlot = slot;
    await pauseGlobalHotkeys();
    paintPanel();
    setStatus(
      `Listening for ${slot === "start" ? "Start" : "Stop"} — press a key, Delete to clear, Esc to cancel`
    );

    keyHandler = async (event) => {
      if (event.key === "Escape") {
        setStatus("Cancelled");
        await stopListening(true);
        return;
      }
      if (CLEAR_KEYS.has(event.key)) {
        event.preventDefault();
        event.stopPropagation();
        view[slot] = "";
        view[`${slot}_display`] = "No bind";
        endListening();
        const ok = await saveBinds(`${slot === "start" ? "Start" : "Stop"}: No bind`);
        if (!ok) await resumeGlobalHotkeys();
        return;
      }
      const captured = formatHotkeyEvent(event);
      if (!captured) return;
      event.preventDefault();
      event.stopPropagation();
      view[slot] = captured;
      view[`${slot}_display`] = displayHotkey(captured);
      const label = displayHotkey(captured);
      endListening();
      const ok = await saveBinds(`${slot === "start" ? "Start" : "Stop"}: ${label}`);
      if (!ok) await resumeGlobalHotkeys();
    };

    window.addEventListener("keydown", keyHandler, true);
  };

  const resetDefaults = async () => {
    await stopListening();
    setStatus("Resetting…");
    try {
      const bridge = api();
      if (!bridge?.set_macro_hotkeys) return;
      const result = await bridge.set_macro_hotkeys({ reset: true });
      if (applyServerBinds(result)) {
        setStatus("Restored default Start / Stop hotkeys");
      }
    } catch (error) {
      setStatus(String(error));
    }
  };

  const onPanelClick = (event) => {
    const root = panel();
    if (!root || !root.contains(event.target)) return;

    if (event.target.closest(".blossom-hotkey-reset")) {
      event.preventDefault();
      resetDefaults();
      return;
    }

    const slotBtn = event.target.closest(".blossom-hotkey-slot");
    if (slotBtn) {
      event.preventDefault();
      const slot = slotBtn.getAttribute("data-slot");
      if (slot === "start" || slot === "stop") beginListening(slot);
    }
  };

  const panelMarkup = (compact, hotkeys) => {
    const ds = hotkeys.default_start_display || "F1";
    const dst = hotkeys.default_stop_display || "F2";
    const slots = `
      <div class="blossom-hotkey-bind-row" style="display:flex;flex-wrap:wrap;gap:10px;align-items:center;">
        <button type="button" class="btn btn-secondary blossom-hotkey-slot" data-slot="start">
          Start: <span class="blossom-hotkey-label">No bind</span>
        </button>
        <button type="button" class="btn btn-secondary blossom-hotkey-slot" data-slot="stop">
          Stop: <span class="blossom-hotkey-label">No bind</span>
        </button>
        <button type="button" class="btn blossom-hotkey-reset" style="margin-left:auto;">
          Reset to defaults (${ds} / ${dst})
        </button>
      </div>`;

    if (compact) {
      return `
        <div style="padding:12px 16px;">
          <div style="font-weight:700;color:var(--accent-text);margin-bottom:4px;">Start / Stop hotkeys</div>
          <div class="form-hint" style="margin:0 0 10px;">Global keys for the macro. Click a slot to change it.</div>
          ${slots}
          <div class="form-hint blossom-hotkey-status" style="margin-top:10px;min-height:1.2em;"></div>
        </div>`;
    }

    return `
      <div class="card-header">
        <div class="card-icon">⌨</div>
        <div><h3>Start / Stop hotkeys</h3><p>Global keys to start and stop the macro</p></div>
      </div>
      <div style="padding:16px 20px 20px;">
        <div class="form-hint" style="margin-bottom:10px;">Click Start or Stop, press a key, Delete to clear, Esc to cancel.</div>
        ${slots}
        <div class="form-hint blossom-hotkey-status" style="margin-top:10px;min-height:1.2em;"></div>
      </div>`;
  };

  const ensurePanel = (insert, hotkeys) => {
    let root = panel();
    const compact = insert.compact;
    const needsRebuild =
      !root ||
      !root.isConnected ||
      root.getAttribute("data-compact") !== String(compact);

    if (needsRebuild) {
      if (root) root.remove();
      root = document.createElement("div");
      root.id = HOTKEY_ID;
      root.setAttribute("data-blossom-managed", "hotkeys");
      root.setAttribute("data-compact", String(compact));
      root.className = "card";
      root.style.marginBottom = compact ? "12px" : "16px";
      root.style.position = "relative";
      root.innerHTML = panelMarkup(compact, hotkeys);
      root.addEventListener("click", onPanelClick);
      const { parent, before } = insert;
      if (before) parent.insertBefore(root, before);
      else parent.appendChild(root);
    }

    if (!listeningSlot) {
      applyView(hotkeys);
      paintPanel();
    }
  };

  const removeMacroHotkeys = () => {
    void stopListening(true);
    panel()?.remove();
    mountedPage = "";
  };

  const fetchHotkeys = async () => {
    const defaults = {
      start: "",
      stop: "",
      start_display: "No bind",
      stop_display: "No bind",
      default_start_display: "F1",
      default_stop_display: "F2",
    };
    const bridge = api();
    if (!bridge?.get_macro_hotkeys) return defaults;
    try {
      return { ...defaults, ...(await bridge.get_macro_hotkeys()) };
    } catch {
      return defaults;
    }
  };

  const syncHotkeys = async () => {
    const title = pageTitle();

    if (!HOTKEY_PAGES.has(title)) {
      if (mountedPage) removeMacroHotkeys();
      return;
    }

    const insert = findInsertTarget(title);
    if (!insert?.parent) return;

    const hotkeys = await fetchHotkeys();
    ensurePanel(insert, hotkeys);
    mountedPage = title;
    if (!listeningSlot) {
      window.BlossomMacroLabels?.refresh?.();
    }
  };

  const boot = () => {
    const run = () => syncHotkeys();
    if (window.Blossom?.observeMain) {
      window.Blossom.observeMain(run, 0, [...HOTKEY_PAGES]);
    } else {
      run();
      window.addEventListener("pywebviewready", run);
    }
  };

  window.BlossomHotkeys = {
    HOTKEY_ID,
    HOTKEY_PAGES,
    removeMacroHotkeys,
    syncHotkeys,
    displayHotkey,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
