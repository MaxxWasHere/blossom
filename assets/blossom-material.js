(function () {
  const ACCORDION_HINT = "Click to view/edit coordinates";
  const MACRO_CAL_PAGE = "Macro Calibrations";
  const LEGACY_ARROW = /^[\s▲▼▽△▾▴]*$/;
  const { observeMain, wrapMorphShell, lockMorphDisplay, isMorphOpen, pageHeaderTitle } = window.Blossom || {};
  const bound = new WeakSet();

  const onMacroCalPage = () =>
    document.documentElement.classList.contains("blsm-page-macro-calibrations") ||
    pageHeaderTitle?.() === MACRO_CAL_PAGE;

  const isMacroCalLegacyCard = (card) => {
    if (!onMacroCalPage()) return false;
    if (card.id === "blsm-cal-hub" || card.classList.contains("blsm-mouse-cal-card")) return false;
    if (card.classList.contains("blsm-cal-preset-card")) return false;
    const sub = card.querySelector(":scope > .card-header p, .card-header p");
    if (sub?.textContent?.includes(ACCORDION_HINT)) return true;
    return card.classList.contains("blsm-cal-legacy-hidden") || card.classList.contains("blsm-native-cal");
  };

  const isAccordion = (card) => {
    if (isMacroCalLegacyCard(card)) return false;
    if (card.classList.contains("blsm-mouse-cal-card")) return false;
    const title = card.querySelector(":scope > .card-header h3")?.textContent?.trim() || "";
    if (title === "Mouse Action Calibration Requirements") return false;
    const p = card.querySelector(":scope > .card-header p");
    if (p?.textContent?.includes(ACCORDION_HINT)) return true;
    const head = card.querySelector(":scope > .card-header");
    return !!head && (head.style.cursor === "pointer" || head.getAttribute("style")?.includes("cursor"));
  };

  const getBody = (card) =>
    card.querySelector(":scope > .blsm-morph-shell") ||
    card.querySelector(":scope > div:not(.card-header)") ||
    null;

  const getChevronSlot = (header) => {
    const kids = [...header.children];
    for (let i = kids.length - 1; i >= 0; i -= 1) {
      const el = kids[i];
      if (el.classList?.contains("card-icon")) continue;
      if (el.querySelector?.("h3")) continue;
      return el;
    }
    return null;
  };

  const purgeLegacyArrow = (slot) => {
    if (!slot) return;
    const text = (slot.textContent || "").trim();
    if (LEGACY_ARROW.test(text) || text === "▲" || text === "▼") {
      slot.textContent = "";
    }
    slot.querySelectorAll("svg.blsm-md-chevron, .blsm-md-chevron-btn").forEach((n) => n.remove());
    slot.classList.add("blsm-md-chevron-host");
  };

  const syncExpanded = (card) => {
    const body = getBody(card);
    const open = isMorphOpen ? isMorphOpen(body) : !!(body && body.offsetParent !== null && body.getBoundingClientRect().height > 6);
    card.classList.toggle("is-expanded", open);
    if (wrapMorphShell && body) {
      wrapMorphShell(body);
      lockMorphDisplay?.(body);
    }
  };

  const patchAccordion = (card) => {
    if (!isAccordion(card)) return;
    card.classList.add("blsm-md-card", "blsm-md-accordion");
    const header = card.querySelector(":scope > .card-header");
    if (!header) return;
    const sub = header.querySelector("p");
    if (sub) sub.classList.add("blsm-md-sub-hide");
    purgeLegacyArrow(getChevronSlot(header));
    const body = getBody(card);
    if (body && wrapMorphShell) wrapMorphShell(body);
    syncExpanded(card);
  };

  const bindAccordion = (card) => {
    if (bound.has(card)) return;
    const header = card.querySelector(":scope > .card-header");
    if (!header) return;
    bound.add(card);

    const refresh = () => {
      patchAccordion(card);
      syncExpanded(card);
    };

    header.addEventListener("click", () => {
      queueMicrotask(refresh);
      requestAnimationFrame(refresh);
    });

    const body = getBody(card);
    if (body) {
      new MutationObserver(refresh).observe(body, {
        attributes: true,
        attributeFilter: ["style", "class"],
        childList: true,
        subtree: true,
      });
    }

    new MutationObserver(refresh).observe(header, {
      childList: true,
      subtree: true,
      characterData: true,
    });
  };

  const enhance = () => {
    const scope = document.querySelector(".page-content, .main-content");
    if (!scope) return;
    scope.querySelectorAll(".card").forEach((card) => {
      if (card.id === "blsm-cal-hub") {
        card.classList.add("blsm-md-card");
        return;
      }
      if (isMacroCalLegacyCard(card)) return;
      card.classList.add("blsm-md-card");
      if (isAccordion(card)) {
        patchAccordion(card);
        bindAccordion(card);
      }
    });
  };

  document.documentElement.classList.add("blsm-material-ui");

  if (observeMain) observeMain(enhance, 0);
  else {
    enhance();
    window.addEventListener("pywebviewready", enhance);
  }
})();
