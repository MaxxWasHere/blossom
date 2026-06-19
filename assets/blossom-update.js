(function () {
  const OVERLAY_ID = "blossom-update-overlay";
  let pending = null;
  let allowApply = false;
  let applyWrapped = false;
  let statusWrapped = false;
  // Versions the user dismissed this session. Cleared on next launch (fresh JS
  // context), so a dismissed version re-prompts next launch, and a newer
  // version always prompts because it is not in this set.
  const dismissedVersions = new Set();
  let escHandler = null;

  const hideBuiltinBanner = () => {
    document.querySelectorAll(".update-banner").forEach((el) => {
      el.style.display = "none";
    });
  };

  const closeModal = () => {
    document.getElementById(OVERLAY_ID)?.remove();
    pending = null;
  };

  const setStatus = (text) => {
    const el = document.querySelector(".blossom-update-status");
    if (el) el.textContent = text || "";
  };

  const formatBytes = (bytes) => {
    const n = Number(bytes) || 0;
    if (n <= 0) return "0 MB";
    const mb = n / (1024 * 1024);
    if (mb >= 1024) return (mb / 1024).toFixed(2) + " GB";
    if (mb >= 10) return mb.toFixed(0) + " MB";
    return mb.toFixed(1) + " MB";
  };

  // Replace the prompt body with the live download/progress screen. Reused for
  // a fresh download and for retries after a failure.
  const buildProgressView = () => {
    const dialog = document.querySelector(".blossom-update-dialog");
    if (!dialog) return;
    dialog.innerHTML = `
      <h3 class="blossom-update-title">Downloading update</h3>
      <p class="blossom-update-sub">Blossom <strong>${pending?.version ?? ""}</strong> is downloading. Keep the app open.</p>
      <div class="blossom-progress" data-state="indeterminate">
        <div class="blossom-progress-track"><div class="blossom-progress-fill"></div></div>
        <div class="blossom-progress-meta">
          <span class="blossom-progress-percent">Starting…</span>
          <span class="blossom-progress-bytes"></span>
        </div>
      </div>
      <p class="blossom-update-status"></p>
      <div class="blossom-update-actions" data-progress-actions hidden>
        <button type="button" class="btn btn-secondary" data-blossom-update-close>Close</button>
        <button type="button" class="btn btn-accent" data-blossom-update-retry hidden>Retry</button>
      </div>`;
    dialog.querySelector("[data-blossom-update-close]")?.addEventListener("click", () => {
      allowApply = false;
      closeModal();
      hideBuiltinBanner();
    });
    dialog.querySelector("[data-blossom-update-retry]")?.addEventListener("click", () => {
      runApply();
    });
  };

  const showProgressActions = ({ retry } = {}) => {
    const actions = document.querySelector("[data-progress-actions]");
    if (actions) actions.hidden = false;
    const retryBtn = document.querySelector("[data-blossom-update-retry]");
    if (retryBtn) retryBtn.hidden = !retry;
  };

  const setProgressTitle = (title, sub) => {
    const titleEl = document.querySelector(".blossom-update-title");
    const subEl = document.querySelector(".blossom-update-sub");
    if (titleEl && title != null) titleEl.textContent = title;
    if (subEl && sub != null) subEl.innerHTML = sub;
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

  const updateProgress = (percent, downloaded, total) => {
    window.BlossomLoading?.setProgress?.(percent, downloaded, total);
    // Ignore stray progress frames if the overlay isn't showing a download view.
    if (!document.getElementById(OVERLAY_ID)) return;
    if (!document.querySelector(".blossom-progress")) buildProgressView();
    const wrap = document.querySelector(".blossom-progress");
    if (!wrap) return;
    const track = wrap.querySelector(".blossom-progress-track");
    const pctEl = wrap.querySelector(".blossom-progress-percent");
    const bytesEl = wrap.querySelector(".blossom-progress-bytes");
    const pct = Number(percent);
    const totalN = Number(total) || 0;
    const determinate =
      window.BlossomM3Progress?.isDeterminate?.(pct, totalN) ??
      (Number.isFinite(pct) && pct >= 0 && (totalN > 0 || pct >= 100));
    if (!determinate) {
      wrap.setAttribute("data-state", "indeterminate");
      syncProgress(track, true);
      if (pctEl) pctEl.textContent = downloaded > 0 ? formatBytes(downloaded) : "Starting…";
      if (bytesEl) bytesEl.textContent = "";
      return;
    }
    const clamped = Math.max(0, Math.min(100, pct));
    wrap.setAttribute("data-state", "determinate");
    syncProgress(track, false, clamped);
    if (pctEl) pctEl.textContent = clamped.toFixed(0) + "%";
    if (bytesEl) bytesEl.textContent = `${formatBytes(downloaded)} / ${formatBytes(totalN)}`;
  };

  const markInstalling = () => {
    const wrap = document.querySelector(".blossom-progress");
    if (wrap) {
      wrap.setAttribute("data-state", "determinate");
      const track = wrap.querySelector(".blossom-progress-track");
      syncProgress(track, false, 100);
      const pctEl = wrap.querySelector(".blossom-progress-percent");
      if (pctEl) pctEl.textContent = "100%";
    }
    setProgressTitle("Installing", "Blossom will restart with the new version.");
    setStatus("");
  };

  const markLauncherRestart = (version, launcher) => {
    const wrap = document.querySelector(".blossom-progress");
    if (wrap) {
      wrap.setAttribute("data-state", "determinate");
      const track = wrap.querySelector(".blossom-progress-track");
      syncProgress(track, false, 100);
      const pctEl = wrap.querySelector(".blossom-progress-percent");
      if (pctEl) pctEl.textContent = "Ready";
    }
    setProgressTitle(
      "Restart the launcher",
      `Blossom <strong>${version || ""}</strong> was downloaded. Close this window, then open <code>${launcher || "Blossom.exe"}</code> again to run the new version.`
    );
    setStatus("Your settings in %LOCALAPPDATA%\\Blossom\\ are kept.");
    showProgressActions({ retry: false });
  };

  const markManual = (version, path) => {
    const wrap = document.querySelector(".blossom-progress");
    if (wrap) {
      wrap.setAttribute("data-state", "determinate");
      const track = wrap.querySelector(".blossom-progress-track");
      syncProgress(track, false, 100);
      const pctEl = wrap.querySelector(".blossom-progress-percent");
      if (pctEl) pctEl.textContent = "Downloaded";
    }
    setProgressTitle(
      "Manual install required",
      `Blossom <strong>${version || ""}</strong> needs a full reinstall. The file location was opened${path ? `:<br><code>${path}</code>` : "."}<br>Close Blossom and run the downloaded installer.`
    );
    setStatus("");
    showProgressActions({ retry: false });
  };

  const markFailed = () => {
    setProgressTitle("Update failed", "The download could not be completed.");
    setStatus("You can retry, or download the latest build from GitHub.");
    showProgressActions({ retry: true });
  };

  const removeEsc = () => {
    if (escHandler) {
      document.removeEventListener("keydown", escHandler);
      escHandler = null;
    }
  };

  // Dismiss = close for now + suppress this exact version for the session.
  // Never disables updates; a newer version or the next launch re-prompts.
  const dismissCurrent = () => {
    if (pending?.version) dismissedVersions.add(pending.version);
    allowApply = false;
    removeEsc();
    closeModal();
    hideBuiltinBanner();
  };

  const runApply = async () => {
    const api = window.pywebview?.api;
    if (!api?.apply_update || !pending) return;
    allowApply = true;
    removeEsc();
    buildProgressView();
    updateProgress(-1, 0, 0);
    const track = document.querySelector(".blossom-progress-track");
    syncProgress(track, true, 0, true);
    try {
      await api.apply_update(pending.url, pending.version);
    } catch (error) {
      console.error("[BlossomUpdate] apply failed:", error);
      markFailed();
      allowApply = false;
    }
  };

  const showPrompt = (version, url) => {
    if (!version || !url) return;
    const v = String(version);
    const u = String(url);
    // User dismissed this version earlier this session: stay quiet.
    if (dismissedVersions.has(v)) return;
    // Already showing this exact prompt: don't rebuild.
    if (pending?.version === v && pending?.url === u && document.getElementById(OVERLAY_ID)) {
      return;
    }
    hideBuiltinBanner();
    // Remove any prior overlay before we (re)build, then set pending.
    document.getElementById(OVERLAY_ID)?.remove();
    pending = { version: v, url: u };

    const overlay = document.createElement("div");
    overlay.id = OVERLAY_ID;
    overlay.className = "blossom-update-overlay";
    overlay.innerHTML = `
      <div class="blossom-update-dialog blossom-update-toast" role="dialog" aria-modal="false" aria-label="Update available">
        <button type="button" class="blossom-update-x" data-blossom-update-x aria-label="Dismiss update notification">${window.BlossomIcons?.svg("close") || "×"}</button>
        <h3>Update available &mdash; ${v}</h3>
        <p>
          A newer Blossom build is ready. Updating closes and restarts the app
          with the new version. Your settings in
          <code>%LOCALAPPDATA%\\Blossom\\</code> are kept.
        </p>
        <p class="blossom-update-status"></p>
        <div class="blossom-update-actions">
          <button type="button" class="btn btn-secondary" data-blossom-update-dismiss>Dismiss</button>
          <button type="button" class="btn btn-accent" data-blossom-update-confirm>Update</button>
        </div>
      </div>`;

    overlay
      .querySelector("[data-blossom-update-x]")
      ?.addEventListener("click", dismissCurrent);
    overlay
      .querySelector("[data-blossom-update-dismiss]")
      ?.addEventListener("click", dismissCurrent);
    overlay
      .querySelector("[data-blossom-update-confirm]")
      ?.addEventListener("click", () => runApply());

    document.body.appendChild(overlay);

    removeEsc();
    escHandler = (event) => {
      // Only the available popup is Esc-dismissable; never mid-download.
      if (event.key !== "Escape") return;
      if (document.querySelector("[data-blossom-update-dismiss]")) dismissCurrent();
    };
    document.addEventListener("keydown", escHandler);
  };

  const wrapApplyUpdate = () => {
    const api = window.pywebview?.api;
    if (!api || applyWrapped || typeof api.apply_update !== "function") return;
    const original = api.apply_update.bind(api);
    api.apply_update = async function wrappedApplyUpdate(url, version) {
      if (!allowApply) {
        showPrompt(String(version || pending?.version || "?"), String(url || pending?.url || ""));
        return { ok: false, pending: true, prompt: true };
      }
      allowApply = false;
      return original(url, version);
    };
    applyWrapped = true;
  };

  const wrapUpdateStatus = () => {
    if (statusWrapped) return;
    const previous = window.onUpdateStatus;
    window.onUpdateStatus = (status) => {
      if (typeof previous === "function") previous(status);
      if (!document.getElementById(OVERLAY_ID)) return;
      const text = String(status || "");
      if (text === "downloading") {
        window.BlossomLoading?.begin?.("update", "Downloading update…");
        if (!document.querySelector(".blossom-progress")) buildProgressView();
      } else if (text === "failed") {
        window.BlossomLoading?.end?.("update");
        markFailed();
        allowApply = false;
      } else if (text.startsWith("done|")) {
        window.BlossomLoading?.setMessage?.("Installing update…");
        markInstalling();
      } else if (text.startsWith("launcher|")) {
        window.BlossomLoading?.end?.("update");
        const parts = text.split("|");
        markLauncherRestart(parts[1] || "", parts[2] || "Blossom.exe");
        allowApply = false;
      } else if (text.startsWith("manual|")) {
        window.BlossomLoading?.end?.("update");
        const parts = text.split("|");
        markManual(parts[1] || "", parts.slice(2).join("|") || "");
        allowApply = false;
      }
    };
    statusWrapped = true;
  };

  // Quiet, non-modal record of the check state (ok | checking | offline).
  // Surfaced as a body data-attribute and on window.BlossomUpdate so a manual
  // "check for updates" action can read it. Never opens a popup on its own.
  let lastCheckState = "ok";
  const setCheckState = (state) => {
    lastCheckState = String(state || "ok");
    if (window.BlossomUpdate) window.BlossomUpdate.lastCheckState = lastCheckState;
    if (document.body) document.body.setAttribute("data-blossom-update-state", lastCheckState);
  };

  const installCheckStateHook = () => {
    let reactHandler = null;
    try {
      Object.defineProperty(window, "onUpdateCheckState", {
        configurable: true,
        enumerable: true,
        get() {
          return (state) => {
            setCheckState(state);
            if (typeof reactHandler === "function") reactHandler(state);
          };
        },
        set(fn) {
          reactHandler = fn;
        },
      });
    } catch {
      window.onUpdateCheckState = (state) => setCheckState(state);
    }
  };

  const installAvailableHook = () => {
    let reactHandler = null;
    try {
      Object.defineProperty(window, "onUpdateAvailable", {
        configurable: true,
        enumerable: true,
        get() {
          return (version, url) => showPrompt(version, url);
        },
        set(fn) {
          reactHandler = fn;
        },
      });
    } catch {
      window.onUpdateAvailable = (version, url) => showPrompt(version, url);
    }
  };

  let bannerObserved = false;
  const observeBanner = () => {
    if (bannerObserved) return;
    bannerObserved = true;
    hideBuiltinBanner();
    // Prefer the shared, RAF-coalesced DOM observer so we don't run a second
    // always-on subtree observer that fires hideBuiltinBanner on every mutation.
    if (window.Blossom?.observeMain) {
      window.Blossom.observeMain(hideBuiltinBanner, 0);
      return;
    }
    const observer = new MutationObserver(() => hideBuiltinBanner());
    const root = document.getElementById("root") || document.body;
    observer.observe(root, { childList: true, subtree: true });
  };

  const boot = () => {
    installAvailableHook();
    installCheckStateHook();
    wrapUpdateStatus();
    observeBanner();
    wrapApplyUpdate();
  };

  window.BlossomUpdate = {
    prompt: showPrompt,
    close: closeModal,
    dismiss: dismissCurrent,
    onDownloadProgress: updateProgress,
    lastCheckState,
    getCheckState: () => lastCheckState,
  };

  const onReady = () => {
    boot();
    wrapApplyUpdate();
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
  window.addEventListener("pywebviewready", onReady);
})();
