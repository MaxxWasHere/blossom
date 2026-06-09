/*
 * Blossom command palette.
 * Ctrl/Cmd+K opens an overlay that searches every sidebar destination plus a
 * few quick actions (start/stop macro, import config, pin window, jump to
 * Appearance). Destinations are read live from the rendered sidebar so the list
 * always matches what the app actually shows. The toolbar "Filter index" box is
 * repurposed into a launcher: focusing it opens the palette.
 *
 * Behaviour: substring/fuzzy filter, up/down to move, Enter or click to run,
 * Esc to close. Themed with the app's CSS variables. No always-on polling — it
 * only builds its list when opened.
 */
(function () {
  "use strict";

  const OVERLAY_ID = "blsm-cmdk";
  const I = (name) => (window.BlossomIcons ? window.BlossomIcons.svg(name) : "");

  let overlay = null;
  let inputEl = null;
  let listEl = null;
  let items = [];      // currently filtered+rendered items
  let active = 0;

  // --- sources ------------------------------------------------------------

  const navDestinations = () => {
    const out = [];
    document.querySelectorAll(".sidebar-item").forEach((el) => {
      // Skip locked/disabled rows.
      if (el.style.pointerEvents === "none" || el.getAttribute("aria-disabled") === "true") return;
      const label = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (!label) return;
      out.push({
        kind: "Go to",
        label,
        icon: el.querySelector(".icon")?.innerHTML || I("location"),
        run: () => el.click(),
      });
    });
    return out;
  };

  const findButtonByText = (re) => {
    const btns = document.querySelectorAll("button, .btn");
    for (const b of btns) {
      if (re.test((b.textContent || "").trim())) return b;
    }
    return null;
  };

  const actions = () => {
    const list = [];
    const macroBtn = findButtonByText(/^(?:[^\s]*\s*)?(Start macro|Stop macro)$/);
    if (macroBtn) {
      const running = /Stop macro/.test(macroBtn.textContent);
      list.push({
        kind: "Action",
        label: running ? "Stop macro" : "Start macro",
        icon: running ? I("stop") : I("play"),
        run: () => macroBtn.click(),
      });
    }
    const importBtn = document.querySelector(".btn-import");
    if (importBtn) {
      list.push({ kind: "Action", label: "Import config", icon: I("box"), run: () => importBtn.click() });
    }
    const pinBtn = document.querySelector(".pin-btn");
    if (pinBtn) {
      const pinned = pinBtn.classList.contains("active");
      list.push({
        kind: "Action",
        label: pinned ? "Unpin window from top" : "Pin window on top",
        icon: I("pin"),
        run: () => pinBtn.click(),
      });
    }
    list.push({
      kind: "Action",
      label: "Open Appearance (themes)",
      icon: I("palette"),
      run: () => window.Blossom?.goToTab?.("Appearance"),
    });
    return list;
  };

  const buildSource = () => [...navDestinations(), ...actions()];

  // --- fuzzy match --------------------------------------------------------

  // Returns a score (higher = better) or -1 for no match. Substring beats
  // scattered-letter (subsequence) matches.
  const score = (q, text) => {
    if (!q) return 0;
    const t = text.toLowerCase();
    const idx = t.indexOf(q);
    if (idx !== -1) return 100 - idx;
    let qi = 0;
    for (let i = 0; i < t.length && qi < q.length; i++) {
      if (t[i] === q[qi]) qi++;
    }
    return qi === q.length ? 1 : -1;
  };

  // --- rendering ----------------------------------------------------------

  const render = () => {
    const q = inputEl.value.trim().toLowerCase();
    const source = buildSource();
    items = source
      .map((it) => ({ it, s: score(q, it.label) }))
      .filter((x) => x.s >= 0)
      .sort((a, b) => b.s - a.s)
      .map((x) => x.it);

    if (active >= items.length) active = items.length - 1;
    if (active < 0) active = 0;

    if (!items.length) {
      listEl.innerHTML = `<div class="blsm-cmdk-empty">No matches</div>`;
      return;
    }
    listEl.innerHTML = items
      .map(
        (it, i) => `
        <div class="blsm-cmdk-item ${i === active ? "is-active" : ""}" data-i="${i}" role="option" aria-selected="${i === active}">
          <span class="blsm-cmdk-ico">${it.icon || ""}</span>
          <span class="blsm-cmdk-label">${escapeHtml(it.label)}</span>
          <span class="blsm-cmdk-kind">${it.kind}</span>
        </div>`
      )
      .join("");
    const activeEl = listEl.querySelector(".blsm-cmdk-item.is-active");
    if (activeEl) activeEl.scrollIntoView({ block: "nearest" });
  };

  const escapeHtml = (s) =>
    String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  const execActive = () => {
    const it = items[active];
    if (!it) return;
    close();
    setTimeout(() => {
      try {
        it.run();
      } catch (err) {
        console.warn("[Blossom] command failed:", err);
      }
    }, 0);
  };

  // --- open / close -------------------------------------------------------

  const ensureOverlay = () => {
    if (overlay) return;
    overlay = document.createElement("div");
    overlay.id = OVERLAY_ID;
    overlay.hidden = true;
    overlay.innerHTML = `
      <div class="blsm-cmdk-backdrop" data-close="1"></div>
      <div class="blsm-cmdk-panel" role="dialog" aria-modal="true" aria-label="Command palette">
        <div class="blsm-cmdk-search">
          <span class="blsm-cmdk-search-ico">${I("search")}</span>
          <input type="text" class="blsm-cmdk-input" placeholder="Search pages and actions" aria-label="Search pages and actions" autocomplete="off" spellcheck="false" />
          <kbd class="blsm-cmdk-esc">Esc</kbd>
        </div>
        <div class="blsm-cmdk-list" role="listbox"></div>
      </div>`;
    document.body.appendChild(overlay);
    inputEl = overlay.querySelector(".blsm-cmdk-input");
    listEl = overlay.querySelector(".blsm-cmdk-list");

    overlay.addEventListener("mousedown", (e) => {
      if (e.target.closest("[data-close]")) close();
    });
    listEl.addEventListener("mousemove", (e) => {
      const row = e.target.closest(".blsm-cmdk-item");
      if (!row) return;
      const i = Number(row.dataset.i);
      if (i !== active) {
        active = i;
        render();
      }
    });
    listEl.addEventListener("click", (e) => {
      const row = e.target.closest(".blsm-cmdk-item");
      if (!row) return;
      active = Number(row.dataset.i);
      execActive();
    });
    inputEl.addEventListener("input", () => {
      active = 0;
      render();
    });
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        active = Math.min(active + 1, items.length - 1);
        render();
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        active = Math.max(active - 1, 0);
        render();
      } else if (e.key === "Enter") {
        e.preventDefault();
        execActive();
      } else if (e.key === "Escape") {
        e.preventDefault();
        close();
      }
    });
  };

  const isOpen = () => overlay && !overlay.hidden;

  const open = () => {
    ensureOverlay();
    if (isOpen()) return;
    overlay.hidden = false;
    document.documentElement.classList.add("blsm-cmdk-open");
    active = 0;
    inputEl.value = "";
    render();
    requestAnimationFrame(() => inputEl.focus());
  };

  const close = () => {
    if (!overlay) return;
    overlay.hidden = true;
    document.documentElement.classList.remove("blsm-cmdk-open");
  };

  const toggle = () => (isOpen() ? close() : open());

  // --- wiring -------------------------------------------------------------

  document.addEventListener(
    "keydown",
    (e) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        toggle();
      }
    },
    true
  );

  // Repurpose the existing toolbar "Filter index" box into a palette launcher.
  // Focusing or clicking it opens the palette instead of the inline dropdown.
  const launchFromToolbar = (e) => {
    const el = e.target;
    if (el && el.tagName === "INPUT" && el.getAttribute("placeholder") === "Search (Ctrl+K)") {
      e.preventDefault();
      el.blur();
      open();
    }
  };
  document.addEventListener("focusin", launchFromToolbar, true);
  document.addEventListener("mousedown", launchFromToolbar, true);
})();
