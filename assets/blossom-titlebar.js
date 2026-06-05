(function () {
  const ICON_MINIMIZE =
    '<svg class="titlebar-glyph" viewBox="0 0 10 10" aria-hidden="true"><path d="M1 5h8" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>';
  const ICON_CLOSE =
    '<svg class="titlebar-glyph" viewBox="0 0 10 10" aria-hidden="true"><path d="M2 2l6 6M8 2L2 8" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>';

  const api = () => window.pywebview && window.pywebview.api;

  const callFirst = async (names) => {
    const bridge = api();
    if (!bridge) return false;
    for (const constName of names) {
      if (typeof bridge[constName] === "function") {
        await bridge[constName]();
        return true;
      }
    }
    return false;
  };

  const queryMaximized = async () => {
    const bridge = api();
    if (bridge && typeof bridge.is_window_maximized === "function") {
      try {
        return !!(await bridge.is_window_maximized());
      } catch (_) {
        /* fall through */
      }
    }
    return (
      window.outerHeight >= screen.availHeight - 4 &&
      window.outerWidth >= screen.availWidth - 4
    );
  };

  const syncChromeState = async () => {
    const maxed = await queryMaximized();
    document.documentElement.classList.toggle("blsm-window-maximized", maxed);
    if (window.BlossomWindow && typeof window.BlossomWindow.syncMaximized === "function") {
      window.BlossomWindow.syncMaximized(maxed);
    }
  };

  const stripExtraCaptionButtons = (titlebar) => {
    titlebar
      .querySelectorAll(".titlebar-btn.resize, .titlebar-btn.maximize, [data-blsm-resize-btn]")
      .forEach((el) => el.remove());
    const controls = titlebar.querySelector(".titlebar-controls");
    if (!controls) return;
    controls.querySelectorAll(".titlebar-btn").forEach((btn) => {
      if (!btn.classList.contains("minimize") && !btn.classList.contains("close")) {
        btn.remove();
      }
    });
  };

  const bindControls = (titlebar) => {
    stripExtraCaptionButtons(titlebar);
    const actions = [
      {
        className: "minimize",
        label: "Minimize",
        icon: ICON_MINIMIZE,
        methods: ["minimize_window", "minimize", "window_minimize"],
      },
      {
        className: "close",
        label: "Close",
        icon: ICON_CLOSE,
        methods: ["close_window", "close", "quit_app", "window_close"],
      },
    ];

    let dragRegion = titlebar.querySelector(".titlebar-drag-region");
    if (!dragRegion) {
      dragRegion = document.createElement("div");
      dragRegion.className = "titlebar-drag-region pywebview-drag-region";
      dragRegion.setAttribute("aria-hidden", "true");
      titlebar.prepend(dragRegion);
    } else {
      dragRegion.classList.add("pywebview-drag-region");
    }

    const controls = titlebar.querySelectorAll(
      ".titlebar-controls .titlebar-btn.minimize, .titlebar-controls .titlebar-btn.close"
    );
    controls.forEach((button, index) => {
      const action = actions[index];
      if (!action) return;
      button.classList.add(action.className);
      button.setAttribute("aria-label", action.label);
      button.setAttribute("title", action.label);
      if (!button.querySelector(".titlebar-glyph")) {
        button.innerHTML = action.icon;
      }
      if (button.dataset.blsmTitlebarBound === "true") return;
      button.dataset.blsmTitlebarBound = "true";
      button.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        try {
          await callFirst(action.methods);
          setTimeout(syncChromeState, 80);
        } catch (error) {
          console.warn(`Titlebar ${action.className} failed`, error);
        }
      });
    });

    return controls.length > 0;
  };

  const createTitlebar = (frame) => {
    const titlebar = document.createElement("header");
    titlebar.className = "titlebar blsm-titlebar coteab-injected-titlebar";
    titlebar.setAttribute("role", "banner");
    titlebar.innerHTML = `
      <div class="titlebar-drag-region pywebview-drag-region" aria-hidden="true"></div>
      <div class="titlebar-brand">
        <img class="titlebar-icon" src="./blossom.png" width="16" height="16" alt="" decoding="async" />
        <span class="titlebar-title">Blossom</span>
      </div>
      <div class="titlebar-spacer" aria-hidden="true"></div>
      <div class="titlebar-controls">
        <button type="button" class="titlebar-btn minimize" aria-label="Minimize"></button>
        <button type="button" class="titlebar-btn close" aria-label="Close"></button>
      </div>
    `;
    frame.insertBefore(titlebar, frame.firstChild);
    return titlebar;
  };

  const setupTitlebar = () => {
    const frame = document.querySelector(".window-frame");
    if (!frame) return false;
    let titlebar = frame.querySelector(".titlebar, .blsm-titlebar");
    if (!titlebar) {
      titlebar = createTitlebar(frame);
    } else {
      titlebar.classList.add("blsm-titlebar", "coteab-injected-titlebar");
    }
    const ok = bindControls(titlebar);
    if (ok) syncChromeState();
    return ok;
  };

  const boot = () => {
    if (!setupTitlebar()) {
      const observer = new MutationObserver(() => {
        if (setupTitlebar()) observer.disconnect();
      });
      observer.observe(document.documentElement, { childList: true, subtree: true });
    }
    window.addEventListener("resize", () => {
      clearTimeout(boot._resizeTimer);
      boot._resizeTimer = setTimeout(syncChromeState, 60);
    });
  };

  window.BlossomTitlebar = { syncChromeState, setupTitlebar };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
  window.addEventListener("pywebviewready", () => {
    boot();
    syncChromeState();
  });
})();
