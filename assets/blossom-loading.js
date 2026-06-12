(function () {
  const OVERLAY_ID = "blossom-loading-overlay";
  const DEFAULT_MESSAGE = "Starting Blossom…";

  const PHASE_TIMEOUT_MS = {
    startup: 45000,
    "runtime-sync": 120000,
    update: 600000,
    "runtime-install": 300000,
  };

  const phases = new Map();
  let hideTimer = null;
  let progress = { percent: null, downloaded: 0, total: 0 };
  let displayMessage = DEFAULT_MESSAGE;

  const formatBytes = (bytes) => {
    const n = Number(bytes) || 0;
    if (n <= 0) return "0 MB";
    const mb = n / (1024 * 1024);
    if (mb >= 1024) return (mb / 1024).toFixed(2) + " GB";
    if (mb >= 10) return mb.toFixed(0) + " MB";
    return mb.toFixed(1) + " MB";
  };

  const overlay = () => document.getElementById(OVERLAY_ID);

  const activePhase = () => {
    if (phases.has("update")) return "update";
    if (phases.has("runtime-install")) return "runtime-install";
    if (phases.has("runtime-sync")) return "runtime-sync";
    if (phases.has("startup")) return "startup";
    for (const key of phases.keys()) return key;
    return null;
  };

  const primaryMessage = () => {
    for (const key of ["update", "runtime-install", "runtime-sync", "startup"]) {
      const entry = phases.get(key);
      if (entry?.message) return entry.message;
    }
    for (const entry of phases.values()) {
      if (entry.message) return entry.message;
    }
    return displayMessage || DEFAULT_MESSAGE;
  };

  const showProgress = () =>
    progress.percent !== null &&
    (phases.has("update") || phases.has("runtime-install") || phases.has("runtime-sync"));

  const ensureOverlay = () => {
    let el = overlay();
    if (el) return el;

    el = document.createElement("div");
    el.id = OVERLAY_ID;
    el.className = "blossom-loading-overlay";
    el.setAttribute("role", "status");
    el.setAttribute("aria-live", "polite");
    el.setAttribute("aria-busy", "true");
    el.innerHTML = `
      <div class="blossom-loading-aurora a1" aria-hidden="true"></div>
      <div class="blossom-loading-aurora a2" aria-hidden="true"></div>
      <div class="blossom-loading-card">
        <img class="blossom-loading-logo" src="./blossom.png" alt="" width="72" height="72" />
        <h2 class="blossom-loading-brand">Blossom</h2>
        <p class="blossom-loading-message">${DEFAULT_MESSAGE}</p>
        <div class="blossom-loading-spinner" data-blsm-spinner aria-hidden="true"></div>
        <div class="blossom-loading-progress" data-blsm-progress hidden>
          <div class="blossom-loading-progress-track">
            <div class="blossom-loading-progress-fill"></div>
          </div>
          <div class="blossom-loading-progress-meta">
            <span class="blsm-loading-pct">Starting…</span>
            <span class="blsm-loading-bytes"></span>
          </div>
        </div>
        <p class="blossom-loading-version" data-blsm-version></p>
      </div>`;
    (document.body || document.documentElement).appendChild(el);
    return el;
  };

  const dismissOverlay = () => {
    const el = overlay();
    if (!el) return;
    el.classList.add("is-hiding");
    el.classList.remove("is-active");
    el.setAttribute("aria-busy", "false");
    if (hideTimer) clearTimeout(hideTimer);
    hideTimer = setTimeout(() => {
      overlay()?.remove();
      hideTimer = null;
    }, 340);
  };

  const render = () => {
    const el = overlay();
    const active = phases.size > 0;

    if (!active) {
      if (el) dismissOverlay();
      return;
    }

    if (hideTimer) {
      clearTimeout(hideTimer);
      hideTimer = null;
    }

    const node = ensureOverlay();
    node.classList.remove("is-hiding");
    node.classList.add("is-active");
    node.setAttribute("aria-busy", "true");
    const coversChrome =
      phases.has("update") ||
      phases.has("runtime-install") ||
      phases.has("runtime-sync");
    node.style.zIndex = coversChrome ? "100002" : "";

    const msgEl = node.querySelector(".blossom-loading-message");
    if (msgEl) msgEl.textContent = primaryMessage();

    const spinner = node.querySelector("[data-blsm-spinner]");
    const bar = node.querySelector("[data-blsm-progress]");
    const showBar = showProgress();

    if (spinner) spinner.hidden = showBar;
    if (bar) bar.hidden = !showBar;

    if (showBar && bar) {
      const fill = bar.querySelector(".blossom-loading-progress-fill");
      const pctEl = bar.querySelector(".blsm-loading-pct");
      const bytesEl = bar.querySelector(".blsm-loading-bytes");
      const pct = Number(progress.percent);
      const totalN = Number(progress.total) || 0;

      if (!Number.isFinite(pct) || pct < 0 || totalN <= 0) {
        bar.setAttribute("data-state", "indeterminate");
        if (fill) fill.style.width = "";
        if (pctEl) {
          pctEl.textContent = progress.downloaded > 0 ? formatBytes(progress.downloaded) : "Downloading…";
        }
        if (bytesEl) bytesEl.textContent = "";
      } else {
        const clamped = Math.max(0, Math.min(100, pct));
        bar.setAttribute("data-state", "determinate");
        if (fill) fill.style.width = clamped + "%";
        if (pctEl) pctEl.textContent = clamped.toFixed(0) + "%";
        if (bytesEl) {
          bytesEl.textContent = `${formatBytes(progress.downloaded)} / ${formatBytes(totalN)}`;
        }
      }
    } else {
      progress = { percent: null, downloaded: 0, total: 0 };
    }
  };

  const clearPhaseTimeout = (entry) => {
    if (entry?.timeoutId) {
      clearTimeout(entry.timeoutId);
      entry.timeoutId = null;
    }
  };

  const schedulePhaseTimeout = (phase, entry) => {
    const ms = PHASE_TIMEOUT_MS[phase] || 60000;
    clearPhaseTimeout(entry);
    entry.timeoutId = setTimeout(() => {
      console.warn(`[BlossomLoading] phase timed out: ${phase}`);
      end(phase, { force: true });
    }, ms);
  };

  const begin = (phase, message) => {
    const key = String(phase || "task").trim() || "task";
    const msg = String(message || "").trim();
    let entry = phases.get(key);
    if (entry) {
      entry.ref += 1;
      if (msg) entry.message = msg;
    } else {
      entry = { ref: 1, message: msg || "" };
      phases.set(key, entry);
    }
    if (msg) displayMessage = msg;
    schedulePhaseTimeout(key, entry);
    render();
  };

  const end = (phase, options) => {
    const key = String(phase || "").trim();
    if (!key) return;
    const entry = phases.get(key);
    if (!entry) return;

    if (options?.force) {
      entry.ref = 0;
    } else {
      entry.ref -= 1;
    }

    if (entry.ref <= 0) {
      clearPhaseTimeout(entry);
      phases.delete(key);
      if (activePhase() === null) {
        progress = { percent: null, downloaded: 0, total: 0 };
      }
    }
    render();
  };

  const setMessage = (message) => {
    const msg = String(message || "").trim();
    if (!msg) return;
    displayMessage = msg;
    const phase = activePhase();
    if (phase) {
      const entry = phases.get(phase);
      if (entry) entry.message = msg;
    }
    render();
  };

  const setProgress = (percent, downloaded, total) => {
    progress = {
      percent: Number(percent),
      downloaded: Number(downloaded) || 0,
      total: Number(total) || 0,
    };
    render();
  };

  const isActive = () => phases.size > 0;

  // --- Startup bootstrap (real events, not a fake delay) ---
  let apiReady = false;
  let configReady = false;
  let uiReady = false;
  let startupFinished = false;

  const maybeFinishStartup = () => {
    if (startupFinished) return;
    if (!apiReady || !configReady || !uiReady) return;
    startupFinished = true;
    end("startup");
  };

  const waitForUi = () => {
    if (uiReady) return;
    const ready =
      document.querySelectorAll(".sidebar-item").length >= 2 ||
      document.querySelector(".window-frame .main-content, .window-frame .page-content");
    if (ready) {
      uiReady = true;
      maybeFinishStartup();
      return;
    }
    const root = document.getElementById("root");
    if (!root) return;
    const obs = new MutationObserver(() => {
      const ok =
        document.querySelectorAll(".sidebar-item").length >= 2 ||
        document.querySelector(".window-frame .main-content, .window-frame .page-content");
      if (!ok) return;
      uiReady = true;
      obs.disconnect();
      maybeFinishStartup();
    });
    obs.observe(root, { childList: true, subtree: true });
    setTimeout(() => {
      if (!uiReady) {
        uiReady = true;
        obs.disconnect();
        maybeFinishStartup();
      }
    }, 12000);
  };

  const onBridgeReady = () => {
    if (apiReady) return;
    apiReady = true;
    setMessage("Loading settings…");

    const bridge = window.pywebview?.api;
    const finishConfig = () => {
      if (configReady) return;
      configReady = true;
      maybeFinishStartup();
    };

    if (bridge?.get_config) {
      Promise.resolve(bridge.get_config())
        .catch((err) => console.warn("[BlossomLoading] config preload failed", err))
        .finally(finishConfig);
    } else {
      finishConfig();
    }

    if (bridge?.get_macro_version) {
      Promise.resolve(bridge.get_macro_version())
        .then((ver) => {
          const node = overlay()?.querySelector("[data-blsm-version]");
          if (node && ver) node.textContent = String(ver);
        })
        .catch(() => {});
    }

    waitForUi();
    maybeFinishStartup();
  };

  begin("startup", DEFAULT_MESSAGE);

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => setMessage("Loading interface…"), { once: true });
  } else {
    setMessage("Loading interface…");
  }

  window.addEventListener("pywebviewready", () => {
    setMessage("Connecting to Blossom…");
    void onBridgeReady();
  });

  setTimeout(() => {
    if (!apiReady) {
      console.warn("[BlossomLoading] pywebview bridge not ready — continuing without backend");
      apiReady = true;
      configReady = true;
      waitForUi();
      maybeFinishStartup();
    }
  }, PHASE_TIMEOUT_MS.startup);

  // Never leave the launch overlay up indefinitely if startup gates stall.
  setTimeout(() => {
    if (startupFinished) return;
    console.warn("[BlossomLoading] forcing startup completion");
    apiReady = true;
    configReady = true;
    uiReady = true;
    maybeFinishStartup();
  }, 18000);

  window.BlossomLoading = {
    begin,
    end,
    setMessage,
    setProgress,
    isActive,
    getActivePhase: activePhase,
  };
})();
