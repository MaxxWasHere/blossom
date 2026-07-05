(function () {
  const PAGES = {
    AUTOMATED: "Automated Actions",
    FISHING: "Fishing",
    STATUS: "Macro Status",
  };

  const MACRO_PAGES = new Set(Object.values(PAGES));

  const HUB = {
    [PAGES.AUTOMATED]: "blsm-macro-hub-auto",
    [PAGES.FISHING]: "blsm-macro-hub-fishing",
    [PAGES.STATUS]: "blsm-macro-hub-status",
  };

  const GRID = {
    [PAGES.AUTOMATED]: "blsm-macro-grid-auto",
    [PAGES.FISHING]: "blsm-macro-grid-fishing",
    [PAGES.STATUS]: "blsm-macro-grid-status",
  };

  const { observeMain, pageHeaderTitle, goToTab } = window.Blossom || {};
  const I = (name) => window.BlossomIcons?.svg(name) || "";
  const api = () => window.pywebview?.api;

  const mainEl = () =>
    document.querySelector(".page-content") || document.querySelector(".main-content");

  const currentPage = () => pageHeaderTitle?.() || "";

  const isMacroPage = () => MACRO_PAGES.has(currentPage());

  const cardByTitle = (title) => {
    const cards = Array.from(mainEl()?.querySelectorAll(".card") || []);
    return (
      cards.find((card) => {
        const h3 = card.querySelector("h3");
        return h3 && h3.textContent.trim() === title;
      }) || null
    );
  };

  const hotkeyHintHtml = async () => {
    let start = "F1";
    let stop = "F2";
    if (api()?.get_macro_hotkeys) {
      try {
        const hk = await api().get_macro_hotkeys();
        const disp = (k, d) =>
          window.BlossomHotkeys?.displayHotkey?.(k, d) || d || k || "No bind";
        start = disp(hk.start, hk.start_display);
        stop = disp(hk.stop, hk.stop_display);
      } catch {}
    }
    return `<span class="blsm-macro-hotkey-hint">Start <kbd>${start}</kbd> · Stop <kbd>${stop}</kbd></span>`;
  };

  const flowHtml = (steps, states, dismissible) => {
    const dismissBtn = dismissible
      ? `<button type="button" class="blsm-macro-flow-dismiss" aria-label="Dismiss setup guide" title="Dismiss">×</button>`
      : "";
    return `<div class="blsm-macro-flow-wrap">${dismissBtn}<div class="blsm-macro-flow" role="list" aria-label="Macro setup flow">${steps
      .map((s, i) => {
        const st = states?.[i] || "is-pending";
        const mark = st === "is-done" ? " ✓" : "";
        return `
        <div class="blsm-macro-flow-step ${st}" data-step="${s.n}" role="listitem">
          <strong>${s.title}${mark}</strong>
          <span>${s.text}</span>
        </div>`;
      })
      .join("")}</div></div>`;
  };

  const FLOW_DISMISS_KEY = "macro_flow_dismissed";

  const configFlagOn = (value) => {
    if (typeof value === "string") {
      return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    }
    return Boolean(value);
  };

  const isCalValue = (v) =>
    Array.isArray(v) && v.length >= 2 && v.every((n) => typeof n === "number" && !Number.isNaN(n));

  const CAL_KEYS = [
    "reconnect_start",
    "merchant_npc_pos",
    "merchant_talk_pos",
    "fishing_cast_pos",
    "collections_menu_pos",
  ];

  const hasCalibration = (config) => CAL_KEYS.some((k) => isCalValue(config?.[k]));

  const anyModeEnabled = (config) =>
    [
      "merchant_teleporter",
      "fishing_mode",
      "enable_auto_obby",
      "auto_claim_daily_quests",
      "enable_potion_crafting",
    ].some((k) => configFlagOn(config?.[k]));

  const pageModeEnabled = (page, config) => {
    if (page === PAGES.FISHING) return configFlagOn(config?.fishing_mode);
    return anyModeEnabled(config);
  };

  const stepStatesFor = (page, calDone, modeDone, running) => {
    const pageSteps = hubContent[page]?.()?.steps || [];
    const n = pageSteps.length;
    const milestones = [];

    if (page === PAGES.STATUS) {
      milestones.push(calDone || modeDone, running, running);
    } else {
      milestones.push(calDone, modeDone, running);
    }

    let currentAssigned = false;
    return milestones.slice(0, n).map((done) => {
      if (done) return "is-done";
      if (!currentAssigned) {
        currentAssigned = true;
        return "is-current";
      }
      return "is-pending";
    });
  };

  const flowDismissed = (config, page) => {
    const raw = config?.[FLOW_DISMISS_KEY];
    if (!raw || typeof raw !== "object") return false;
    return Boolean(raw[page]);
  };

  const saveFlowDismiss = async (page) => {
    const bridge = api();
    if (!bridge?.get_config || !bridge?.save_config) return;
    try {
      const cur = await bridge.get_config();
      const dismissed = { ...(cur[FLOW_DISMISS_KEY] || {}), [page]: true };
      await bridge.save_config({ ...cur, [FLOW_DISMISS_KEY]: dismissed });
    } catch {}
  };

  let lastFlowKey = "";

  const syncFlowSteps = async () => {
    const page = currentPage();
    if (!isMacroPage()) return;

    const hub = document.getElementById(HUB[page]);
    const flow = hub?.querySelector(".blsm-macro-flow");
    if (!flow) return;

    let config = {};
    let running = false;
    if (api()?.get_config) {
      try {
        config = await api().get_config();
      } catch {}
    }
    if (api()?.get_session_stats) {
      try {
        const stats = await api().get_session_stats();
        running = !!stats?.running;
      } catch {}
    }

    if (flowDismissed(config, page)) {
      hub.querySelector(".blsm-macro-flow-wrap")?.remove();
      return;
    }

    const calDone = hasCalibration(config);
    const modeDone = pageModeEnabled(page, config);
    const states = stepStatesFor(page, calDone, modeDone, running);
    const spec = hubContent[page]?.();
    if (!spec) return;

    const key = `${page}:${states.join(",")}:${running}`;
    if (key === lastFlowKey) return;
    lastFlowKey = key;

    const wrap = hub.querySelector(".blsm-macro-flow-wrap");
    if (wrap) {
      wrap.outerHTML = flowHtml(spec.steps, states, true);
      const newWrap = hub.querySelector(".blsm-macro-flow-wrap");
      newWrap?.querySelector(".blsm-macro-flow-dismiss")?.addEventListener("click", () => {
        void saveFlowDismiss(page).then(() => newWrap?.remove());
      });
    }
  };

  const quickLinksHtml = () => `
    <div class="blsm-macro-quick">
      <button type="button" class="blsm-macro-chip" data-macro-go="Calibrations">📍 Calibrations</button>
      <button type="button" class="blsm-macro-chip" data-macro-go="Settings">⚙️ Hotkeys &amp; misc</button>
      <button type="button" class="blsm-macro-chip" data-macro-go="Fishing">🎣 Fishing</button>
      <button type="button" class="blsm-macro-chip" data-macro-go="Macro Status">📊 Status</button>
      <button type="button" class="blsm-macro-chip" data-macro-go="Schedule">${I("calendar")} Schedule</button>
      <span data-macro-hotkey-hint></span>
    </div>`;

  const bindQuickLinks = (hub) => {
    hub.querySelectorAll("[data-macro-go]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tab = btn.getAttribute("data-macro-go");
        if ((tab === "Macro Schedule" || tab === "Schedule") && window.BlossomScheduleTab?.open) {
          window.BlossomScheduleTab.open();
          return;
        }
        goToTab?.(tab);
      });
    });
    const hintHost = hub.querySelector("[data-macro-hotkey-hint]");
    if (hintHost) {
      void hotkeyHintHtml().then((html) => {
        hintHost.outerHTML = html;
      });
    }
  };

  const hubContent = {
    [PAGES.AUTOMATED]: () => ({
      subtitle:
        "Turn on the automations you want, then press Start in the header (or your hotkey). Calibrate under Macro Calibrations first.",
      steps: [
        {
          n: 1,
          title: "Calibrate UI",
          text: "Macro Calibrations — movement, merchant, fishing, and inventory marks for your resolution.",
        },
        {
          n: 2,
          title: "Enable modes",
          text: "Toggle merchant, quests, BR/SC, obby, biome tools, and other automations below.",
        },
        {
          n: 3,
          title: "Start macro",
          text: "Use the green Start button or your configured hotkey. Other tabs keep running in the background.",
        },
      ],
      quick: true,
    }),
    [PAGES.FISHING]: () => ({
      subtitle:
        "Full fishing loop: cast, detect bite, reel minigame, walk to dock, optional sell. Calibrate Fishing and Movements first.",
      steps: [
        {
          n: 1,
          title: "Calibrate",
          text: "Fishing + Movements calibrations — dock path, reel UI, collections menu, and sell trip if needed.",
        },
        {
          n: 2,
          title: "Enable mode",
          text: "Turn on Fishing Mode below. Merchant, quests, and potion craft pause while a fishing cycle runs.",
        },
        {
          n: 3,
          title: "Cast → reel → sell",
          text: "Blossom handles bite detection, the reel minigame, walking, and optional fish-shop sell.",
        },
      ],
      quick: true,
    }),
    [PAGES.STATUS]: () => ({
      subtitle: "Live view of which automations are active while the macro runs.",
      steps: [
        {
          n: 1,
          title: "Configure",
          text: "Enable automations on Automated Actions and Fishing, then calibrate if you have not yet.",
        },
        {
          n: 2,
          title: "Start macro",
          text: "Press Start in the header. This page updates as modules come online.",
        },
        {
          n: 3,
          title: "Watch modules",
          text: "Active Modules lists what Blossom is doing right now — merchant, fishing, quests, and more.",
        },
      ],
      quick: false,
    }),
  };

  const ensureHub = (page) => {
    const main = mainEl();
    const hubId = HUB[page];
    if (!main || !hubId) return document.getElementById(hubId);

    let hub = document.getElementById(hubId);
    if (hub) return hub;

    const spec = hubContent[page]?.();
    if (!spec) return null;

    const header = main.querySelector(".page-header");
    if (header) {
      const sub = header.querySelector("p");
      if (sub && spec.subtitle) sub.textContent = spec.subtitle;
    }

    hub = document.createElement("section");
    hub.id = hubId;
    hub.className = "blsm-macro-hub";

    const livePill =
      page === PAGES.STATUS
        ? `<div class="blsm-macro-live-pill" data-macro-live><span class="blsm-macro-live-dot"></span><span data-macro-live-text>Macro idle</span></div><div class="blsm-macro-reason" data-macro-reason hidden></div>`
        : "";

    hub.innerHTML =
      flowHtml(spec.steps, ["is-current", "is-pending", "is-pending"], true) +
      (spec.quick ? quickLinksHtml() : "") +
      livePill;

    bindQuickLinks(hub);
    hub.querySelector(".blsm-macro-flow-dismiss")?.addEventListener("click", () => {
      void saveFlowDismiss(page).then(() => hub.querySelector(".blsm-macro-flow-wrap")?.remove());
    });

    const anchor = header?.nextElementSibling || main.firstChild;
    if (anchor) main.insertBefore(hub, anchor);
    else main.appendChild(hub);

    return hub;
  };

  let bridgeReady = Boolean(api()?.get_session_stats);
  let runningKnown = false;
  let syncTimer = null;
  let syncInFlight = false;

  const applyLivePill = (running) => {
    const pill = document.querySelector("[data-macro-live]");
    if (!pill) return;
    pill.classList.toggle("is-running", running);
    const text = pill.querySelector("[data-macro-live-text]");
    if (text) text.textContent = running ? "Macro running" : "Macro idle";
  };

  const applyReason = (detail) => {
    const box = document.querySelector("[data-macro-reason]");
    if (!box) return;
    if (!detail) {
      box.hidden = true;
      box.textContent = "";
      box.classList.remove("is-error");
      return;
    }
    const parts = [];
    if (detail.reason) parts.push(detail.reason);
    const enabled = detail.enabled_modules ?? 0;
    const active = detail.active_modules ?? 0;
    if (detail.running) {
      parts.push(`${active} active · ${enabled} enabled module${enabled === 1 ? "" : "s"}`);
    }
    if (detail.uptime_seconds > 0) {
      parts.push(`uptime ${Math.floor(detail.uptime_seconds)}s`);
    }
    box.textContent = parts.join(" · ");
    box.hidden = false;
    box.classList.toggle("is-error", Boolean(detail.last_error && !detail.running));
  };

  // Authoritative running state from the backend — default idle until confirmed.
  const syncLivePill = () => {
    const pill = document.querySelector("[data-macro-live]");
    if (!pill) return;

    if (!bridgeReady || !api()?.get_session_stats) {
      applyLivePill(false);
      return;
    }

    if (syncTimer) clearTimeout(syncTimer);
    syncTimer = setTimeout(async () => {
      syncTimer = null;
      if (syncInFlight) return;
      syncInFlight = true;
      try {
        const stats = await api().get_session_stats();
        runningKnown = true;
        applyLivePill(!!stats?.running);
        // On the Status page, pull the richer detail so idle/stopped runs
        // explain themselves instead of silently showing "Macro idle".
        if (api()?.get_macro_status_detail && currentPage() === PAGES.STATUS) {
          try {
            const detail = await api().get_macro_status_detail();
            applyReason(detail);
          } catch {
            applyReason(null);
          }
        }
        void syncFlowSteps();
      } catch {
        if (!runningKnown) applyLivePill(false);
      } finally {
        syncInFlight = false;
      }
    }, runningKnown ? 300 : 0);
  };

  const onBridgeReady = () => {
    bridgeReady = true;
    runningKnown = false;
    syncLivePill();
  };

  window.addEventListener("pywebviewready", onBridgeReady, { once: true });
  if (bridgeReady) onBridgeReady();

  const layoutAutomated = () => {
    const main = mainEl();
    const gridId = GRID[PAGES.AUTOMATED];
    if (!main || document.getElementById(gridId)) return;

    const itemUsage = cardByTitle("Item Usage");
    const limbo = cardByTitle("Limbo Item Usage & Eden Detection");
    const biomeRec = cardByTitle("Biome Recording");
    const screenshots = cardByTitle("Periodical Screenshots & Quests");
    if (!itemUsage) return;

    const grid = document.createElement("div");
    grid.id = gridId;
    grid.className = "blsm-macro-grid blsm-macro-grid--auto";

    const left = document.createElement("div");
    left.className = "blsm-macro-grid-col";
    const right = document.createElement("div");
    right.className = "blsm-macro-grid-col";

    const bottom = document.createElement("div");
    bottom.id = "blsm-macro-grid-auto-bottom";
    bottom.className = "blsm-macro-grid-row";

    grid.appendChild(left);
    grid.appendChild(right);

    const hub = document.getElementById(HUB[PAGES.AUTOMATED]);
    const insertAfter = hub?.nextSibling;
    if (insertAfter) main.insertBefore(grid, insertAfter);
    else main.appendChild(grid);

    left.appendChild(itemUsage);

    // Keep injected panels (biome selector, BR/SC grid) after Item Usage in the left column
    const biomePanel = document.getElementById("blossom-biome-selector-panel");
    if (biomePanel && biomePanel.parentElement === main) {
      left.appendChild(biomePanel);
    }

    if (limbo) right.appendChild(limbo);
    if (biomeRec) bottom.appendChild(biomeRec);
    if (screenshots) bottom.appendChild(screenshots);

    if (bottom.childElementCount) grid.after(bottom);
  };

  const layoutFishing = () => {
    const main = mainEl();
    const gridId = GRID[PAGES.FISHING];
    if (!main || document.getElementById(gridId)) return;

    const mode = cardByTitle("Fishing Mode");
    const cal = cardByTitle("Fishing Calibration Values");
    if (!mode) return;

    const grid = document.createElement("div");
    grid.id = gridId;
    grid.className = "blsm-macro-grid blsm-macro-grid--fishing";

    const left = document.createElement("div");
    left.className = "blsm-macro-grid-col";
    const right = document.createElement("div");
    right.className = "blsm-macro-grid-col";

    grid.appendChild(left);
    grid.appendChild(right);

    const hub = document.getElementById(HUB[PAGES.FISHING]);
    const insertAfter = hub?.nextSibling;
    if (insertAfter) main.insertBefore(grid, insertAfter);
    else main.appendChild(grid);

    left.appendChild(mode);
    if (cal) right.appendChild(cal);
  };

  const layoutStatus = () => {
    const main = mainEl();
    const gridId = GRID[PAGES.STATUS];
    if (!main || document.getElementById(gridId)) return;

    const modules = cardByTitle("Active Modules");
    if (!modules) return;

    const grid = document.createElement("div");
    grid.id = gridId;
    grid.className = "blsm-macro-grid blsm-macro-grid--status";

    const col = document.createElement("div");
    col.className = "blsm-macro-grid-col";
    grid.appendChild(col);

    const hub = document.getElementById(HUB[PAGES.STATUS]);
    const insertAfter = hub?.nextSibling;
    if (insertAfter) main.insertBefore(grid, insertAfter);
    else main.appendChild(grid);

    col.appendChild(modules);
  };

  const layoutForPage = (page) => {
    if (page === PAGES.AUTOMATED) layoutAutomated();
    else if (page === PAGES.FISHING) layoutFishing();
    else if (page === PAGES.STATUS) layoutStatus();
  };

  const teardown = () => {
    document.documentElement.classList.remove("blsm-macro-hub-active");
    Object.values(HUB).forEach((id) => document.getElementById(id)?.remove());
    Object.values(GRID).forEach((id) => document.getElementById(id)?.remove());
    document.getElementById("blsm-macro-grid-auto-bottom")?.remove();
  };

  const refresh = () => {
    const page = currentPage();
    if (!isMacroPage()) {
      teardown();
      return;
    }

    document.documentElement.classList.add("blsm-macro-hub-active");
    ensureHub(page);
    layoutForPage(page);
    syncLivePill();
    lastFlowKey = "";
    void syncFlowSteps();

    // Refresh hotkey hint when returning to automated/fishing hub
    const hub = document.getElementById(HUB[page]);
    if (hub && hubContent[page]?.().quick) {
      const existing = hub.querySelector(".blsm-macro-hotkey-hint");
      if (existing) {
        void hotkeyHintHtml().then((html) => {
          existing.outerHTML = html;
        });
      }
    }
  };

  if (observeMain) {
    observeMain(refresh, 120, [...MACRO_PAGES]);
  } else {
    window.addEventListener("pywebviewready", refresh);
    refresh();
  }

  // Keep live pill in sync when start/stop toggles
  if (observeMain) {
    observeMain(syncLivePill, 0);
  }
})();
