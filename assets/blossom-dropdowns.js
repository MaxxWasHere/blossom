(function () {
  const ROOT_SEL = "select.form-input";
  const MARK = "data-blossom-dropdown";
  const MENU_Z = 12000;

  const chevronSvg =
    '<svg class="blossom-dropdown-chevron" viewBox="0 0 16 16" aria-hidden="true"><path d="M4 6l4 4 4-4" fill="none" stroke="currentColor" stroke-width="1.25" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  const debounce =
    window.Blossom?.debounce ||
    ((fn, ms) => {
      let t;
      return (...a) => {
        clearTimeout(t);
        t = setTimeout(() => fn(...a), ms);
      };
    });

  const pageTitle = () =>
    document.querySelector(".page-header h2")?.textContent?.trim() || "";

  const skipEnhance = (select) => {
    if (!select) return true;
    if (select.getAttribute("data-blossom-native") === "1") return true;
    if (pageTitle() === "Auras") return true;
    if (select.closest(".blossom-aura-scroll, [data-blossom-native-selects]")) return true;
    return false;
  };

  const closeAll = (except) => {
    document.querySelectorAll(".blossom-dropdown.is-open").forEach((wrap) => {
      if (wrap !== except) {
        wrap.classList.remove("is-open");
        const trigger = wrap.querySelector(".blossom-dropdown-trigger");
        if (trigger) trigger.setAttribute("aria-expanded", "false");
        if (wrap._portalMenu) wrap._portalMenu.classList.remove("is-open");
      }
    });
  };

  const positionMenu = (trigger, menu) => {
    const r = trigger.getBoundingClientRect();
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const w = Math.max(r.width, 120);
    const left = Math.max(8, Math.min(r.left, vw - w - 8));
    const spaceBelow = vh - r.bottom - 12;
    const spaceAbove = r.top - 12;
    const openUp = spaceBelow < 140 && spaceAbove > spaceBelow;

    menu.style.position = "fixed";
    menu.style.left = `${left}px`;
    menu.style.width = `${w}px`;
    menu.style.right = "auto";
    menu.style.zIndex = String(MENU_Z);
    menu.style.maxHeight = `${Math.min(240, Math.max(openUp ? spaceAbove : spaceBelow, 80))}px`;

    if (openUp) {
      menu.style.top = "auto";
      menu.style.bottom = `${vh - r.top + 4}px`;
      menu.dataset.placement = "up";
    } else {
      menu.style.top = `${r.bottom + 4}px`;
      menu.style.bottom = "auto";
      menu.dataset.placement = "down";
    }
  };

  let repositionRaf = 0;
  const repositionOpenMenus = () => {
    if (repositionRaf) return;
    repositionRaf = requestAnimationFrame(() => {
      repositionRaf = 0;
      document.querySelectorAll(".blossom-dropdown.is-open").forEach((wrap) => {
        const trigger = wrap.querySelector(".blossom-dropdown-trigger");
        const menu = wrap._portalMenu;
        if (trigger && menu) positionMenu(trigger, menu);
      });
    });
  };

  window.addEventListener("scroll", repositionOpenMenus, true);
  window.addEventListener("resize", repositionOpenMenus);

  const enhanceSelect = (select) => {
    if (!select || select.getAttribute(MARK) === "done" || select.closest(".blossom-dropdown")) return;
    if (skipEnhance(select)) return;

    select.setAttribute(MARK, "done");
    select.classList.add("blossom-dropdown-native");

    const parent = select.parentElement;
    const wrap = document.createElement("div");
    wrap.className = "blossom-dropdown";
    if (parent && getComputedStyle(parent).position === "static") {
      parent.style.position = "relative";
    }

    parent.insertBefore(wrap, select);
    wrap.appendChild(select);

    const trigger = document.createElement("button");
    trigger.type = "button";
    trigger.className = "blossom-dropdown-trigger";
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");

    const label = document.createElement("span");
    label.className = "blossom-dropdown-label";
    trigger.appendChild(label);
    trigger.insertAdjacentHTML("beforeend", chevronSvg);

    const menu = document.createElement("div");
    menu.className = "blossom-dropdown-menu blossom-dropdown-menu--portal";
    menu.setAttribute("role", "listbox");

    const list = document.createElement("div");
    list.className = "blossom-dropdown-list";
    menu.appendChild(list);

    wrap.appendChild(trigger);
    document.body.appendChild(menu);
    wrap._portalMenu = menu;

    const syncLabel = () => {
      const opt = select.options[select.selectedIndex];
      label.textContent = opt ? opt.textContent : "";
      list.querySelectorAll(".blossom-dropdown-option").forEach((btn) => {
        btn.classList.toggle("is-selected", btn.dataset.value === select.value);
      });
    };

    const buildOptions = () => {
      list.innerHTML = "";
      Array.from(select.options).forEach((opt) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "blossom-dropdown-option";
        btn.dataset.value = opt.value;
        btn.setAttribute("role", "option");
        btn.textContent = opt.textContent;
        if (opt.value === select.value) btn.classList.add("is-selected");
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          if (select.value !== opt.value) {
            select.value = opt.value;
            select.dispatchEvent(new Event("change", { bubbles: true }));
            select.dispatchEvent(new Event("input", { bubbles: true }));
          }
          syncLabel();
          wrap.classList.remove("is-open");
          menu.classList.remove("is-open");
          trigger.setAttribute("aria-expanded", "false");
        });
        list.appendChild(btn);
      });
    };

    const open = () => {
      buildOptions();
      closeAll(wrap);
      positionMenu(trigger, menu);
      wrap.classList.add("is-open");
      menu.classList.add("is-open");
      trigger.setAttribute("aria-expanded", "true");
      const selected = list.querySelector(".blossom-dropdown-option.is-selected");
      if (selected) selected.scrollIntoView({ block: "nearest", behavior: "auto" });
    };

    const close = () => {
      wrap.classList.remove("is-open");
      menu.classList.remove("is-open");
      trigger.setAttribute("aria-expanded", "false");
    };

    trigger.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (wrap.classList.contains("is-open")) close();
      else open();
    });

    select.addEventListener("change", syncLabel);

    const stopWheel = (e) => e.stopPropagation();
    menu.addEventListener("wheel", stopWheel, { passive: true });

    syncLabel();
  };

  const scan = () => {
    document.querySelectorAll(".blossom-dropdown").forEach((wrap) => {
      if (!wrap.querySelector("select")) {
        wrap._portalMenu?.remove();
        wrap.remove();
      }
    });
    document.querySelectorAll(ROOT_SEL).forEach((select) => {
      if (select.closest(".blossom-dropdown")) return;
      if (select.getAttribute(MARK) !== "done") enhanceSelect(select);
    });
  };

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".blossom-dropdown") && !e.target.closest(".blossom-dropdown-menu--portal")) {
      closeAll(null);
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeAll(null);
  });

  const runScan = debounce(scan, 280);

  const markAurasPage = () => {
    if (pageTitle() !== "Auras") return;
    document.querySelectorAll(".page-content select.form-input, .main-content select.form-input").forEach((s) => {
      s.setAttribute("data-blossom-native", "1");
    });
  };

  const boot = () => {
    const run = () => {
      runScan();
      markAurasPage();
    };
    if (window.Blossom?.observeMain) {
      window.Blossom.observeMain(run, 0);
    } else {
      run();
      window.addEventListener("pywebviewready", run);
    }
  };

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
