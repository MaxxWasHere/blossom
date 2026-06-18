(function () {
  const { observeMain } = window.Blossom || {};
  const docEl = document.documentElement;
  const RIPPLE_SEL =
    ".btn, .calibration-btn, .blossom-dropdown-trigger, .sidebar-item:not(.active):not(.is-active)";
  const NAV_SEL = ".sidebar-item.active, .sidebar-item.is-active";

  const motionAllowed = () =>
    docEl.classList.contains("blsm-motion-on") &&
    !docEl.classList.contains("blsm-reduce-motion");

  const syncExpressiveClass = () => {
    docEl.classList.toggle("blsm-expressive-on", motionAllowed());
  };

  const spawnRipple = (el, event) => {
    if (!motionAllowed() || !el || event.pointerType === "mouse" && event.button !== 0) return;
    if (getComputedStyle(el).position === "static") el.style.position = "relative";
    const rect = el.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2.2;
    const ripple = document.createElement("span");
    ripple.className = "blsm-m3e-ripple";
    ripple.style.width = `${size}px`;
    ripple.style.height = `${size}px`;
    ripple.style.left = `${event.clientX - rect.left - size / 2}px`;
    ripple.style.top = `${event.clientY - rect.top - size / 2}px`;
    el.appendChild(ripple);
    ripple.addEventListener("animationend", () => ripple.remove(), { once: true });
  };

  let rippleBound = false;
  const bindRipples = () => {
    if (rippleBound || !motionAllowed()) return;
    rippleBound = true;
    document.addEventListener(
      "pointerdown",
      (e) => {
        if (!motionAllowed()) return;
        const el = e.target?.closest?.(RIPPLE_SEL);
        if (el) spawnRipple(el, e);
      },
      { passive: true }
    );
  };

  let lastActiveNav = null;
  const pulseNavSelection = () => {
    if (!motionAllowed()) return;
    const active = document.querySelector(NAV_SEL);
    if (!active || active === lastActiveNav) return;
    lastActiveNav = active;
    active.classList.remove("blsm-m3e-nav-enter");
    void active.offsetWidth;
    active.classList.add("blsm-m3e-nav-enter");
    active.addEventListener(
      "animationend",
      () => active.classList.remove("blsm-m3e-nav-enter"),
      { once: true }
    );
  };

  let lastMacroBtn = null;
  const pulseMacroButton = () => {
    if (!motionAllowed()) return;
    const btn = document.querySelector(".header-bar .btn-start, .header-bar .btn-stop");
    if (!btn || btn === lastMacroBtn) return;
    lastMacroBtn = btn;
    btn.classList.remove("blsm-m3e-macro-morph");
    void btn.offsetWidth;
    btn.classList.add("blsm-m3e-macro-morph");
    btn.addEventListener(
      "animationend",
      () => btn.classList.remove("blsm-m3e-macro-morph"),
      { once: true }
    );
  };

  let dropdownObserver = null;
  const watchDropdowns = () => {
    if (dropdownObserver || !motionAllowed()) return;
    dropdownObserver = new MutationObserver((records) => {
      for (const rec of records) {
        if (rec.type !== "attributes" || rec.attributeName !== "class") continue;
        const menu = rec.target;
        if (!menu.classList?.contains("blossom-dropdown-menu--portal")) continue;
        const open = menu.classList.contains("is-open");
        menu.classList.toggle("blsm-m3e-menu-open", open);
        if (!open) menu.classList.remove("blsm-m3e-menu-open");
      }
    });
    dropdownObserver.observe(document.body, {
      attributes: true,
      attributeFilter: ["class"],
      subtree: true,
    });
  };

  const tick = () => {
    syncExpressiveClass();
    pulseNavSelection();
    pulseMacroButton();
  };

  syncExpressiveClass();
  bindRipples();
  watchDropdowns();
  tick();

  if (observeMain) observeMain(tick, 0);
  else window.addEventListener("pywebviewready", tick);

  window.addEventListener("pywebviewready", () => {
    lastActiveNav = null;
    lastMacroBtn = null;
    syncExpressiveClass();
    tick();
  });

  const motionObserver = new MutationObserver(syncExpressiveClass);
  motionObserver.observe(docEl, { attributes: true, attributeFilter: ["class"] });
})();
