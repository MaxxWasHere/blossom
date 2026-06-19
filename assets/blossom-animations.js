(function () {
  const { observeMain, pageHeaderTitle } = window.Blossom || {};

  const PAGE_CHILD =
    ":scope > .page-header, :scope > .card, :scope > .changelog-item, :scope > #blsm-cal-hub, :scope > .blsm-mouse-cal-card, :scope > .blsm-macro-hub, :scope > .blsm-macro-grid, :scope > .blsm-macro-grid-row";

  const STAGGER_STEP_MS = 55;
  const STAGGER_BASE_MS = 80;
  const MAX_STAGGER = 12;

  const mainEl = () =>
    document.querySelector(".page-content") ||
    document.querySelector(".main-content");

  const onMacroCalPage = () =>
    document.documentElement.classList.contains("blsm-page-macro-calibrations") ||
    pageHeaderTitle?.() === "Macro Calibrations";

  const pageItems = (main) => {
    const items = [...main.querySelectorAll(PAGE_CHILD)].filter(Boolean);
    if (!onMacroCalPage()) return items;
    return items.filter(
      (el) =>
        el.classList.contains("page-header") ||
        el.id === "blsm-cal-hub" ||
        el.classList.contains("blsm-mouse-cal-card") ||
        el.classList.contains("blsm-cal-preset-card") ||
        el.classList.contains("info-banner")
    );
  };

  const sidebarIndexForTitle = (title) => {
    const items = [...document.querySelectorAll(".sidebar-item, .sidebar .nav-item")];
    const idx = items.findIndex((el) => {
      const t = el.textContent?.trim() || "";
      return title && (t === title || t.includes(title) || title.includes(t));
    });
    return idx >= 0 ? idx : 0;
  };

  let lastNavIndex = 0;

  const setStagger = (main) => {
    pageItems(main).forEach((el, i) => {
      el.style.setProperty("--blsm-stagger", String(Math.min(i, MAX_STAGGER)));
    });
  };

  const runPageEnter = (main, axis) => {
    if (!main || !pageItems(main).length) return;
    setStagger(main);
    main.classList.remove("blsm-page-enter", "blsm-axis-forward", "blsm-axis-back");
    void main.offsetWidth;
    main.classList.add("blsm-page-enter");
    if (axis === "back") main.classList.add("blsm-axis-back");
    else if (axis === "forward") main.classList.add("blsm-axis-forward");
  };

  let lastPage = "";
  let lastStaggerKey = "";

  const onPageChange = () => {
    const title = pageHeaderTitle?.() || "";
    if (!title || title === lastPage) return;
    const navIdx = sidebarIndexForTitle(title);
    const axis = navIdx < lastNavIndex ? "back" : navIdx > lastNavIndex ? "forward" : "forward";
    lastNavIndex = navIdx;
    lastPage = title;
    lastStaggerKey = "";
    runPageEnter(mainEl(), axis);
  };

  const tagNativeCalFields = () => {
    document
      .querySelectorAll(".blsm-native-cal.is-expanded .coord-input-group")
      .forEach((el, i) => {
        el.style.setProperty("--blsm-i", String(i));
      });
  };

  const tick = () => {
    onPageChange();
    tagNativeCalFields();
    const main = mainEl();
    if (!main) return;
    const key = `${lastPage}:${pageItems(main).length}`;
    if (key !== lastStaggerKey) {
      lastStaggerKey = key;
      setStagger(main);
    }
  };

  if (observeMain) observeMain(tick, 0);
  else {
    tick();
    window.addEventListener("pywebviewready", tick);
  }

  if (window.Blossom) {
    window.Blossom.runPageEnter = runPageEnter;
    window.Blossom.m3Stagger = { base: STAGGER_BASE_MS, step: STAGGER_STEP_MS };
  }
})();
