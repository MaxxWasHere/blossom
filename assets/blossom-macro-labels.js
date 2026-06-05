(function () {
  const api = () => window.pywebview?.api;

  const display = (key, label) =>
    window.BlossomHotkeys?.displayHotkey?.(key, label) ||
    (label || (key ? String(key) : "No bind"));

  const refreshHeaderButton = async () => {
    const btn = document.querySelector(".header-bar .btn-start, .header-bar .btn-stop");
    if (!btn) return;

    let hotkeys = { start: "", stop: "", start_display: "No bind", stop_display: "No bind" };
    if (api()?.get_macro_hotkeys) {
      try {
        hotkeys = await api().get_macro_hotkeys();
      } catch {}
    }

    const running = btn.classList.contains("btn-stop");
    if (running) {
      const stop = display(hotkeys.stop, hotkeys.stop_display);
      btn.textContent = hotkeys.stop ? `■ Stop (${stop})` : "■ Stop macro";
    } else {
      const start = display(hotkeys.start, hotkeys.start_display);
      btn.textContent = hotkeys.start ? `▶ Start (${start})` : "▶ Start macro";
    }
  };

  window.BlossomMacroLabels = { refresh: refreshHeaderButton };

  window.addEventListener("pywebviewready", refreshHeaderButton);

  if (window.Blossom?.observeMain) {
    window.Blossom.observeMain(refreshHeaderButton, 400);
  } else {
    refreshHeaderButton();
  }
})();
