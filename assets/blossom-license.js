(function () {
  const OVERLAY_ID = "blossom-license-overlay";
  // Optional: set your Discord invite to show a "Get a key" button.
  const DISCORD_INVITE = "";

  let lastStatus = null;
  let polledOnce = false;

  const removeOverlay = () => document.getElementById(OVERLAY_ID)?.remove();

  const headingFor = (status) => {
    switch (status.state) {
      case "expired_build":
        return "Beta expired";
      case "offline":
      case "dns_error":
        return "Can't reach the server";
      case "timeout":
        return "Server timed out";
      case "ssl_error":
        return "Secure connection failed";
      case "server_error":
      case "not_found":
        return "Activation server error";
      case "unconfigured":
        return "Activation unavailable";
      case "invalid":
        return "Activation problem";
      default:
        return "Activate Blossom Beta";
    }
  };

  const allowsKeyEntry = (status) =>
    status.state === "unlicensed" || status.state === "invalid" || status.state === "offline";

  const buildOverlay = (status) => {
    const overlay = document.createElement("div");
    overlay.id = OVERLAY_ID;
    overlay.className = "blossom-license-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");

    const msg = status.message || "Enter your beta key to continue.";
    const keyBlock = allowsKeyEntry(status)
      ? `
        <input type="text" class="blsm-license-input" placeholder="BLSM-XXXXX-XXXXX-XXXXX-XXXXX"
               autocomplete="off" spellcheck="false" value="${status.key_masked ? "" : ""}" />
        <div class="blsm-license-actions">
          <button type="button" class="btn btn-accent" data-blsm-activate>Activate</button>
          <button type="button" class="btn btn-secondary" data-blsm-retry>Retry</button>
        </div>`
      : `
        <div class="blsm-license-actions">
          <button type="button" class="btn btn-secondary" data-blsm-retry>Try again</button>
        </div>`;

    const discordBtn = DISCORD_INVITE
      ? `<a class="blsm-license-link" href="${DISCORD_INVITE}" target="_blank" rel="noreferrer">Get a key on Discord</a>`
      : "";

    overlay.innerHTML = `
      <div class="blossom-license-card">
        <div class="blsm-license-logo">Blossom</div>
        <h3>${headingFor(status)}</h3>
        <p class="blsm-license-msg">${msg}</p>
        ${keyBlock}
        <p class="blsm-license-status" aria-live="polite"></p>
        <div class="blsm-license-foot">
          ${discordBtn}
          <button type="button" class="blsm-license-hwid" data-blsm-copy-hwid title="Copy machine ID">
            Machine ID: <code>${(status.hwid || "").slice(0, 12)}…</code>
          </button>
        </div>
      </div>`;

    wire(overlay, status);
    return overlay;
  };

  const setStatusText = (text, isError) => {
    const el = document.querySelector(".blsm-license-status");
    if (!el) return;
    el.textContent = text || "";
    el.classList.toggle("is-error", Boolean(isError));
  };

  const wire = (overlay, status) => {
    const input = overlay.querySelector(".blsm-license-input");

    const activate = async () => {
      const api = window.pywebview?.api;
      if (!api?.submit_license_key) return;
      const key = (input?.value || "").trim();
      if (!key) {
        setStatusText("Enter your key first.", true);
        return;
      }
      setStatusText("Activating…", false);
      overlay.querySelectorAll("button").forEach((b) => (b.disabled = true));
      try {
        const result = await api.submit_license_key(key);
        applyStatus(result);
        if (result && !result.licensed) {
          overlay.querySelectorAll("button").forEach((b) => (b.disabled = false));
        }
      } catch (e) {
        setStatusText("Activation failed. Try again.", true);
        overlay.querySelectorAll("button").forEach((b) => (b.disabled = false));
      }
    };

    const retry = async () => {
      const api = window.pywebview?.api;
      if (!api?.get_license_status) return;
      setStatusText("Checking…", false);
      try {
        const result = await api.get_license_status(true);
        applyStatus(result);
      } catch (e) {
        setStatusText("Still can't reach the server.", true);
      }
    };

    overlay.querySelector("[data-blsm-activate]")?.addEventListener("click", activate);
    overlay.querySelector("[data-blsm-retry]")?.addEventListener("click", retry);
    input?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") activate();
    });
    overlay.querySelector("[data-blsm-copy-hwid]")?.addEventListener("click", () => {
      const hwid = status.hwid || "";
      try {
        navigator.clipboard?.writeText(hwid);
        setStatusText("Machine ID copied.", false);
      } catch {
        setStatusText(hwid, false);
      }
    });
  };

  const applyStatus = (status) => {
    if (!status) return;
    lastStatus = status;
    if (!status.required || status.licensed) {
      removeOverlay();
      return;
    }
    // Locked: (re)build the overlay so messaging matches the latest state.
    removeOverlay();
    document.body.appendChild(buildOverlay(status));
  };

  window.onLicenseStatus = (status) => applyStatus(status);

  const poll = async () => {
    if (polledOnce) return;
    const api = window.pywebview?.api;
    if (!api?.get_license_status) return;
    polledOnce = true;
    try {
      const status = await api.get_license_status(false);
      applyStatus(status);
      // Kick a background refresh that confirms against the server.
      api.get_license_status(true).then(applyStatus).catch(() => {});
    } catch (e) {
      console.error("[BlossomLicense] poll failed", e);
      polledOnce = false;
    }
  };

  window.addEventListener("pywebviewready", poll);
  if (window.pywebview?.api) poll();
})();
