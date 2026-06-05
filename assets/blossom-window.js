(function () {
  const CAPTION_SELECTORS = ".titlebar-btn.minimize, .titlebar-btn.close";

  const syncMaximized = (maxed) => {
    if (typeof maxed !== "boolean") return;
    document.documentElement.classList.toggle("blsm-window-maximized", maxed);
  };

  const isResizeCaptionButton = (btn) => {
    if (!btn || !btn.classList) return false;
    if (btn.classList.contains("resize")) return true;
    if (btn.dataset.blsmResizeBtn === "true") return true;
    const label = `${btn.getAttribute("aria-label") || ""} ${btn.getAttribute("title") || ""}`.toLowerCase();
    return /\bresize\b/.test(label) && !/\brestore\b/.test(label);
  };

  const removeResizeUi = () => {
    document
      .querySelectorAll(
        ".blsm-window-resize-root, .blsm-window-resize, [data-blsm-window-resize], [data-blsm-resize-btn]"
      )
      .forEach((el) => el.remove());

    document.querySelectorAll(".titlebar, .coteab-injected-titlebar, .blsm-titlebar").forEach((titlebar) => {
      titlebar.querySelectorAll(".titlebar-btn").forEach((btn) => {
        if (isResizeCaptionButton(btn)) btn.remove();
        if (btn.classList.contains("maximize")) btn.remove();
      });

      const controls = titlebar.querySelector(".titlebar-controls");
      if (controls) {
        controls.querySelectorAll(".titlebar-btn").forEach((btn) => {
          const allowed = btn.classList.contains("minimize") || btn.classList.contains("close");
          if (!allowed) btn.remove();
        });
      }

      const dragRegion = titlebar.querySelector(".titlebar-drag-region");
      if (dragRegion) {
        const cap = titlebar.querySelectorAll(CAPTION_SELECTORS).length;
        if (cap > 0) {
          const w = getComputedStyle(titlebar.querySelector(".titlebar-btn") || titlebar).width;
          const px = parseFloat(w);
          dragRegion.style.right = Number.isFinite(px) ? `${cap * px}px` : `${cap * 40}px`;
        }
      }
    });
  };

  const boot = () => {
    removeResizeUi();
    if (window.Blossom?.observeMain) {
      window.Blossom.observeMain(removeResizeUi, 400);
    } else {
      const root = document.querySelector(".window-frame") || document.documentElement;
      const obs = new MutationObserver(removeResizeUi);
      obs.observe(root, { childList: true, subtree: true });
    }
  };

  window.BlossomWindow = { syncMaximized, removeResizeUi };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
  window.addEventListener("pywebviewready", boot);
})();
