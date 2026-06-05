(function () {
  /** Header chrome only — pin removed (use Settings → Always on top). */

  const blockLegacyPin = () => {
    document.querySelectorAll(".header-bar .pin-btn").forEach((btn) => {
      btn.style.display = "none";
      btn.style.pointerEvents = "none";
      btn.setAttribute("aria-hidden", "true");
      btn.tabIndex = -1;
    });
  };

  const patchHeaderFilter = () => {
    const input = document.querySelector(
      '.header-right input.form-input[placeholder*="Filter"]'
    );
    if (!input) return;
    const wrap = input.closest('div[style*="position"]');
    if (!wrap) return;
    wrap.classList.add("blsm-header-filter");
    input.style.width = "100%";
    input.style.minWidth = "0";
    input.style.maxWidth = "100%";
    input.style.boxSizing = "border-box";
    const icon = wrap.querySelector('div[style*="position: absolute"]');
    if (icon) {
      icon.style.left = "10px";
      icon.style.pointerEvents = "none";
    }
  };

  const tagFilterMenus = () => {
    document.querySelectorAll(".header-right div[style]").forEach((el) => {
      const style = el.getAttribute("style") || "";
      const z = style.replace(/\s/g, "");
      if (
        (z.includes("zIndex:1000") || z.includes("zIndex:1e3")) &&
        (z.includes("position:absolute") || z.includes("position:fixed"))
      ) {
        el.classList.add("blossom-header-filter-menu");
      }
    });
  };

  const removeSidePills = () => {
    document.getElementById("blsm-dock")?.remove();
    document.getElementById("blsm-panel")?.remove();
    document.querySelector(".main-content")?.classList.remove("blsm-has-dock");
  };

  const run = () => {
    removeSidePills();
    blockLegacyPin();
    patchHeaderFilter();
    tagFilterMenus();
  };

  document.addEventListener(
    "click",
    (event) => {
      if (event.target.closest?.(".header-bar .pin-btn")) {
        event.preventDefault();
        event.stopPropagation();
        event.stopImmediatePropagation();
      }
    },
    true
  );

  const boot = () => {
    run();
    if (window.Blossom?.observeMain) {
      window.Blossom.observeMain(run, 400);
    } else {
      const root =
        document.querySelector(".main-content") ||
        document.getElementById("root");
      if (root) {
        const obs = new MutationObserver(run);
        obs.observe(root, { childList: true, subtree: true });
      }
      window.addEventListener("pywebviewready", run);
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
