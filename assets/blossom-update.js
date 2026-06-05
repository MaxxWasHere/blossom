(function () {
  const OVERLAY_ID = "blossom-update-overlay";
  let pending = null;
  let allowApply = false;
  let applyWrapped = false;
  let statusWrapped = false;

  const corners = `
    <div class="corner-bracket tl"></div>
    <div class="corner-bracket tr"></div>
    <div class="corner-bracket bl"></div>
    <div class="corner-bracket br"></div>`;

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

  const runApply = async () => {
    const api = window.pywebview?.api;
    if (!api?.apply_update || !pending) return;
    allowApply = true;
    setStatus("Downloading update…");
    const cancelBtn = document.querySelector("[data-blossom-update-cancel]");
    const updateBtn = document.querySelector("[data-blossom-update-confirm]");
    if (cancelBtn) cancelBtn.disabled = true;
    if (updateBtn) updateBtn.disabled = true;
    try {
      await api.apply_update(pending.url, pending.version);
    } catch (error) {
      console.error("[BlossomUpdate] apply failed:", error);
      setStatus("Update failed. Try again or download from GitHub.");
      if (cancelBtn) cancelBtn.disabled = false;
      if (updateBtn) updateBtn.disabled = false;
      allowApply = false;
    }
  };

  const showPrompt = (version, url) => {
    if (!version || !url) return;
    if (pending?.version === version && pending?.url === url && document.getElementById(OVERLAY_ID)) {
      return;
    }
    pending = { version: String(version), url: String(url) };
    hideBuiltinBanner();

    closeModal();
    const overlay = document.createElement("div");
    overlay.id = OVERLAY_ID;
    overlay.className = "blossom-update-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.innerHTML = `
      <div class="blossom-update-dialog">
        ${corners}
        <h3>Update available</h3>
        <p>
          Blossom <strong>${pending.version}</strong> is available.
          Update now? The app will close and restart with the new version.
          Your settings in <code>%LOCALAPPDATA%\\Blossom\\</code> are kept.
        </p>
        <p class="blossom-update-status"></p>
        <div class="blossom-update-actions">
          <button type="button" class="btn btn-secondary" data-blossom-update-cancel>Cancel</button>
          <button type="button" class="btn btn-accent" data-blossom-update-confirm>Update</button>
        </div>
      </div>`;

    overlay.querySelector("[data-blossom-update-cancel]")?.addEventListener("click", () => {
      allowApply = false;
      closeModal();
      hideBuiltinBanner();
    });

    overlay.querySelector("[data-blossom-update-confirm]")?.addEventListener("click", () => {
      runApply();
    });

    overlay.addEventListener("click", (event) => {
      if (event.target === overlay) {
        allowApply = false;
        closeModal();
        hideBuiltinBanner();
      }
    });

    document.body.appendChild(overlay);
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
      if (text === "downloading") setStatus("Downloading update…");
      else if (text === "failed") {
        setStatus("Update failed. You can try again or download from GitHub.");
        document.querySelector("[data-blossom-update-cancel]")?.removeAttribute("disabled");
        document.querySelector("[data-blossom-update-confirm]")?.removeAttribute("disabled");
      } else if (text.startsWith("done|")) {
        setStatus("Installing… restarting Blossom.");
      }
    };
    statusWrapped = true;
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

  const observeBanner = () => {
    const observer = new MutationObserver(() => hideBuiltinBanner());
    const root = document.getElementById("root") || document.body;
    observer.observe(root, { childList: true, subtree: true });
    hideBuiltinBanner();
  };

  const boot = () => {
    installAvailableHook();
    wrapUpdateStatus();
    observeBanner();
    wrapApplyUpdate();
  };

  window.BlossomUpdate = { prompt: showPrompt, close: closeModal };

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
