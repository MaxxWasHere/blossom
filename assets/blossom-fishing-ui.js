(function () {
  const HUB_ID = "blsm-fishing-collection-hub";
  const PAGE = "Fishing";

  const { observeMain, pageHeaderTitle } = window.Blossom || {};
  const api = () => window.pywebview?.api;

  const isFishingPage = () => pageHeaderTitle?.() === PAGE;

  const mainEl = () =>
    document.querySelector(".page-content") || document.querySelector(".main-content");

  const clampInt = (value, fallback, min, max) => {
    const n = Math.floor(Number(value));
    if (!Number.isFinite(n)) return fallback;
    return Math.min(max, Math.max(min, n));
  };

  const saveSettings = async (patch) => {
    const bridge = api();
    if (!bridge?.get_config || !bridge?.save_config) return;
    try {
      const config = await bridge.get_config();
      await bridge.save_config({ ...config, ...patch });
    } catch (error) {
      console.warn("[fishing-ui] could not save collections click settings:", error);
    }
  };

  const ensureHub = () => {
    const main = mainEl();
    if (!main || document.getElementById(HUB_ID)) return document.getElementById(HUB_ID);

    const header = main.querySelector(".page-header");
    const hub = document.createElement("section");
    hub.id = HUB_ID;
    hub.innerHTML = `
      <div class="blsm-fishing-collection-toggle">
        <input type="checkbox" id="blsm-fishing-slow-collections-cb" />
        <label for="blsm-fishing-slow-collections-cb">
          <b>Slower Collections clicks</b>
          <span>Opens and closes the Collections menu with a longer settle and click hold, plus extra wait for the menu to appear. Helpful on slower PCs where the menu does not open in time.</span>
        </label>
      </div>
      <div class="blsm-fishing-collection-delay" data-blsm-slow-row hidden>
        <label for="blsm-fishing-slow-collections-delay">Extra delay (ms)</label>
        <input
          type="number"
          id="blsm-fishing-slow-collections-delay"
          min="0"
          max="5000"
          step="50"
          value="400"
        />
        <span class="blsm-fishing-collection-delay-hint">Added settle + hold per collections click and to the menu-open wait. 0 keeps the default timing.</span>
      </div>
    `;

    const toggle = hub.querySelector("#blsm-fishing-slow-collections-cb");
    const delayRow = hub.querySelector("[data-blsm-slow-row]");
    const delayInput = hub.querySelector("#blsm-fishing-slow-collections-delay");

    const syncDelayRow = () => {
      if (!delayRow) return;
      delayRow.hidden = !toggle.checked;
    };

    toggle?.addEventListener("change", () => {
      syncDelayRow();
      void saveSettings({
        fishing_slow_collections_clicks: Boolean(toggle.checked),
        fishing_collections_click_delay_ms: clampInt(delayInput?.value, 400, 0, 5000),
      });
    });

    delayInput?.addEventListener("change", () => {
      const clamped = clampInt(delayInput.value, 400, 0, 5000);
      delayInput.value = String(clamped);
      void saveSettings({ fishing_collections_click_delay_ms: clamped });
    });

    const anchor = header?.nextElementSibling || main.firstChild;
    if (anchor) {
      main.insertBefore(hub, anchor);
    } else {
      main.appendChild(hub);
    }

    void (async () => {
      const bridge = api();
      if (!bridge?.get_config || !toggle) return;
      try {
        const config = await bridge.get_config();
        toggle.checked = Boolean(config.fishing_slow_collections_clicks);
        if (delayInput) {
          delayInput.value = String(
            clampInt(config.fishing_collections_click_delay_ms, 400, 0, 5000)
          );
        }
      } catch {
        toggle.checked = false;
      }
      syncDelayRow();
    })();

    return hub;
  };

  const teardown = () => {
    if (isFishingPage()) return;
    document.getElementById(HUB_ID)?.remove();
    document.documentElement.classList.remove("blsm-fishing-hub-active");
  };

  const refresh = () => {
    if (!isFishingPage()) {
      teardown();
      return;
    }
    document.documentElement.classList.add("blsm-fishing-hub-active");
    ensureHub();
  };

  if (observeMain) {
    observeMain(refresh, 120, [PAGE]);
  } else {
    window.addEventListener("pywebviewready", refresh);
    refresh();
  }
})();
