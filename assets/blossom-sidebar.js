(function () {
  const collectNavNodes = (nav) => {
    const nodes = [];
    [...nav.children].forEach((child) => {
      if (child.classList?.contains("sidebar-section-label")) {
        nodes.push(child);
      } else if (child.classList?.contains("sidebar-item")) {
        nodes.push(child);
      } else if (child.classList?.contains("sidebar-group")) {
        [...child.children].forEach((item) => {
          if (
            item.classList?.contains("sidebar-section-label") ||
            item.classList?.contains("sidebar-item")
          ) {
            nodes.push(item);
          }
        });
      }
    });
    return nodes;
  };

  const motionAllowed = () =>
    document.documentElement.classList.contains("blsm-motion-on") &&
    !document.documentElement.classList.contains("blsm-reduce-motion");

  const playNavExit = (el) => {
    if (!el || !motionAllowed()) return;
    el.classList.remove("blsm-m3e-nav-enter");
    el.classList.add("blsm-m3e-nav-exit");
    el.addEventListener(
      "animationend",
      () => el.classList.remove("blsm-m3e-nav-exit"),
      { once: true }
    );
  };

  const playNavEnter = (el) => {
    if (!el || !motionAllowed()) return;
    el.classList.remove("blsm-m3e-nav-exit");
    el.classList.remove("blsm-m3e-nav-enter");
    void el.offsetWidth;
    el.classList.add("blsm-m3e-nav-enter");
    el.addEventListener(
      "animationend",
      () => el.classList.remove("blsm-m3e-nav-enter"),
      { once: true }
    );
  };

  const bindNavSelectionMotion = (nav) => {
    if (!nav || nav.dataset.blsmNavMotion === "1") return;
    nav.dataset.blsmNavMotion = "1";
    nav.addEventListener(
      "click",
      (event) => {
        const item = event.target?.closest?.(".sidebar-item");
        if (!item || !motionAllowed()) return;
        const prev = nav.querySelector(".sidebar-item.active, .sidebar-item.is-active");
        if (prev && prev !== item) playNavExit(prev);
        window.requestAnimationFrame(() => {
          window.requestAnimationFrame(() => {
            if (
              item.classList.contains("active") ||
              item.classList.contains("is-active")
            ) {
              playNavEnter(item);
            }
          });
        });
      },
      true
    );
  };

  const wrapNavGroups = () => {
    const nav = document.querySelector(".sidebar-nav");
    if (!nav || nav.dataset.blossomGrouped === "1") return;

    const nodes = collectNavNodes(nav);

    if (!nodes.length) return;

    const frag = document.createDocumentFragment();
    let group = null;

    nodes.forEach((node) => {
      if (node.classList.contains("sidebar-section-label")) {
        if (group) frag.appendChild(group);
        group = document.createElement("div");
        group.className = "sidebar-group";
        group.appendChild(node);
        return;
      }
      if (!group) {
        group = document.createElement("div");
        group.className = "sidebar-group";
      }
      group.appendChild(node);
    });

    if (group) frag.appendChild(group);

    nav.replaceChildren(frag);
    nav.dataset.blossomGrouped = "1";
    [...nav.querySelectorAll(":scope > .sidebar-group")].forEach((group, index) => {
      group.style.setProperty("--blsm-nav-stagger", String(index));
    });
    bindNavSelectionMotion(nav);
  };

  let navObserver = null;
  const boot = () => {
    wrapNavGroups();
    const nav = document.querySelector(".sidebar-nav");
    if (!nav) return;
    bindNavSelectionMotion(nav);
    if (navObserver) navObserver.disconnect();
    navObserver = new MutationObserver(() => {
      if (nav.dataset.blossomGrouped !== "1" && nav.querySelector(".sidebar-section-label")) {
        wrapNavGroups();
      }
    });
    navObserver.observe(nav, { childList: true });
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  window.addEventListener("pywebviewready", () => {
    const nav = document.querySelector(".sidebar-nav");
    if (nav) delete nav.dataset.blossomGrouped;
    boot();
  });
})();
