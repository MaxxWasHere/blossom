(function () {
  const OVERLAY_ID = "blossom-license-overlay";
  const DISCORD_INVITE = "https://discord.gg/tv5T9uh2Ef";

  let lastStatus = null;
  let bridgeReady = false;
  let pollTimer = null;

  const removeOverlay = () => document.getElementById(OVERLAY_ID)?.remove();

  const isLicensed = (status) =>
    status && (!status.required || status.licensed || status.state === "not_required");

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
    status.state === "unlicensed" ||
    status.state === "invalid" ||
    status.state === "offline" ||
    status.state === "wrong_machine";

  const hwidDisplay = (status, expanded) => {
    const hwid = status.hwid || "";
    if (!hwid) return "Machine ID unavailable";
    if (expanded) return hwid;
    return hwid.length > 16 ? `${hwid.slice(0, 16)}…` : hwid;
  };

  const buildOverlay = (status) => {
    const overlay = document.createElement("div");
    overlay.id = OVERLAY_ID;
    overlay.className = "blossom-license-overlay";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-labelledby", "blsm-license-title");

    const msg = status.message || "Enter your beta key to continue.";
    const showKey = allowsKeyEntry(status);

    const discordBlock = DISCORD_INVITE
      ? `<div class="blsm-license-discord-block">
          <a class="btn btn-secondary blsm-license-discord" href="${DISCORD_INVITE}" target="_blank" rel="noreferrer">
            Get beta access on Discord
          </a>
          <p class="blsm-license-discord-hint">Beta keys are issued to Discord members with beta access.</p>
        </div>`
      : "";

    const keyBlock = showKey
      ? `<div class="blsm-license-key-block">
          <label class="blsm-license-label" for="blsm-license-key">Beta key</label>
          <input id="blsm-license-key" type="text" class="blsm-license-input" placeholder="BLSM-XXXXX-XXXXX-XXXXX-XXXXX"
                 autocomplete="off" spellcheck="false" />
          <div class="blsm-license-actions">
            <button type="button" class="btn btn-accent blsm-license-btn" data-blsm-activate>Activate</button>
            <button type="button" class="btn btn-secondary blsm-license-btn" data-blsm-retry>Retry</button>
          </div>
        </div>`
      : `<div class="blsm-license-actions blsm-license-actions--solo">
          <button type="button" class="btn btn-secondary blsm-license-btn" data-blsm-retry>Try again</button>
        </div>`;

    overlay.innerHTML = `
      <div class="blossom-license-card m3e-container-enter">
        <div class="blsm-license-logo-row">
          <img class="blsm-license-icon" src="./blossom.png" alt="" width="40" height="40" onerror="this.style.display='none'" />
          <span class="blsm-license-logo">Blossom Beta</span>
        </div>
        <h3 id="blsm-license-title">${headingFor(status)}</h3>
        <p class="blsm-license-msg">${msg}</p>
        ${discordBlock}
        ${keyBlock}
        <div class="blsm-license-activating" data-blsm-activating hidden aria-hidden="true">
          <div class="blsm-license-spinner" data-blsm-spinner></div>
          <span>Activating…</span>
        </div>
        <p class="blsm-license-status" aria-live="polite"></p>
        <div class="blsm-license-foot">
          <button type="button" class="blsm-license-hwid" data-blsm-toggle-hwid title="Show full machine ID">
            Machine ID: <code data-blsm-hwid-text>${hwidDisplay(status, false)}</code>
          </button>
          <button type="button" class="blsm-license-copy" data-blsm-copy-hwid>Copy</button>
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

  const setActivating = (on) => {
    const block = document.querySelector("[data-blsm-activating]");
    const spinner = document.querySelector("[data-blsm-activating] [data-blsm-spinner]");
    if (block) {
      block.hidden = !on;
      block.setAttribute("aria-hidden", on ? "false" : "true");
    }
    if (on && spinner && window.BlossomM3Loading) {
      window.BlossomM3Loading.mount(spinner);
    } else if (!on && spinner && window.BlossomM3Loading) {
      window.BlossomM3Loading.unmount(spinner);
    }
  };

  const wire = (overlay, status) => {
    const input = overlay.querySelector(".blsm-license-input");
    let hwidExpanded = false;

    const activate = async () => {
      const api = window.pywebview?.api;
      if (!api?.submit_license_key) return;
      const key = (input?.value || "").trim();
      if (!key) {
        setStatusText("Enter your key first.", true);
        input?.focus();
        return;
      }
      setStatusText("", false);
      setActivating(true);
      overlay.querySelectorAll("button").forEach((b) => (b.disabled = true));
      if (input) input.disabled = true;
      try {
        const result = await api.submit_license_key(key);
        setActivating(false);
        applyStatus(result);
        if (result && !result.licensed) {
          overlay.querySelectorAll("button").forEach((b) => (b.disabled = false));
          if (input) input.disabled = false;
        }
      } catch (e) {
        setActivating(false);
        setStatusText("Activation failed. Try again.", true);
        overlay.querySelectorAll("button").forEach((b) => (b.disabled = false));
        if (input) input.disabled = false;
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
    overlay.querySelector("[data-blsm-toggle-hwid]")?.addEventListener("click", () => {
      hwidExpanded = !hwidExpanded;
      const code = overlay.querySelector("[data-blsm-hwid-text]");
      if (code) code.textContent = hwidDisplay(status, hwidExpanded);
    });

    if (input) {
      requestAnimationFrame(() => input.focus());
    }
  };

  const notifyLicensed = (status) => {
    window.dispatchEvent(
      new CustomEvent("blossom-licensed", { detail: status || lastStatus })
    );
  };

  const applyStatus = (status) => {
    if (!status) return;
    lastStatus = status;
    if (isLicensed(status)) {
      removeOverlay();
      notifyLicensed(status);
      return;
    }
    removeOverlay();
    document.body.appendChild(buildOverlay(status));
  };

  window.onLicenseStatus = (status) => applyStatus(status);
  window.BlossomLicense = {
    isLicensed: () => isLicensed(lastStatus),
    getStatus: () => lastStatus,
    whenReady: (cb) => {
      if (isLicensed(lastStatus)) {
        cb(lastStatus);
        return;
      }
      const handler = (e) => {
        window.removeEventListener("blossom-licensed", handler);
        cb(e.detail);
      };
      window.addEventListener("blossom-licensed", handler);
    },
  };

  const poll = async () => {
    const api = window.pywebview?.api;
    if (!api?.get_license_status) return;
    try {
      const status = await api.get_license_status(false);
      applyStatus(status);
      if (!isLicensed(status)) {
        api.get_license_status(true).then(applyStatus).catch(() => {});
      }
    } catch (e) {
      console.error("[BlossomLicense] poll failed", e);
    }
  };

  const onBridgeReady = () => {
    if (bridgeReady) return;
    bridgeReady = true;
    if (pollTimer) clearInterval(pollTimer);
    void poll();
  };

  const waitForBridge = () => {
    if (window.pywebview?.api?.get_license_status) {
      onBridgeReady();
      return;
    }
    pollTimer = setInterval(() => {
      if (window.pywebview?.api?.get_license_status) onBridgeReady();
    }, 120);
    setTimeout(() => {
      if (pollTimer) clearInterval(pollTimer);
    }, 15000);
  };

  window.addEventListener("pywebviewready", waitForBridge);
  if (window.pywebview?.api) waitForBridge();
})();
