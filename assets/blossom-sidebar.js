(function () {
  const wrapNavGroups = () => {
    const nav = document.querySelector(".sidebar-nav");
    if (!nav || nav.dataset.blossomGrouped === "1") return;

    const nodes = [...nav.children].filter(
      (n) =>
        n.classList?.contains("sidebar-section-label") || n.classList?.contains("sidebar-item")
    );

    if (!nodes.length) return;

    const frag = document.createDocumentFragment();
    let group = null;

    nodes.forEach((node) => {
      if (node.classList.contains("sidebar-section-label")) {
        if (group) frag.appendChild(group);
        frag.appendChild(node);
        group = document.createElement("div");
        group.className = "sidebar-group";
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
  };

  let navObserver = null;
  const boot = () => {
    wrapNavGroups();
    const nav = document.querySelector(".sidebar-nav");
    if (!nav) return;
    // Disconnect any prior observer before re-binding (boot re-runs on
    // pywebviewready) so observers can't accumulate on stale nav nodes.
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
