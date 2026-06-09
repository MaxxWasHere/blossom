(function () {
  const CAPTION_SELECTORS = ".titlebar-btn.minimize, .titlebar-btn.close";
  const RESIZE_EDGES = [
    "top",
    "right",
    "bottom",
    "left",
    "top-left",
    "top-right",
    "bottom-left",
    "bottom-right",
  ];

  const api = () => window.pywebview?.api;

  const syncMaximized = (maxed) => {
    if (typeof maxed !== "boolean") return;
    document.documentElement.classList.toggle("blsm-window-maximized", maxed);
  };

  const stripMaximizeButtons = () => {
    document.querySelectorAll(".titlebar-btn.maximize, [data-blsm-resize-btn]").forEach((el) => {
      el.remove();
    });
  };

  const ensureResizeHandles = () => {
    const frame = document.querySelector(".window-frame");
    if (!frame || frame.dataset.blsmResizeReady === "1") return;

    let root = frame.querySelector(".blsm-window-resize-root");
    if (!root) {
      root = document.createElement("div");
      root.className = "blsm-window-resize-root";
      root.setAttribute("aria-hidden", "true");
      RESIZE_EDGES.forEach((edge) => {
        const handle = document.createElement("div");
        handle.className = "blsm-window-resize";
        handle.dataset.blsmWindowResize = edge;
        handle.title = "Resize window";
        handle.addEventListener("pointerdown", (event) => {
          event.preventDefault();
          event.stopPropagation();
          const bridge = api();
          if (bridge?.start_window_resize) {
            void bridge.start_window_resize(edge);
          }
        });
        root.appendChild(handle);
      });
      frame.appendChild(root);
    }

    frame.dataset.blsmResizeReady = "1";
  };

  const run = () => {
    stripMaximizeButtons();
    ensureResizeHandles();
  };

  let observed = false;
  const boot = () => {
    run();
    if (observed) return;
    if (window.Blossom?.observeMain) {
      observed = true;
      window.Blossom.observeMain(run, 400);
    } else {
      const root = document.querySelector(".window-frame") || document.documentElement;
      const obs = new MutationObserver(run);
      obs.observe(root, { childList: true, subtree: true });
      observed = true;
    }
  };

  window.BlossomWindow = { syncMaximized, ensureResizeHandles, run };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
  window.addEventListener("pywebviewready", boot);
})();
