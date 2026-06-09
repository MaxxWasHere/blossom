(function () {
  const { observeMain, pageHeaderTitle, goToTab } = window.Blossom || {};
  const PANEL_ID = "blossom-settings-extras";
  const WINDOW_PANEL_ID = "blossom-window-settings";

  const isSettingsPage = () => pageHeaderTitle() === "Settings & extras";

  const api = () => window.pywebview?.api;

  const configFlagOn = (value) => {
    if (typeof value === "string") {
      return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    }
    return Boolean(value);
  };

  const findInsertTarget = () => {
    const headers = Array.from(document.querySelectorAll(".page-header"));
    const header = headers.find(
      (h) => h.querySelector("h2")?.textContent?.trim() === "Settings & extras"
    );
    if (!header?.parentElement) return null;
    const parent = header.parentElement;
    const firstCard = Array.from(parent.children).find((n) => n.classList?.contains("card"));
    return { parent, before: firstCard };
  };

  const SHORTCUTS = [
    { label: "Appearance", tab: "Appearance", primary: true },
    { label: "Macro Calibrations", tab: "Calibrations" },
    { label: "Potion Crafting", tab: "Potion craft" },
    { label: "Auras", tab: "Auras" },
    { label: "Automated Actions", tab: "Automated" },
    { label: "Macro Status", tab: "Macro Status" },
    { label: "Movements", tab: "Movements" },
    { label: "Webhook", tab: "Webhook" },
  ];

  const mountShortcuts = (mountTarget) => {
    if (!mountTarget || document.getElementById(PANEL_ID)) return;

    const panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.className = "card";
    panel.style.marginBottom = "16px";
    panel.style.position = "relative";
    panel.innerHTML = `
      <div class="card-header">
        <div class="card-icon">⚡</div>
        <div><h3>Quick navigation</h3><p>Jump to common pages</p></div>
      </div>
      <div class="blossom-settings-shortcuts" style="padding:16px 20px 20px;display:flex;flex-wrap:wrap;gap:8px;"></div>
    `;
    const grid = panel.querySelector(".blossom-settings-shortcuts");
    for (const item of SHORTCUTS) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = item.primary ? "btn btn-accent" : "btn btn-secondary";
      btn.textContent = item.label;
      btn.addEventListener("click", () => goToTab?.(item.tab));
      grid.appendChild(btn);
    }
    const { parent, before } = mountTarget;
    if (before) parent.insertBefore(panel, before);
    else parent.appendChild(panel);
  };

  const mountWindowSettings = (mountTarget) => {
    if (!mountTarget) return;
    let panel = document.getElementById(WINDOW_PANEL_ID);
    if (panel) return;

    panel = document.createElement("div");
    panel.id = WINDOW_PANEL_ID;
    panel.className = "card";
    panel.style.marginBottom = "16px";
    panel.style.position = "relative";
    panel.innerHTML = `
      <div class="card-header">
        <div class="card-icon">🪟</div>
        <div><h3>Window</h3><p>Keep Blossom above other apps</p></div>
      </div>
      <div style="padding:16px 20px 20px;">
        <label class="blossom-aot-row" style="display:flex;align-items:center;gap:10px;cursor:pointer;">
          <input type="checkbox" class="blossom-aot-checkbox" />
          <span style="font-weight:600;">Always on top</span>
        </label>
        <p class="form-hint blossom-aot-hint" style="margin:10px 0 0;color:var(--text-muted);">
          Saved with your config. Uses a single native Windows setting (no header pin).
        </p>
        <p class="form-hint blossom-aot-status" style="margin:6px 0 0;min-height:1.2em;"></p>
      </div>
    `;

    const checkbox = panel.querySelector(".blossom-aot-checkbox");
    const status = panel.querySelector(".blossom-aot-status");
    let applying = false;
    let debounceTimer = null;

    const loadState = async () => {
      const bridge = api();
      if (!bridge) return;
      let enabled = false;
      try {
        if (typeof bridge.get_window_always_on_top === "function") {
          const res = await bridge.get_window_always_on_top();
          enabled = Boolean(res?.enabled);
        } else if (typeof bridge.get_config === "function") {
          const cfg = await bridge.get_config();
          enabled = configFlagOn(cfg?.always_on_top);
        }
      } catch {
        return;
      }
      checkbox.checked = enabled;
      status.textContent = enabled ? "On — window stays above others." : "Off";
    };

    const applyState = async (enabled) => {
      const bridge = api();
      if (!bridge?.set_window_always_on_top || applying) return;
      applying = true;
      status.textContent = "Applying…";
      try {
        const result = await bridge.set_window_always_on_top(!!enabled);
        if (result?.ok === false) {
          status.textContent = result.error || "Could not change always on top.";
          checkbox.checked = !enabled;
          return;
        }
        status.textContent = enabled
          ? "On — window stays above others."
          : "Off";
      } catch (error) {
        status.textContent = String(error);
        checkbox.checked = !enabled;
      } finally {
        applying = false;
      }
    };

    checkbox.addEventListener("change", () => {
      const next = checkbox.checked;
      clearTimeout(debounceTimer);
      debounceTimer = setTimeout(() => void applyState(next), 350);
    });

    panel._blossomLoadAot = loadState;

    const { parent, before } = mountTarget;
    const shortcuts = document.getElementById(PANEL_ID);
    const insertBefore = shortcuts?.nextSibling || before;
    if (insertBefore) parent.insertBefore(panel, insertBefore);
    else parent.appendChild(panel);

    void loadState();
  };

  const sync = () => {
    if (!isSettingsPage()) {
      document.getElementById(PANEL_ID)?.remove();
      document.getElementById(WINDOW_PANEL_ID)?.remove();
      return;
    }
    const target = findInsertTarget();
    if (!target) return;
    mountShortcuts(target);
    mountWindowSettings(target);
    document.getElementById(WINDOW_PANEL_ID)?._blossomLoadAot?.();
    window.BlossomHotkeys?.syncHotkeys?.();
  };

  if (observeMain) observeMain(() => sync(), 0, "Settings & extras");
  else {
    sync();
    window.addEventListener("pywebviewready", sync);
  }
})();
