(function () {
  "use strict";

  const OVERLAY_ID = "blossom-schedule-tour-overlay";
  const SCHEDULE_TOUR_VERSION = 1;
  const DONE_KEY = "schedule_tour_version";

  const api = () => window.pywebview?.api;
  const I = (name) => window.BlossomIcons?.svg(name) || "";

  const titlebarHeight = () => {
    const bar = document.querySelector(".coteab-injected-titlebar, .titlebar");
    if (!bar) return 40;
    return Math.max(0, Math.round(bar.getBoundingClientRect().bottom));
  };

  let state = { idx: 0, count: 0 };
  let opening = false;

  const persist = async (patch) => {
    const bridge = api();
    if (!bridge?.get_config || !bridge?.save_config) return false;
    const cur = await bridge.get_config();
    await bridge.save_config({ ...cur, ...patch });
    return true;
  };

  const close = () => {
    const o = document.getElementById(OVERLAY_ID);
    if (!o) return;
    o.style.animation = "blsm-st-fade 0.25s ease reverse both";
    setTimeout(() => o.remove(), 220);
    document.removeEventListener("keydown", onKey);
    opening = false;
  };

  const onKey = (e) => {
    if (e.key === "Escape") {
      void finish();
      return;
    }
    if (e.key === "ArrowRight" || e.key === "Enter") next();
    if (e.key === "ArrowLeft") prev();
  };

  const slides = () => [
    {
      html: `
        <h2>Timed automation blocks</h2>
        <p class="blsm-st-lead">Macro Schedule runs one activity at a time in order — fish, craft potions, merchant, or idle — each for the duration you set.</p>
        <div class="blsm-st-track-demo">
          <div class="blsm-st-track-row"><span>${I("fishing")} Fishing</span><span class="dur">2h 00m</span></div>
          <div class="blsm-st-track-row"><span>${I("flask")} Potion</span><span class="dur">3h 00m</span></div>
          <div class="blsm-st-track-row"><span>${I("cart")} Merchant</span><span class="dur">45m</span></div>
        </div>`,
    },
    {
      html: `
        <h2>Drag to build your plan</h2>
        <p class="blsm-st-lead">Use the grip on each block to reorder. Drag chips from the palette below onto the timeline to add new steps.</p>
        <div class="blsm-st-palette-demo">
          <span class="blsm-st-chip">${I("fishing")} Fishing</span>
          <span class="blsm-st-chip">${I("flask")} Potion</span>
          <span class="blsm-st-chip">${I("cart")} Merchant</span>
          <span class="blsm-st-chip">${I("pause")} Idle</span>
        </div>
        <p class="blsm-st-lead" style="font-size:0.8rem;margin-top:14px;">Tap the hours and minutes on each block to fine-tune duration.</p>`,
    },
    {
      html: `
        <h2>Duration &amp; loop</h2>
        <p class="blsm-st-lead">Set how long each block runs with the inline hour and minute fields. Turn on <strong>Loop after last step</strong> to return to step 1, or leave it off to stop the macro when the plan finishes.</p>
        <div class="blsm-st-highlight">Idle blocks pause automations for that window — useful for breaks or manual play between tasks.</div>`,
    },
    {
      html: `
        <h2>Enable &amp; start</h2>
        <p class="blsm-st-lead">Turn on <strong>Use schedule when macro runs</strong>, then press Start in the header (or your hotkey). The live pill at the bottom shows which step is active and time remaining.</p>
        <div class="blsm-st-highlight">While the macro runs, schedule mode overrides your manual fishing / potion / merchant toggles for the current step.</div>`,
    },
  ];

  const render = () => {
    const list = slides();
    state.count = list.length;
    const dots = list
      .map((_, i) => {
        let cls = "blsm-st-dot";
        if (i < state.idx) cls += " is-done";
        if (i === state.idx) cls += " is-active";
        return `<span class="${cls}" aria-hidden="true"></span>`;
      })
      .join("");

    const slideHtml = list
      .map((s, i) => {
        let cls = "blsm-st-slide";
        if (i === state.idx) cls += " is-active";
        else if (i < state.idx) cls += " is-prev";
        return `<div class="${cls}" data-idx="${i}">${s.html}</div>`;
      })
      .join("");

    const overlay = document.getElementById(OVERLAY_ID);
    if (!overlay) return;

    const top = titlebarHeight();
    overlay.style.top = `${top}px`;
    overlay.style.setProperty("--blsm-st-top", `${top}px`);
    overlay.querySelector(".blsm-st-progress").innerHTML = dots;
    overlay.querySelector(".blsm-st-viewport").innerHTML = slideHtml;
    overlay.querySelector("[data-st-back]").hidden = state.idx === 0;
    overlay.querySelector("[data-st-next]").textContent =
      state.idx >= state.count - 1 ? "Got it" : "Next";
  };

  const next = () => {
    if (state.idx < state.count - 1) {
      state.idx += 1;
      render();
      return;
    }
    void finish();
  };

  const prev = () => {
    if (state.idx > 0) {
      state.idx -= 1;
      render();
    }
  };

  const finish = async () => {
    await persist({ [DONE_KEY]: SCHEDULE_TOUR_VERSION });
    close();
    window.dispatchEvent(new CustomEvent("blossom-schedule-tour-done"));
  };

  const open = async () => {
    if (opening || document.getElementById(OVERLAY_ID)) return;
    opening = true;
    state = { idx: 0, count: slides().length };

    const overlay = document.createElement("div");
    overlay.id = OVERLAY_ID;
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Macro Schedule setup");
    overlay.innerHTML = `
      <div class="blsm-st-bg"></div>
      <div class="blsm-st-aurora a1"></div>
      <div class="blsm-st-aurora a2"></div>
      <div class="blsm-st-card">
        <div class="blsm-st-progress"></div>
        <div class="blsm-st-viewport"></div>
        <div class="blsm-st-foot">
          <button type="button" class="blsm-st-skip" data-st-skip>Skip setup</button>
          <div style="display:flex;gap:8px;">
            <button type="button" class="blsm-st-btn blsm-st-ghost" data-st-back hidden>Back</button>
            <button type="button" class="blsm-st-btn blsm-st-primary" data-st-next>Next</button>
          </div>
        </div>
      </div>`;

    const top = titlebarHeight();
    overlay.style.top = `${top}px`;
    overlay.style.setProperty("--blsm-st-top", `${top}px`);
    document.body.appendChild(overlay);
    render();

    overlay.querySelector("[data-st-next]")?.addEventListener("click", next);
    overlay.querySelector("[data-st-back]")?.addEventListener("click", prev);
    overlay.querySelector("[data-st-skip]")?.addEventListener("click", () => void finish());
    document.addEventListener("keydown", onKey);
  };

  const shouldShow = async () => {
    const bridge = api();
    if (!bridge?.get_config) return false;
    try {
      const cfg = await bridge.get_config();
      if (cfg[DONE_KEY] === SCHEDULE_TOUR_VERSION) return false;
      if (document.getElementById("blossom-intro-overlay")) return false;
      if (document.getElementById("blossom-license-overlay")) return false;
      return true;
    } catch {
      return false;
    }
  };

  const tryOpenOnTab = async () => {
    if (!(await shouldShow())) return;
    await open();
  };

  window.addEventListener("blossom-schedule-tab-open", () => {
    void tryOpenOnTab();
  });

  window.BlossomScheduleTour = { open, tryOpenOnTab, SCHEDULE_TOUR_VERSION };
})();
