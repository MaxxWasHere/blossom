(function () {
  const { observeMain, pageHeaderTitle } = window.Blossom || {};

  const PAGE_CHILD =
    ":scope > .page-header, :scope > .card, :scope > .changelog-item, :scope > #blsm-cal-hub, :scope > .blsm-mouse-cal-card";

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

  const setStagger = (main) => {
    pageItems(main).forEach((el, i) => {
      el.style.setProperty("--blsm-stagger", String(i));
    });
  };

  const runPageEnter = (main) => {
    if (!main || !pageItems(main).length) return;
    setStagger(main);
    main.classList.remove("blsm-page-enter");
    void main.offsetWidth;
    main.classList.add("blsm-page-enter");
  };

  let lastPage = "";
  let lastItemCount = 0;

  const onPageChange = () => {
    const title = pageHeaderTitle?.() || "";
    if (!title || title === lastPage) return;
    lastPage = title;
    const main = mainEl();
    runPageEnter(main);
    lastItemCount = main ? pageItems(main).length : 0;
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
    const count = pageItems(main).length;
    if (!count) return;
    if (count !== lastItemCount || !main.classList.contains("blsm-page-enter")) {
      lastItemCount = count;
      runPageEnter(main);
    }
  };

  if (observeMain) observeMain(tick, 0);
  else {
    tick();
    window.addEventListener("pywebviewready", tick);
  }

  if (window.Blossom) window.Blossom.runPageEnter = runPageEnter;
})();
