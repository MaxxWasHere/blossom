(function () {
  const CARD_MARK = "blsm-mouse-cal-card";
  const ROOT_ID = "blsm-mouse-cal-root";
  const PAGE = "Macro Calibrations";
  const { observeMain, pageHeaderTitle, triggerMorphSwap, debounce } = window.Blossom || {};

  const CHEVRON =
    '<svg class="blsm-cal-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';

  const TONES = ["amber", "cyan", "green", "lime", "rose", "violet", "indigo", "sky", "yellow", "purple", "teal"];

  const CATEGORY_TONE = {
    movements: "violet",
    movement: "violet",
    merchant: "amber",
    quest: "cyan",
    inventory: "green",
    potion: "lime",
    fishing: "sky",
    biome: "teal",
    currency: "yellow",
    buff: "rose",
    aura: "purple",
  };

  const gridObservers = new WeakMap();
  let rebuildSuppressed = 0;
  let sectionInteracting = false;

  const debouncedRebuild =
    typeof debounce === "function"
      ? debounce((card) => {
          if (!isCalPage()) return;
          rebuildUi(card);
        }, 80)
      : (card) => rebuildUi(card);

  const isCalPage = () => pageHeaderTitle?.() === PAGE;

  const findCard = () => {
    const root = document.querySelector(".page-content, .main-content");
    if (!root) return null;
    for (const card of root.querySelectorAll(".card")) {
      const h3 = card.querySelector(".card-header h3");
      if (h3?.textContent?.trim() === "Mouse Action Calibration Requirements") return card;
    }
    return null;
  };

  const moveToTop = (card) => {
    const header = document.querySelector(".page-header");
    if (!header || !card) return;
    const hub = document.getElementById("blsm-cal-hub");
    if (hub?.parentElement) {
      if (card.nextElementSibling !== hub) hub.parentElement.insertBefore(card, hub);
      return;
    }
    if (header.nextElementSibling !== card) header.insertAdjacentElement("afterend", card);
  };

  const getCardBody = (card) => card.querySelector(":scope > div:not(.card-header)");

  const toneForCategory = (category) => {
    const key = (category || "").trim().toLowerCase().replace(/\s+/g, " ");
    for (const [needle, tone] of Object.entries(CATEGORY_TONE)) {
      if (key.includes(needle)) return tone;
    }
    let h = 0;
    for (let i = 0; i < key.length; i++) h = (h * 31 + key.charCodeAt(i)) >>> 0;
    return TONES[h % TONES.length];
  };

  const parseRow = (row) => {
    const cols = [...row.children].filter((el) => el.tagName === "DIV");
    if (cols.length < 3) return null;
    const category = cols[0].textContent?.trim() || "";
    const feature = cols[1].textContent?.trim() || "";
    if (!feature) return null;
    return {
      category,
      feature,
      calibrationsHtml: cols[2].innerHTML?.trim() || "",
      calibrationsText: cols[2].textContent?.trim() || "",
    };
  };

  const findNativeGrid = (body) => {
    if (!body) return null;
    const marked = body.querySelector(":scope > .blsm-mouse-cal-native-grid");
    if (marked) return marked;
    for (const el of body.children) {
      if (el.id === ROOT_ID) continue;
      if (el.classList?.contains("form-hint")) continue;
      if (!el.children?.length) continue;
      const rows = [...el.children];
      if (rows.length && rows.every((r) => r.children?.length >= 3)) return el;
    }
    return null;
  };

  const parseGrid = (grid) => {
    if (!grid) return [];
    return [...grid.children].map(parseRow).filter(Boolean);
  };

  const rowSignature = (rows) => rows.map((r) => `${r.category}\t${r.feature}\t${r.calibrationsText}`).join("\n");

  const formatCalibrations = (row) => {
    const html = row.calibrationsHtml;
    const text = row.calibrationsText;
    if (html && /<[a-z][\s\S]*>/i.test(html)) {
      const wrap = document.createElement("div");
      wrap.className = "blsm-mouse-cal-reqs blsm-mouse-cal-reqs--html";
      wrap.innerHTML = html;
      return wrap;
    }
    const wrap = document.createElement("div");
    wrap.className = "blsm-mouse-cal-reqs";
    const lines = (text || "")
      .split(/\n+|(?:\s*;\s*)|(?:\s*,\s+(?=[A-Z]))/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (lines.length <= 1) {
      const p = document.createElement("p");
      p.className = "blsm-mouse-cal-req-plain";
      p.textContent = text || "—";
      wrap.appendChild(p);
      return wrap;
    }
    const ul = document.createElement("ul");
    ul.className = "blsm-mouse-cal-req-list";
    for (const line of lines) {
      const li = document.createElement("li");
      li.textContent = line;
      ul.appendChild(li);
    }
    wrap.appendChild(ul);
    return wrap;
  };

  const openFeatureId = (root) =>
    root?.querySelector(".blsm-cal-section.is-open")?.dataset.feature || null;

  const restoreOpenSection = (host, feature) => {
    if (!feature || !host) return;
    const sec = host.querySelector(`.blsm-cal-section[data-feature="${CSS.escape(feature)}"]`);
    if (!sec) return;
    sec.classList.add("is-open");
    const head = sec.querySelector(".blsm-cal-section-head");
    if (head) head.setAttribute("aria-expanded", "true");
  };

  const mutationInsideBuiltUi = (mutation) => {
    const nodes = [mutation.target, mutation.previousSibling, mutation.nextSibling];
    for (const node of nodes) {
      if (!(node instanceof Element)) continue;
      if (node.id === ROOT_ID || node.closest?.(`#${ROOT_ID}`)) return true;
      if (node.closest?.(".blsm-cal-section")) return true;
    }
    return false;
  };

  const closeOtherSections = (host, keepSec) => {
    host.querySelectorAll(".blsm-cal-section.is-open").forEach((s) => {
      if (s === keepSec) return;
      s.classList.remove("is-open");
      const head = s.querySelector(".blsm-cal-section-head");
      if (head) head.setAttribute("aria-expanded", "false");
    });
  };

  const buildSection = (row, host) => {
    const sec = document.createElement("section");
    sec.className = "blsm-cal-section";
    sec.dataset.feature = row.feature;
    if (row.category) sec.dataset.category = row.category;
    const tone = toneForCategory(row.category);
    if (tone) sec.dataset.tone = tone;

    sec.innerHTML = `
      <button type="button" class="blsm-cal-section-head" aria-expanded="false">
        <div class="blsm-cal-section-title">
          <div class="blsm-cal-section-text">
            <strong>${escapeHtml(row.feature)}</strong>
          </div>
        </div>
        <div class="blsm-cal-section-meta">${CHEVRON}</div>
      </button>
      <div class="blsm-cal-section-body blsm-morph-body">
        <div class="blsm-cal-section-collapse blsm-morph-collapse">
          <div class="blsm-cal-section-scroll blsm-cal-section-content blsm-morph-panel"></div>
        </div>
      </div>
    `;

    const panel = sec.querySelector(".blsm-cal-section-content");
    if (row.category) {
      const meta = document.createElement("p");
      meta.className = "blsm-mouse-cal-category-meta";
      meta.textContent = row.category;
      panel.appendChild(meta);
    }
    panel.appendChild(formatCalibrations(row));

    const head = sec.querySelector(".blsm-cal-section-head");
    head.addEventListener("click", (e) => {
      e.stopPropagation();
      const opening = !sec.classList.contains("is-open");
      if (opening) closeOtherSections(host, sec);
      sec.classList.toggle("is-open");
      head.setAttribute("aria-expanded", sec.classList.contains("is-open") ? "true" : "false");
      const scroll = sec.querySelector(".blsm-morph-panel, .blsm-cal-section-scroll");
      if (scroll && opening) {
        if (triggerMorphSwap) triggerMorphSwap(scroll);
        else {
          scroll.classList.remove("blsm-morph-swap");
          void scroll.offsetWidth;
          scroll.classList.add("blsm-morph-swap");
        }
      }
    });

    return sec;
  };

  const escapeHtml = (s) =>
    String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");

  const markLegacyGrid = (grid) => {
    if (!grid) return;
    grid.classList.add("blsm-mouse-cal-native-grid", "blsm-mouse-cal-legacy-grid");
    [...grid.children].forEach((row) => row.classList.add("blsm-mouse-cal-native-row"));
  };

  const staticCardHeader = (card) => {
    card.classList.remove("blsm-md-accordion", "is-expanded");
    const header = card.querySelector(":scope > .card-header");
    if (header) header.style.cursor = "default";
    const sub = card.querySelector(".card-header p");
    sub?.classList.remove("blsm-md-sub-hide");
    const body = getCardBody(card);
    body?.classList.remove("blsm-morph-shell");
    if (body?.style?.display === "none") body.style.removeProperty("display");
  };

  const rebuildUi = (card) => {
    if (sectionInteracting || rebuildSuppressed > 0) return;
    const body = getCardBody(card);
    if (!body) return;

    const grid = findNativeGrid(body);
    const rows = parseGrid(grid);
    if (!rows.length) {
      card.querySelector(`#${ROOT_ID}`)?.remove();
      if (grid) grid.classList.remove("blsm-mouse-cal-legacy-grid");
      return;
    }

    markLegacyGrid(grid);

    const sig = rowSignature(rows);
    let root = card.querySelector(`#${ROOT_ID}`);
    const keepOpen = openFeatureId(root);
    if (root?.dataset.blsmSig === sig) return;

    rebuildSuppressed += 1;
    try {
      if (!root) {
        root = document.createElement("div");
        root.id = ROOT_ID;
        body.appendChild(root);
      }
      root.dataset.blsmSig = sig;
      root.replaceChildren();

      const sectionsHost = document.createElement("div");
      sectionsHost.className = "blsm-cal-sections";
      for (const row of rows) sectionsHost.appendChild(buildSection(row, sectionsHost));
      root.appendChild(sectionsHost);
      restoreOpenSection(sectionsHost, keepOpen);
    } finally {
      rebuildSuppressed -= 1;
    }
  };

  const watchGrid = (card) => {
    const body = getCardBody(card);
    if (!body) return;

    const grid = findNativeGrid(body);
    if (!grid) {
      gridObservers.get(card)?.disconnect?.();
      gridObservers.delete(card);
      return;
    }

    const prev = gridObservers.get(card);
    if (prev?.grid === grid) return;
    prev?.disconnect?.();

    const obs = new MutationObserver((mutations) => {
      if (!isCalPage() || sectionInteracting) return;
      if (mutations.every(mutationInsideBuiltUi)) return;
      debouncedRebuild(card);
    });
    obs.observe(grid, { childList: true, subtree: true });
    gridObservers.set(card, obs);
    obs.grid = grid;
  };

  const enhance = () => {
    if (!isCalPage()) return;
    const card = findCard();
    if (!card) return;

    card.classList.add(CARD_MARK, "blsm-md-card");
    card.classList.remove("blsm-md-accordion");
    moveToTop(card);
    staticCardHeader(card);
    rebuildUi(card);
    watchGrid(card);
  };

  document.addEventListener(
    "pointerdown",
    (e) => {
      if (e.target.closest?.(".blsm-mouse-cal-card .blsm-cal-section-head")) sectionInteracting = true;
    },
    true
  );
  document.addEventListener(
    "pointerup",
    () => {
      sectionInteracting = false;
    },
    true
  );
  document.addEventListener(
    "pointercancel",
    () => {
      sectionInteracting = false;
    },
    true
  );

  if (observeMain) observeMain(enhance, 0, PAGE);
  else {
    enhance();
    window.addEventListener("pywebviewready", enhance);
  }
})();
