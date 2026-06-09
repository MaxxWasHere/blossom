(function () {
  const PANEL_ID = "blossom-biome-selector-panel";
  const { observeMain } = window.Blossom || {};

  const api = () => window.pywebview?.api;

  const configOn = (value) => {
    if (typeof value === "string") {
      return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    }
    return Boolean(value);
  };

  const isAutomatedActionsPage = () => {
    const header = document.querySelector(".page-header h2");
    return header && header.textContent.trim() === "Automated Actions";
  };

  const findItemUsageCard = () => {
    for (const card of document.querySelectorAll(".card")) {
      const title = card.querySelector("h3");
      if (title && title.textContent.trim() === "Item Usage") return card;
    }
    return null;
  };

  const persist = async (patch) => {
    const bridge = api();
    if (!bridge?.get_config || !bridge?.save_config) return;
    const cur = await bridge.get_config();
    await bridge.save_config({ ...cur, ...patch });
  };

  const saveDrives = async (drives) => {
    const bridge = api();
    if (bridge?.save_biome_selector_drives) {
      await bridge.save_biome_selector_drives(drives);
      return;
    }
    await persist({ biome_selector_drives: drives });
  };

  const renderDriveGrid = (panel, drives) => {
    const grid = panel.querySelector(".blsm-bs-drive-grid");
    if (!grid) return;
    grid.innerHTML = "";
    const names = Object.keys(drives).sort();
    for (const name of names) {
      const label = document.createElement("label");
      label.className = "blsm-bs-drive-row";
      label.innerHTML = `
        <input type="checkbox" ${drives[name] ? "checked" : ""} />
        <span>${name}</span>
      `;
      label.querySelector("input").addEventListener("change", async (e) => {
        drives[name] = !!e.target.checked;
        await saveDrives(drives);
        updateReadyBadge(panel);
      });
      grid.appendChild(label);
    }
  };

  const updateReadyBadge = async (panel) => {
    const badge = panel.querySelector(".blsm-bs-ready-badge");
    const bridge = api();
    if (!badge || !bridge?.get_biome_selector_status) return;
    try {
      const st = await bridge.get_biome_selector_status();
      const ok = st.inventory_ready && st.ui_ready && st.ocr_ready;
      badge.textContent = ok ? "Ready" : "Needs calibration / OCR";
      badge.style.color = ok ? "#86efac" : "#fbbf24";
    } catch {
      badge.textContent = "";
    }
  };

  const mountPanel = async (anchorCard) => {
    if (!anchorCard || document.getElementById(PANEL_ID)) return;

    const bridge = api();
    let config = {};
    let status = {};
    if (bridge?.get_config) {
      try {
        config = await bridge.get_config();
      } catch {}
    }
    if (bridge?.get_biome_selector_status) {
      try {
        status = await bridge.get_biome_selector_status();
      } catch {}
    }

    const enabled = configOn(config.biome_selector);
    const interval = Number(config.biome_selector_duration) || 30;
    const drives = status.drives || config.biome_selector_drives || {};

    const panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.className = "card";
    panel.style.marginTop = "16px";
    panel.style.position = "relative";
    panel.innerHTML = `
      <div class="card-header">
        <div class="card-icon">🧭</div>
        <div>
          <h3>Biome Selector <span style="color:#ff6b6b;font-weight:700;">(Broken / W.I.P.)</span></h3>
          <p>Use item → OCR drive list → click enabled rows → Confirm</p>
        </div>
      </div>
      <div style="padding:16px 20px 20px;display:flex;flex-direction:column;gap:14px;">
        <div style="border:1px solid rgba(255,107,107,0.45);background:rgba(255,107,107,0.12);border-radius:8px;padding:10px 12px;font-size:13px;line-height:1.4;">
          <strong style="color:#ff6b6b;">Broken / Work in progress.</strong>
          This automation is unfinished and unreliable right now. Leave it off — it may misclick or fail until it is fixed.
        </div>
        <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;opacity:0.6;">
          <label style="display:flex;align-items:center;gap:10px;cursor:not-allowed;" title="Biome Selector is broken / W.I.P. and temporarily disabled.">
            <input type="checkbox" class="blsm-bs-enable" ${enabled ? "checked" : ""} disabled />
            <span style="font-weight:600;">Enable automation (disabled — W.I.P.)</span>
          </label>
          <span class="form-hint blsm-bs-ready-badge" style="margin:0;font-weight:600;">…</span>
        </div>
        <label style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
          <span style="min-width:160px;">Interval (minutes)</span>
          <input type="number" min="1" step="1" class="form-input blsm-bs-interval" value="${interval}" style="max-width:110px;" />
        </label>
        <p class="form-hint" style="margin:0;">
          OCR always runs on each drive row. Only drives toggled <strong>On</strong> below are clicked, then <strong>Confirm</strong> is pressed for each match.
        </p>
        <div class="blsm-bs-drive-grid" style="display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;"></div>
        <div style="display:flex;gap:10px;flex-wrap:wrap;">
          <button type="button" class="btn btn-accent blsm-bs-run-once">Run once now</button>
          <button type="button" class="btn btn-secondary blsm-bs-open-cal">Calibrations</button>
          <button type="button" class="btn btn-secondary blsm-bs-all-on">All on</button>
          <button type="button" class="btn btn-secondary blsm-bs-all-off">All off</button>
        </div>
        <p class="form-hint blsm-bs-status" style="margin:0;min-height:1.2em;"></p>
      </div>
    `;

    anchorCard.insertAdjacentElement("afterend", panel);

    renderDriveGrid(panel, drives);
    updateReadyBadge(panel);

    panel.querySelector(".blsm-bs-enable").addEventListener("change", (e) => {
      persist({ biome_selector: !!e.target.checked });
    });
    panel.querySelector(".blsm-bs-interval").addEventListener("change", (e) => {
      const v = Math.max(1, Math.round(Number(e.target.value) || 30));
      e.target.value = v;
      persist({ biome_selector_duration: v });
    });
    panel.querySelector(".blsm-bs-open-cal").addEventListener("click", () => {
      window.Blossom?.goToTab?.("Calibrations");
    });
    panel.querySelector(".blsm-bs-all-on").addEventListener("click", async () => {
      const next = { ...drives };
      for (const k of Object.keys(next)) next[k] = true;
      renderDriveGrid(panel, next);
      await saveDrives(next);
      updateReadyBadge(panel);
    });
    panel.querySelector(".blsm-bs-all-off").addEventListener("click", async () => {
      const next = { ...drives };
      for (const k of Object.keys(next)) next[k] = false;
      renderDriveGrid(panel, next);
      await saveDrives(next);
      updateReadyBadge(panel);
    });
    panel.querySelector(".blsm-bs-run-once").addEventListener("click", async () => {
      const statusEl = panel.querySelector(".blsm-bs-status");
      statusEl.textContent = "Running…";
      try {
        const res = await bridge?.run_biome_selector_now?.();
        statusEl.textContent = res?.status || res?.error || "Done";
      } catch (error) {
        statusEl.textContent = String(error);
      }
      updateReadyBadge(panel);
    });
  };

  const sync = async () => {
    if (!isAutomatedActionsPage()) {
      document.getElementById(PANEL_ID)?.remove();
      return;
    }
    const card = findItemUsageCard();
    if (card) await mountPanel(card);
  };

  if (observeMain) observeMain(() => sync(), 0, "Automated Actions");
  else {
    sync();
    window.addEventListener("pywebviewready", sync);
  }
})();
