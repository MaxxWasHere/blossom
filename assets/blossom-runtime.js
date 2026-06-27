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



  const TERMINAL_STATES = new Set(["installed", "error", "unavailable"]);



  const card = () => document.getElementById(CARD_ID);



  const isDeterminate = () =>

    window.BlossomM3Progress?.isDeterminate

      ? window.BlossomM3Progress.isDeterminate(model.percent, model.total)

      : Number.isFinite(model.percent) && model.percent >= 0 && (model.total > 0 || model.percent >= 100);



  const stopTrack = (track) => {

    if (track && window.BlossomM3Progress?.unmount) {

      window.BlossomM3Progress.unmount(track);

    }

  };



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



  const syncProgress = (track, indeterminate, percent, reset) => {

    if (!track || !window.BlossomM3Progress) return;

    if (indeterminate) {

      window.BlossomM3Progress.update(track, { indeterminate: true, reset: !!reset });

      return;

    }

    window.BlossomM3Progress.update(track, {

      indeterminate: false,

      percent: Math.max(0, Math.min(100, Number(percent) || 0)),

      reset: !!reset,

    });

  };



  const render = () => {

    const el = card();

    if (!el) return;



    const statusEl = el.querySelector(".blsm-rt-status");

    const detailEl = el.querySelector(".blsm-rt-detail");

    const msgEl = el.querySelector(".blsm-rt-message");

    const btn = el.querySelector(".blsm-rt-btn");

    const bar = el.querySelector(".blsm-rt-progress");

    const track = el.querySelector(".blsm-rt-progress-track");

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



    const showBar = model.state === "installing";

    if (bar) {

      bar.hidden = !showBar;

      if (showBar && track) {

        const determinate = isDeterminate();

        bar.classList.toggle("is-indeterminate", !determinate);

        if (determinate) {

          syncProgress(track, false, model.percent);

        } else {

          syncProgress(track, true);

        }

      } else if (track) {

        bar.classList.remove("is-indeterminate");

        stopTrack(track);

      }

    }

    if (pct) {

      if (showBar && isDeterminate()) {

        const dl = fmtMB(model.downloaded);

        const tot = fmtMB(model.total);

        const mb = dl && tot ? ` (${dl} / ${tot})` : dl ? ` (${dl})` : "";

        pct.textContent = `${Math.round(model.percent)}%${mb}`;

        pct.hidden = false;

      } else if (showBar) {

        pct.textContent = model.downloaded > 0 ? `Downloading… ${fmtMB(model.downloaded)}` : "Preparing download…";

        pct.hidden = false;

      } else {

        pct.hidden = true;

        pct.textContent = "";

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

    const wasInstalling = model.state === "installing";

    try {

      const res = await bridge.get_opencv_status();

      if (res && typeof res === "object") {

        if (res.state === "installing") {

          // Backend may still report installing briefly after a push "installed" event.

          if (TERMINAL_STATES.has(model.state)) return;

          model.state = "installing";

          if (model.percent === null) model.percent = -1;

          render();

          return;

        }

        if (wasInstalling) {

          if (res.state !== "installed" && res.state !== "unavailable" && res.state !== "error") {

            return;

          }

        }

        model.state = res.state || "not_installed";

        model.version = res.version || null;

        model.size = res.size || null;

        if (res.state !== "installing") {

          model.percent = null;

          model.downloaded = 0;

          model.total = 0;

        }

        // Surface a one-time explanatory message for the unavailable case.

        if (res.state === "unavailable") {

          model.message = res.message || "Component not available for this build yet; fishing uses the built-in fallback.";

        } else if (res.state === "installed" || res.state === "not_installed") {

          model.message = "";

        } else if (res.state === "error" && !res.message) {

          model.message = "";

        }

        render();

      }

    } catch (err) {

      console.warn("[runtime] status check failed", err);

      if (!wasInstalling) {

        model.state = "not_installed";

        render();

      }

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

    window.BlossomLoading?.begin?.(

      "runtime-install",

      "Installing fishing vision component…"

    );

    render();

    const track = card()?.querySelector(".blsm-rt-progress-track");

    syncProgress(track, true, 0, true);

    try {

      const result = await bridge.install_opencv();

      if (result?.already_running) return;

    } catch (err) {

      console.warn("[runtime] install call failed", err);

      if (model.state === "installing") {

        model.state = "error";

        model.message = "Install failed. Fishing still works using the built-in fallback.";

        model.percent = null;

        window.BlossomLoading?.end?.("runtime-install");

        render();

      }

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

      const track = card()?.querySelector(".blsm-rt-progress-track");

      stopTrack(track);

      card()?.remove();

      return;

    }

    mountCard();

  };



  const finishInstall = (state, message) => {

    model.state = state;

    model.percent = null;

    model.downloaded = 0;

    model.total = 0;

    if (message) model.message = message;

    window.BlossomLoading?.end?.("runtime-install");

    stopTrack(card()?.querySelector(".blsm-rt-progress-track"));

    render();

    if (state === "installed") {

      setTimeout(() => void refreshStatus(), 350);

    }

  };



  // Backend bridge hooks (pushed via evaluate_js from the install thread).

  window.BlossomRuntime = {

    onInstallProgress(percent, downloaded, total) {

      model.percent = Number(percent);

      model.downloaded = Number(downloaded) || 0;

      model.total = Number(total) || 0;

      if (model.state !== "installing") model.state = "installing";

      if (isDeterminate()) {

        model.message = `Downloading… ${Math.round(model.percent)}%`;

      } else if (model.downloaded > 0) {

        model.message = `Downloading… ${fmtMB(model.downloaded)}`;

      } else if (!model.message) {

        model.message = "Preparing download…";

      }

      window.BlossomLoading?.setProgress?.(percent, downloaded, total);

      render();

    },

    onInstallState(state, message) {

      if (state === "installed") {

        finishInstall("installed", message);

        return;

      }

      if (state === "error" || state === "unavailable") {

        finishInstall(state, message);

        return;

      }

      model.state = state || model.state;

      if (message) model.message = message;

      if (state === "installing" && model.percent === null) {

        model.percent = -1;

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


