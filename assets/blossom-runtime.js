(function () {
  const { observeMain, pageHeaderTitle } = window.Blossom || {};
  const CARD_ID = "blossom-runtime-card";
  const SETTINGS_PAGE = "Settings & extras";

  const api = () => window.pywebview?.api;

  // Local mirror of the last backend status so re-renders (DOM swaps, page
  // re-entry) don't flicker. No polling: refreshed on mount + after install.
  let model = {
    state: "checking", // checking | installed | not_installed | installing | error | unavailable
    message: "",
    version: null,
    size: null,
    percent: null, // null = no bar; -1 = indeterminate; 0..100 = determinate
    downloaded: 0,
    total: 0,
  };

  const fmtMB = (bytes) => {
    const n = Number(bytes) || 0;
    if (n <= 0) return "";
    return (n / (1024 * 1024)).toFixed(1) + " MB";
  };

  const STATUS_TEXT = {
    checking: "Checking…",
    installed: "Installed",
    not_installed: "Not installed",
    installing: "Installing…",
    error: "Not installed",
    unavailable: "Not available yet",
  };

  const card = () => document.getElementById(CARD_ID);

  const buttonLabel = () => {
    switch (model.state) {
      case "installed":
        return "Reinstall";
      case "installing":
        return "Installing…";
      case "error":
        return "Retry";
      default:
        return "Install";
    }
  };

  const render = () => {
    const el = card();
    if (!el) return;

    const statusEl = el.querySelector(".blsm-rt-status");
    const detailEl = el.querySelector(".blsm-rt-detail");
    const msgEl = el.querySelector(".blsm-rt-message");
    const btn = el.querySelector(".blsm-rt-btn");
    const bar = el.querySelector(".blsm-rt-progress");
    const fill = el.querySelector(".blsm-rt-progress-fill");
    const pct = el.querySelector(".blsm-rt-progress-text");

    el.dataset.state = model.state;

    if (statusEl) {
      statusEl.textContent = "Fishing vision component: " + (STATUS_TEXT[model.state] || "Unknown");
    }

    if (detailEl) {
      const bits = [];
      if (model.state === "installed") {
        if (model.version) bits.push("OpenCV " + model.version);
        const mb = fmtMB(model.size);
        if (mb) bits.push(mb);
      }
      detailEl.textContent = bits.join(" · ");
      detailEl.hidden = bits.length === 0;
    }

    if (msgEl) {
      msgEl.textContent = model.message || "";
      msgEl.hidden = !model.message;
      msgEl.classList.toggle("is-error", model.state === "error");
    }

    const showBar = model.state === "installing" && model.percent !== null;
    if (bar) {
      bar.hidden = !showBar;
      bar.classList.toggle("is-indeterminate", showBar && model.percent < 0);
    }
    if (showBar && fill) {
      if (model.percent >= 0) {
        fill.style.width = Math.max(0, Math.min(100, model.percent)) + "%";
      } else {
        fill.style.width = "";
      }
    }
    if (pct) {
      if (showBar && model.percent >= 0) {
        const dl = fmtMB(model.downloaded);
        const tot = fmtMB(model.total);
        const mb = dl && tot ? ` (${dl} / ${tot})` : dl ? ` (${dl})` : "";
        pct.textContent = `${Math.round(model.percent)}%${mb}`;
        pct.hidden = false;
      } else if (showBar) {
        pct.textContent = "Downloading…";
        pct.hidden = false;
      } else {
        pct.hidden = true;
      }
    }

    if (btn) {
      btn.textContent = buttonLabel();
      btn.disabled = model.state === "installing" || model.state === "checking" || model.state === "unavailable";
    }
  };

  const refreshStatus = async () => {
    const bridge = api();
    if (!bridge?.get_opencv_status) return;
    try {
      const res = await bridge.get_opencv_status();
      if (res && typeof res === "object") {
        model.state = res.state || "not_installed";
        model.version = res.version || null;
        model.size = res.size || null;
        if (res.state !== "installing") {
          model.percent = null;
        }
        // Surface a one-time explanatory message for the unavailable case.
        if (res.state === "unavailable") {
          model.message = res.message || "Component not available for this build yet; fishing uses the built-in fallback.";
        } else if (res.state === "installed" || res.state === "not_installed") {
          model.message = "";
        }
        render();
      }
    } catch (err) {
      console.warn("[runtime] status check failed", err);
    }
  };

  const startInstall = async () => {
    const bridge = api();
    if (!bridge?.install_opencv) return;
    model.state = "installing";
    model.message = "Preparing download…";
    model.percent = -1;
    model.downloaded = 0;
    model.total = 0;
    render();
    try {
      await bridge.install_opencv();
    } catch (err) {
      console.warn("[runtime] install call failed", err);
      model.state = "error";
      model.message = "Install failed. Fishing still works using the built-in fallback.";
      model.percent = null;
      render();
    }
  };

  const buildCard = () => {
    const el = document.createElement("div");
    el.id = CARD_ID;
    el.className = "card blsm-rt-card";
    el.style.marginBottom = "16px";
    el.innerHTML = `
      <div class="card-header">
        <div class="card-icon">🎣</div>
        <div>
          <h3>Fishing vision component</h3>
          <p>Optional faster bite &amp; reel detection for Fishing Mode</p>
        </div>
      </div>
      <div class="blsm-rt-body">
        <p class="blsm-rt-status">Fishing vision component: Checking…</p>
        <p class="blsm-rt-detail" hidden></p>
        <p class="blsm-rt-explain">
          Fishing can use this component for faster, more reliable bite and reel
          detection. Without it, fishing still works using the slower built-in
          fallback, so installing it is optional.
        </p>
        <div class="blsm-rt-progress" hidden>
          <div class="blsm-rt-progress-track">
            <div class="blsm-rt-progress-fill"></div>
          </div>
          <span class="blsm-rt-progress-text" hidden></span>
        </div>
        <p class="blsm-rt-message" role="status" hidden></p>
        <div class="blsm-rt-actions">
          <button type="button" class="btn btn-accent blsm-rt-btn">Install</button>
        </div>
      </div>
    `;
    el.querySelector(".blsm-rt-btn").addEventListener("click", () => void startInstall());
    return el;
  };

  const findInsertTarget = () => {
    const header = Array.from(document.querySelectorAll(".page-header")).find(
      (h) => h.querySelector("h2")?.textContent?.trim() === SETTINGS_PAGE
    );
    return header?.parentElement || null;
  };

  const mountCard = () => {
    const existing = card();
    if (existing?.isConnected) {
      render();
      return;
    }
    if (existing) existing.remove();
    const parent = findInsertTarget();
    if (!parent) return;
    const el = buildCard();
    parent.appendChild(el);
    render();
    void refreshStatus();
  };

  const onSettingsPage = () =>
    (pageHeaderTitle ? pageHeaderTitle() : document.querySelector(".page-header h2")?.textContent?.trim()) ===
    SETTINGS_PAGE;

  const sync = () => {
    if (!onSettingsPage()) {
      card()?.remove();
      return;
    }
    mountCard();
  };

  // Backend bridge hooks (pushed via evaluate_js from the install thread).
  window.BlossomRuntime = {
    onInstallProgress(percent, downloaded, total) {
      model.percent = Number(percent);
      model.downloaded = Number(downloaded) || 0;
      model.total = Number(total) || 0;
      if (model.state !== "installing") model.state = "installing";
      render();
    },
    onInstallState(state, message) {
      model.state = state || model.state;
      model.message = message || "";
      if (state === "installed") {
        model.percent = null;
        void refreshStatus();
      } else if (state !== "installing") {
        model.percent = null;
      }
      render();
    },
    refreshStatus,
    getState: () => ({ ...model }),
  };

  if (observeMain) observeMain(sync, 0, SETTINGS_PAGE);
  else {
    sync();
    window.addEventListener("pywebviewready", sync);
  }
})();
