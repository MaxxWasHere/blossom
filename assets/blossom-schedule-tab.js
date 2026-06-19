(function () {

  "use strict";



  const TAB_LABEL = "Macro Schedule";

  const SECTION_LABEL = "Schedule";

  const PAGE_ID = "blsm-schedule-page";

  const SIDEBAR_ID = "blsm-sidebar-macro-schedule";

  const SECTION_LABEL_ID = "blsm-sidebar-schedule-label";

  const SECTION_GROUP_ID = "blsm-sidebar-schedule-group";



  const { setPageAttr, scheduleUiSync } = window.Blossom || {};



  let active = false;

  let trackHandle = null;

  let bootAttempts = 0;

  let navObserver = null;

  let docObserver = null;



  const mainEl = () =>

    document.querySelector(".page-content") || document.querySelector(".main-content");



  const itemLabel = (item) => (item?.textContent || "").replace(/\s+/g, " ").trim().toLowerCase();



  const findMacroStatusItem = () => {

    const items = document.querySelectorAll(".sidebar-item");

    for (const item of items) {

      const text = itemLabel(item);

      if (text === "macro status" || text.endsWith("macro status")) return item;

    }

    return null;

  };



  const findInsertAnchor = (nav) => {
    const groups = nav.querySelectorAll(":scope > .sidebar-group");
    for (const group of groups) {
      const label = group.querySelector(":scope > .sidebar-section-label");
      if (label?.textContent.trim().toLowerCase() === "macro") return group;
    }

    const labels = [...nav.querySelectorAll(":scope > .sidebar-section-label")];
    const macroLabel = labels.find((l) => l.textContent.trim().toLowerCase() === "macro");
    if (macroLabel) {
      if (macroLabel.parentElement?.classList.contains("sidebar-group")) {
        return macroLabel.parentElement;
      }
      let el = macroLabel.nextElementSibling;
      while (el && !el.classList.contains("sidebar-group")) el = el.nextElementSibling;
      if (el) return el;
    }

    const status = findMacroStatusItem();
    return status?.closest(".sidebar-group") || null;
  };



  const scheduleIcon = () => window.BlossomIcons?.svg("calendar") || "";

  const wipIcon = () => window.BlossomIcons?.svg("warning") || "";



  const buildSidebarItemMarkup = () =>

    `<span class="icon">${scheduleIcon()}</span>` +

    `<span class="blsm-sidebar-item-text">` +

    `<span class="blsm-sidebar-item-label">${TAB_LABEL}</span>` +

    `<span class="blsm-sidebar-item-hint">W.I.P. — may not work</span>` +

    `</span>` +

    `<span class="blsm-sidebar-wip-badge">W.I.P.</span>`;



  const buildWipBannerMarkup = () =>

    `<div class="blsm-schedule-wip-banner" role="status" aria-live="polite">` +

    `<span class="blsm-schedule-wip-banner-icon" aria-hidden="true">${wipIcon()}</span>` +

    `<div class="blsm-schedule-wip-banner-copy">` +

    `<strong>Work in progress — experimental</strong>` +

    `<p>Macro Schedule is unfinished and may not run correctly. Profiles, timelines, and macro integration can break or do nothing. Use at your own risk while we build it out.</p>` +

    `</div></div>`;



  const ensureSidebarItem = () => {

    const existing = document.getElementById(SIDEBAR_ID);

    const label = document.getElementById(SECTION_LABEL_ID);

    if (existing?.isConnected && label?.isConnected) {

      existing.classList.add("blsm-sidebar-wip");

      existing.setAttribute("title", "W.I.P. — experimental; may not work correctly");

      existing.innerHTML = buildSidebarItemMarkup();

      label.innerHTML = `${SECTION_LABEL} <span class="blsm-sidebar-wip-chip">W.I.P.</span>`;

      existing.closest(".sidebar-group")?.classList.add("blsm-sidebar-wip-group");

      return existing;

    }



    document.getElementById(SECTION_LABEL_ID)?.remove();

    document.getElementById(SECTION_GROUP_ID)?.remove();

    existing?.remove();



    const nav = document.querySelector(".sidebar-nav");

    if (!nav) return null;



    const sectionLabel = document.createElement("div");

    sectionLabel.id = SECTION_LABEL_ID;

    sectionLabel.className = "sidebar-section-label";

    sectionLabel.innerHTML = `${SECTION_LABEL} <span class="blsm-sidebar-wip-chip">W.I.P.</span>`;



    const group = document.createElement("div");

    group.id = SECTION_GROUP_ID;

    group.className = "sidebar-group blsm-sidebar-wip-group";

    const item = document.createElement("div");

    item.id = SIDEBAR_ID;

    item.className = "sidebar-item blsm-sidebar-wip";

    item.setAttribute("role", "button");

    item.setAttribute("tabindex", "0");

    item.setAttribute("title", "W.I.P. — experimental; may not work correctly");

    item.innerHTML = buildSidebarItemMarkup();

    group.appendChild(sectionLabel);

    group.appendChild(item);

    bindSidebarItem(item);



    const anchor = findInsertAnchor(nav);

    if (anchor) {

      anchor.insertAdjacentElement("afterend", group);

    } else {

      nav.appendChild(group);

    }



    return item;

  };



  const clearScheduleActive = () => {

    document.getElementById(SIDEBAR_ID)?.classList.remove("active", "is-active");

  };



  const setScheduleActive = () => {

    document.querySelectorAll(".sidebar-item.active, .sidebar-item.is-active").forEach((el) => {

      el.classList.remove("active", "is-active");

    });

    document.getElementById(SIDEBAR_ID)?.classList.add("active", "is-active");

  };



  const teardown = () => {

    const hadPage = !!document.getElementById(PAGE_ID);

    if (!active && !hadPage) {

      clearScheduleActive();

      document.documentElement.classList.remove("blsm-schedule-page-active");

      return;

    }

    active = false;

    document.documentElement.classList.remove("blsm-schedule-page-active");

    clearScheduleActive();

    window.BlossomMacroSchedule?.exitEditMode?.();

    trackHandle?.destroy?.();

    trackHandle = null;

    document.getElementById(PAGE_ID)?.remove();

  };



  const mountPage = () => {

    const main = mainEl();

    if (!main) return false;



    active = true;

    document.documentElement.classList.add("blsm-schedule-page-active");



    let page = document.getElementById(PAGE_ID);

    if (!page) {

      page = document.createElement("div");

      page.id = PAGE_ID;

      page.className = "blsm-schedule-page";

      page.innerHTML = `

        <div class="blsm-schedule-wip-banner-wrap">

          ${buildWipBannerMarkup()}

        </div>

        <div class="page-header">

          <h2>${TAB_LABEL} <span class="blsm-schedule-wip-title-chip">W.I.P.</span></h2>

          <p>Experimental automation planner — profiles and timelines are under active development and may not work when the macro runs.</p>

        </div>

        <div class="blsm-schedule-mount"></div>`;

      main.appendChild(page);

    } else if (!page.isConnected) {

      main.appendChild(page);

    }



    if (!page.querySelector(".blsm-schedule-wip-banner")) {

      const wrap = document.createElement("div");

      wrap.className = "blsm-schedule-wip-banner-wrap";

      wrap.innerHTML = buildWipBannerMarkup();

      page.insertBefore(wrap, page.firstElementChild);

    }



    const header = page.querySelector(".page-header h2");

    if (header && !header.querySelector(".blsm-schedule-wip-title-chip")) {

      header.insertAdjacentHTML(

        "beforeend",

        ` <span class="blsm-schedule-wip-title-chip">W.I.P.</span>`

      );

    }



    const headerNote = page.querySelector(".page-header p");

    if (headerNote) {

      headerNote.textContent =

        "Experimental automation planner — profiles and timelines are under active development and may not work when the macro runs.";

    }



    main.setAttribute("data-blossom-page", TAB_LABEL);

    setPageAttr?.();

    scheduleUiSync?.();



    const mount = page.querySelector(".blsm-schedule-mount");

    if (mount && window.BlossomMacroSchedule?.mountTrack && !mount.dataset.blsmMounted) {

      mount.dataset.blsmMounted = "1";

      void window.BlossomMacroSchedule.mountTrack(mount).then((handle) => {

        trackHandle = handle;

      });

    }



    window.dispatchEvent(new CustomEvent("blossom-schedule-tab-open"));

    return true;

  };



  const openTab = (event) => {

    if (event) {

      event.preventDefault();

      event.stopPropagation();

    }

    if (!ensureSidebarItem()) return;

    setScheduleActive();

    if (!mountPage()) {

      active = false;

      clearScheduleActive();

      document.documentElement.classList.remove("blsm-schedule-page-active");

    }

  };



  const onNavCapture = (event) => {

    const target = event.target;

    if (!(target instanceof Element)) return;

    const item = target.closest(".sidebar-item");

    if (!item || item.id === SIDEBAR_ID) return;

    if (active || document.getElementById(PAGE_ID)) {

      teardown();

      scheduleUiSync?.();

    }

  };



  const bindSidebarItem = (item) => {

    if (!item || item.dataset.blsmScheduleBound === "1") return;

    item.dataset.blsmScheduleBound = "1";

    item.addEventListener("click", openTab);

    item.addEventListener("keydown", (e) => {

      if (e.key === "Enter" || e.key === " ") {

        e.preventDefault();

        openTab(e);

      }

    });

  };



  const bindNavDelegation = (nav) => {

    if (!nav || nav.dataset.blsmScheduleNavBound === "1") return;

    nav.dataset.blsmScheduleNavBound = "1";

    nav.addEventListener("click", onNavCapture, true);

  };



  const boot = () => {

    const item = ensureSidebarItem();

    if (!item) return false;

    const nav = document.querySelector(".sidebar-nav, .sidebar");

    bindNavDelegation(nav);

    return true;

  };



  const ensureNavObserver = () => {

    const nav = document.querySelector(".sidebar-nav");

    if (!nav) return false;

    if (navObserver) return true;

    navObserver = new MutationObserver(() => {

      if (!document.getElementById(SIDEBAR_ID)?.isConnected) boot();

    });

    navObserver.observe(nav, { childList: true, subtree: true });

    return true;

  };



  const ensureDocObserver = () => {

    if (docObserver) return;

    docObserver = new MutationObserver(() => {

      if (!document.getElementById(SIDEBAR_ID)?.isConnected) boot();

    });

    docObserver.observe(document.documentElement, { childList: true, subtree: true });

  };



  const scheduleBootRetries = () => {

    if (boot()) {

      ensureNavObserver();

      return;

    }

    if (bootAttempts >= 40) return;

    bootAttempts += 1;

    const delay = bootAttempts < 8 ? 50 : bootAttempts < 20 ? 120 : 250;

    window.setTimeout(scheduleBootRetries, delay);

  };



  const scheduleBoot = () => {

    bootAttempts = 0;

    scheduleBootRetries();

    ensureNavObserver();

    ensureDocObserver();

  };



  window.BlossomScheduleTab = {

    open: () => openTab(),

    teardown,

    TAB_LABEL,

    SECTION_LABEL,

  };



  if (document.readyState === "loading") {

    document.addEventListener("DOMContentLoaded", scheduleBoot);

  } else {

    scheduleBoot();

  }

  window.addEventListener("pywebviewready", () => {

    window.setTimeout(scheduleBoot, 0);

    window.setTimeout(scheduleBoot, 120);

  });

})();

