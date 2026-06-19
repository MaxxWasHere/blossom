(function () {
  const { observeMain, pageHeaderTitle } = window.Blossom || {};
  const PANEL_ID = "blossom-logs-diagnostics";

  const isSettingsPage = () => pageHeaderTitle() === "Settings & extras";

  const api = () => window.pywebview?.api;

  const formatBytes = (n) => {
    const v = Number(n);
    if (!Number.isFinite(v) || v < 0) return "";
    if (v < 1024) return `${v} B`;
    if (v < 1024 * 1024) return `${(v / 1024).toFixed(1)} KB`;
    return `${(v / (1024 * 1024)).toFixed(2)} MB`;
  };

  const findInsertTarget = () => {
    const headers = Array.from(document.querySelectorAll(".page-header"));
    const header = headers.find(
      (h) => h.querySelector("h2")?.textContent?.trim() === "Settings & extras"
    );
    if (!header?.parentElement) return null;
    const parent = header.parentElement;
    const firstCard = Array.from(parent.children).find((n) => n.classList?.contains("card"));
    return { parent, before: firstCard };
  };

  const mountLogsPanel = (mountTarget) => {
    if (!mountTarget || document.getElementById(PANEL_ID)) return;

    const panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.className = "card";
    panel.style.marginBottom = "16px";
    panel.innerHTML = `
      <div class="card-header">
        <div class="card-icon">📋</div>
        <div>
          <h3>Logs &amp; diagnostics</h3>
          <p>Troubleshoot issues or share logs with support</p>
        </div>
      </div>
      <div style="padding:16px 20px 20px;">
        <p class="form-hint" style="margin:0 0 10px;color:var(--text-muted);line-height:1.5;">
          Blossom writes detailed logs to your AppData folder. The main file is
          <code style="font-family:var(--font-mono,monospace);">logs.txt</code>;
          errors also go to <code style="font-family:var(--font-mono,monospace);">errors.log</code>.
        </p>
        <p class="blsm-logs-path" style="margin:0 0 12px;font-family:var(--font-mono,monospace);font-size:12px;word-break:break-all;color:var(--text-secondary);min-height:2.4em;"></p>
        <p class="blsm-logs-meta" style="margin:0 0 14px;font-size:12px;color:var(--text-muted);min-height:1.2em;"></p>
        <div style="display:flex;flex-wrap:wrap;gap:8px;">
          <button type="button" class="btn btn-secondary" data-open-logs-folder>Open logs folder</button>
          <button type="button" class="btn btn-accent" data-copy-recent-logs>Copy recent logs</button>
        </div>
        <p class="blsm-logs-status" style="margin:10px 0 0;min-height:1.2em;font-size:12px;color:var(--text-muted);"></p>
      </div>
    `;

    const pathEl = panel.querySelector(".blsm-logs-path");
    const metaEl = panel.querySelector(".blsm-logs-meta");
    const statusEl = panel.querySelector(".blsm-logs-status");

    const setStatus = (text, isError) => {
      statusEl.textContent = text || "";
      statusEl.style.color = isError ? "var(--md-sys-color-error, #b3261e)" : "var(--text-muted)";
    };

    const refreshInfo = async () => {
      const bridge = api();
      if (!bridge?.get_log_info) {
        pathEl.textContent = "Logs available after the app finishes loading.";
        return;
      }
      try {
        const info = await bridge.get_log_info();
        if (!info?.ok) {
          pathEl.textContent = info?.error || "Could not read log paths.";
          return;
        }
        pathEl.textContent = info.folder || info.main_log || "";
        const parts = [];
        if (info.main_exists) {
          parts.push(`logs.txt ${formatBytes(info.main_log_bytes)}`);
        } else {
          parts.push("logs.txt (not created yet)");
        }
        if (info.errors_exists) {
          parts.push(`errors.log ${formatBytes(info.errors_log_bytes)}`);
        }
        metaEl.textContent = parts.join(" · ");
      } catch (error) {
        pathEl.textContent = String(error);
      }
    };

    panel.querySelector("[data-open-logs-folder]")?.addEventListener("click", async () => {
      const bridge = api();
      if (!bridge?.open_logs_folder) {
        setStatus("Open logs folder is not available in this build.", true);
        return;
      }
      setStatus("Opening folder…");
      try {
        const result = await bridge.open_logs_folder();
        if (result?.ok === false) {
          setStatus(result.error || "Could not open logs folder.", true);
          return;
        }
        setStatus("Opened logs folder in File Explorer.");
        void refreshInfo();
      } catch (error) {
        setStatus(String(error), true);
      }
    });

    panel.querySelector("[data-copy-recent-logs]")?.addEventListener("click", async () => {
      const bridge = api();
      if (!bridge?.copy_recent_logs) {
        setStatus("Copy recent logs is not available in this build.", true);
        return;
      }
      setStatus("Reading recent log lines…");
      try {
        const result = await bridge.copy_recent_logs(300);
        if (result?.ok === false) {
          setStatus(result.error || "Could not read logs.", true);
          return;
        }
        const text = result.text || "";
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(text);
          setStatus("Copied the last ~300 log lines to your clipboard.");
        } else {
          const ta = document.createElement("textarea");
          ta.value = text;
          ta.style.position = "fixed";
          ta.style.left = "-9999px";
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          ta.remove();
          setStatus("Copied the last ~300 log lines to your clipboard.");
        }
      } catch (error) {
        setStatus(String(error), true);
      }
    });

    panel._blossomRefreshLogs = refreshInfo;

    const { parent, before } = mountTarget;
    const onboarding = document.getElementById("blossom-onboarding-replay");
    const windowPanel = document.getElementById("blossom-window-settings");
    const insertBefore = onboarding?.nextSibling || windowPanel?.nextSibling || before;
    if (insertBefore) parent.insertBefore(panel, insertBefore);
    else parent.appendChild(panel);

    void refreshInfo();
  };

  const sync = () => {
    if (!isSettingsPage()) {
      document.getElementById(PANEL_ID)?.remove();
      return;
    }
    const target = findInsertTarget();
    if (!target) return;
    mountLogsPanel(target);
    document.getElementById(PANEL_ID)?._blossomRefreshLogs?.();
  };

  if (observeMain) observeMain(() => sync(), 0, "Settings & extras logs");
  else {
    sync();
    window.addEventListener("pywebviewready", sync);
  }
})();
