(function () {
  const PHASES = ["starting", "update", "runtime", "launch", "ready"];
  const DEFAULT_MESSAGE = "Starting Blossom…";

  let displayPct = 0;
  let targetPct = 0;
  let indeterminate = true;
  let animFrame = 0;

  const $ = (sel) => document.querySelector(sel);

  const formatBytes = (bytes) => {
    const n = Number(bytes) || 0;
    if (n <= 0) return "0 MB";
    const mb = n / (1024 * 1024);
    if (mb >= 1024) return (mb / 1024).toFixed(2) + " GB";
    if (mb >= 10) return mb.toFixed(0) + " MB";
    return mb.toFixed(1) + " MB";
  };

  const phaseNodes = () =>
    Array.from(document.querySelectorAll("[data-blsm-phase]"));

  const setPhase = (phase) => {
    const key = String(phase || "starting").trim().toLowerCase();
    const idx = PHASES.indexOf(key);
    phaseNodes().forEach((node) => {
      const nodePhase = node.getAttribute("data-blsm-phase");
      const nodeIdx = PHASES.indexOf(nodePhase);
      node.classList.toggle("is-active", nodePhase === key);
      node.classList.toggle("is-done", idx >= 0 && nodeIdx >= 0 && nodeIdx < idx);
    });
  };

  const setMessage = (message) => {
    const msg = String(message || "").trim();
    const el = $(".blossom-loading-message");
    if (el && msg) el.textContent = msg;
  };

  const setVersion = (version) => {
    const el = $("[data-blsm-version]");
    if (el) el.textContent = String(version || "").trim().toUpperCase();
  };

  const setSpinnerVisible = (visible) => {
    const spinner = $("[data-blsm-spinner]");
    const bar = $("[data-blsm-progress]");
    if (spinner) spinner.hidden = !visible;
    if (bar) bar.hidden = visible;
    if (window.BlossomM3Loading) window.BlossomM3Loading.sync(spinner, visible);
  };

  const progressTrack = () => $(".blossom-loading-progress-track");

  const syncProgress = (reset) => {
    const track = progressTrack();
    if (!track || !window.BlossomM3Progress) return;
    if (indeterminate) {
      window.BlossomM3Progress.update(track, { indeterminate: true, reset: !!reset });
      return;
    }
    window.BlossomM3Progress.update(track, {
      indeterminate: false,
      percent: targetPct,
    });
  };

  const renderProgressMeta = (downloaded, total, reset) => {
    const bar = $("[data-blsm-progress]");
    const pctEl = $(".blsm-loading-pct");
    const bytesEl = $(".blsm-loading-bytes");
    if (!bar) return;

    if (indeterminate || total <= 0) {
      bar.setAttribute("data-state", "indeterminate");
      syncProgress(reset);
      if (pctEl) {
        pctEl.textContent = downloaded > 0 ? formatBytes(downloaded) : "Working…";
      }
      if (bytesEl) bytesEl.textContent = "";
      return;
    }

    bar.setAttribute("data-state", "determinate");
    syncProgress();
    if (pctEl) pctEl.textContent = Math.round(displayPct) + "%";
    if (bytesEl) {
      bytesEl.textContent = `${formatBytes(downloaded)} / ${formatBytes(total)}`;
    }
  };

  const tickProgress = () => {
    const bar = $("[data-blsm-progress]");
    if (!bar) return;

    if (indeterminate) {
      syncProgress();
      animFrame = requestAnimationFrame(tickProgress);
      return;
    }

    const delta = targetPct - displayPct;
    if (Math.abs(delta) > 0.08) {
      displayPct += delta * 0.14;
    } else {
      displayPct = targetPct;
    }
    syncProgress();
    animFrame = requestAnimationFrame(tickProgress);
  };

  const setProgress = (downloaded, total) => {
    const wasIndeterminate = indeterminate;
    indeterminate = false;
    setSpinnerVisible(false);
    const dl = Number(downloaded) || 0;
    const tot = Number(total) || 0;
    if (tot > 0) {
      const next = Math.max(0, Math.min(100, (dl / tot) * 100));
      if (wasIndeterminate) {
        targetPct = next;
        displayPct = 0;
      } else {
        targetPct = next;
      }
    }
    renderProgressMeta(dl, tot, wasIndeterminate);
  };

  const setIndeterminate = (active) => {
    indeterminate = !!active;
    if (indeterminate) {
      targetPct = 0;
      displayPct = 0;
      setSpinnerVisible(true);
    } else {
      setSpinnerVisible(false);
    }
    renderProgressMeta(0, 0, true);
  };

  const showError = (message) => {
    const box = $("[data-blsm-error]");
    const msg = String(message || "").trim();
    setMessage("Something went wrong");
    setPhase("error");
    if (box) {
      box.textContent = msg;
      box.hidden = !msg;
    }
    setIndeterminate(true);
  };

  const clearError = () => {
    const box = $("[data-blsm-error]");
    if (box) {
      box.textContent = "";
      box.hidden = true;
    }
  };

  const fadeOut = (delayMs) => {
    const ms = Math.max(0, Number(delayMs) || 480);
    const frame = $(".bootstrap-window");
    if (frame) frame.classList.add("is-closing");
    return new Promise((resolve) => setTimeout(resolve, ms));
  };

  const wireTitlebar = () => {
    document.querySelectorAll("[data-blsm-minimize]").forEach((btn) => {
      btn.addEventListener("click", () => {
        window.pywebview?.api?.minimize?.();
      });
    });
    document.querySelectorAll("[data-blsm-close]").forEach((btn) => {
      btn.addEventListener("click", () => {
        window.pywebview?.api?.close?.();
      });
    });
  };

  const boot = () => {
    wireTitlebar();
    setPhase("starting");
    setMessage(DEFAULT_MESSAGE);
    setIndeterminate(true);
    if (!animFrame) tickProgress();
  };

  window.BootstrapSplash = {
    setMessage: (msg) => {
      clearError();
      setMessage(msg);
    },
    setVersion,
    setProgress,
    setIndeterminate,
    setPhase,
    showError,
    fadeOut,
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }

  window.addEventListener("pywebviewready", () => {
    const bridge = window.pywebview?.api;
    if (!bridge?.get_config) return;
    Promise.resolve(bridge.get_config())
      .then((cfg) => window.BlossomThemeBoot?.applyFromConfig?.(cfg))
      .catch(() => {});
  });
})();
