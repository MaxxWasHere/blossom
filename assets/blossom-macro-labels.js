(function () {
  const api = () => window.pywebview?.api;

  const display = (key, label) =>
    window.BlossomHotkeys?.displayHotkey?.(key, label) ||
    (label || (key ? String(key) : "No bind"));

  let lastLabelKey = "";

  const labelText = (running, hotkeys) => {
    if (running) {
      const stop = display(hotkeys.stop, hotkeys.stop_display);
      return hotkeys.stop ? `Stop (${stop})` : "Stop macro";
    }
    const start = display(hotkeys.start, hotkeys.start_display);
    return hotkeys.start ? `Start (${start})` : "Start macro";
  };

  const iconMarkup = (running) => {
    const name = running ? "stop" : "play";
    return window.BlossomIcons?.svg(name) || (running ? "■" : "▶");
  };

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
    const text = labelText(running, hotkeys);
    const key = `${running}|${text}`;
    if (key === lastLabelKey && btn.querySelector(".blossom-macro-btn-label")) return;
    lastLabelKey = key;

    btn.innerHTML = `${iconMarkup(running)}<span class="blossom-macro-btn-label">${text}</span>`;
  };

  window.BlossomMacroLabels = { refresh: refreshHeaderButton };

  window.addEventListener("pywebviewready", refreshHeaderButton);

  if (window.Blossom?.observeMain) {
    window.Blossom.observeMain(refreshHeaderButton, 400);
  } else {
    refreshHeaderButton();
  }
})();
