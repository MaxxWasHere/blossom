(function () {
  const OVERLAY_ID = "blossom-macro-intro-overlay";
  const MACRO_INTRO_VERSION = 1;
  const GLOBAL_INTRO_VERSION = 5;
  const DONE_KEY = "macro_intro_version";

  const MACRO_PAGES = new Set(["Automated Actions", "Fishing", "Macro Status"]);

  const api = () => window.pywebview?.api;
  const { goToTab, pageHeaderTitle, observeMain } = window.Blossom || {};

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
    o.style.animation = "blsm-macro-intro-fade 0.25s ease reverse both";
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
        <h2>Macro setup</h2>
        <p class="blsm-mi-lead">Blossom automates fishing, merchant runs, potions, quests, and more while you are away. Use <strong>Start</strong> in the header (or your hotkey) to run everything you have enabled.</p>
        <div class="blsm-mi-illus">
          <div class="blsm-mi-tile"><span class="ico">▶️</span>Start / Stop</div>
          <div class="blsm-mi-tile"><span class="ico">🎣</span>Fishing loop</div>
          <div class="blsm-mi-tile"><span class="ico">🛒</span>Merchant</div>
        </div>`,
    },
    {
      html: `
        <h2>Calibrate once</h2>
        <p class="blsm-mi-lead">Macro Calibrations store screen positions for your resolution — movement, merchant dialogue, fishing UI, and inventory marks. You only need to do this once per setup.</p>
        <button type="button" class="blsm-mi-chip" data-mi-go="Calibrations">📍 Open Macro Calibrations</button>
        <p class="blsm-mi-lead" style="margin-top:14px;font-size:0.8rem;">Tip: use a preset if your resolution matches a bundled profile, then fine-tune individual marks.</p>`,
    },
    {
      html: `
        <h2>Pick your modes</h2>
        <p class="blsm-mi-lead">On <strong>Automated Actions</strong> and <strong>Fishing</strong>, toggle the automations you want. Merchant, quests, BR/SC, obby, biome tools, and Fishing Mode can run together — Blossom coordinates them.</p>
        <div class="blsm-mi-illus">
          <div class="blsm-mi-tile"><span class="ico">🎣</span>Fishing Mode</div>
          <div class="blsm-mi-tile"><span class="ico">⚗️</span>Potion craft</div>
          <div class="blsm-mi-tile"><span class="ico">🛒</span>Merchant</div>
        </div>`,
    },
    {
      html: `
        <h2>Macro Schedule</h2>
        <p class="blsm-mi-lead">Open the <strong>Macro Schedule</strong> sidebar tab to build an ordered plan — fish, craft potions, run merchant, then idle. Turn on <strong>Use schedule when macro runs</strong> and press Start.</p>
        <div class="blsm-mi-schedule">
          <div class="blsm-mi-schedule-row"><span>🎣 Fishing Mode</span><span class="dur">2h 00m</span></div>
          <div class="blsm-mi-schedule-row"><span>⚗️ Auto Potion Craft</span><span class="dur">3h 00m</span></div>
          <div class="blsm-mi-schedule-row"><span>🛒 Merchant Teleporter</span><span class="dur">45m</span></div>
        </div>
        <p class="blsm-mi-lead" style="font-size:0.8rem;">Schedules loop back to step 1, or stop after the last step — your choice.</p>`,
    },
    {
      html: `
        <h2>You are ready</h2>
        <p class="blsm-mi-lead">Enable your modes, calibrate if you have not yet, then press the green <strong>Start</strong> button. Macro Status shows live modules while the macro runs.</p>
        <div class="blsm-mi-highlight">Each macro tab shows a setup guide that updates as you calibrate, enable modes, and start the macro.</div>`,
    },
  ];

  const render = () => {
    const list = slides();
    state.count = list.length;
    const dots = list
      .map((_, i) => {
        let cls = "blsm-mi-dot";
        if (i < state.idx) cls += " is-done";
        if (i === state.idx) cls += " is-active";
        return `<span class="${cls}" aria-hidden="true"></span>`;
      })
      .join("");

    const slideHtml = list
      .map((s, i) => {
        let cls = "blsm-mi-slide";
        if (i === state.idx) cls += " is-active";
        else if (i < state.idx) cls += " is-prev";
        return `<div class="${cls}" data-idx="${i}">${s.html}</div>`;
      })
      .join("");

    const overlay = document.getElementById(OVERLAY_ID);
    if (!overlay) return;

    const top = titlebarHeight();
    overlay.style.top = `${top}px`;
    overlay.style.setProperty("--blsm-mi-top", `${top}px`);
    overlay.querySelector(".blsm-mi-progress").innerHTML = dots;
    overlay.querySelector(".blsm-mi-viewport").innerHTML = slideHtml;
    overlay.querySelector("[data-mi-back]").hidden = state.idx === 0;
    overlay.querySelector("[data-mi-next]").textContent =
      state.idx >= state.count - 1 ? "Get started" : "Next";
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
    await persist({ [DONE_KEY]: MACRO_INTRO_VERSION });
    close();
    window.dispatchEvent(new CustomEvent("blossom-macro-intro-done"));
  };

  const open = async () => {
    if (opening || document.getElementById(OVERLAY_ID)) return;
    opening = true;
    state = { idx: 0, count: slides().length };

    const overlay = document.createElement("div");
    overlay.id = OVERLAY_ID;
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.setAttribute("aria-label", "Macro setup");
    overlay.innerHTML = `
      <div class="blsm-mi-bg"></div>
      <div class="blsm-mi-aurora a1"></div>
      <div class="blsm-mi-aurora a2"></div>
      <div class="blsm-mi-card">
        <div class="blsm-mi-progress"></div>
        <div class="blsm-mi-viewport"></div>
        <div class="blsm-mi-foot">
          <button type="button" class="blsm-mi-skip" data-mi-skip>Skip setup</button>
          <div style="display:flex;gap:8px;">
            <button type="button" class="blsm-mi-btn blsm-mi-ghost" data-mi-back hidden>Back</button>
            <button type="button" class="blsm-mi-btn blsm-mi-primary" data-mi-next>Next</button>
          </div>
        </div>
      </div>`;

    const top = titlebarHeight();
    overlay.style.top = `${top}px`;
    overlay.style.setProperty("--blsm-mi-top", `${top}px`);
    document.body.appendChild(overlay);
    render();

    overlay.querySelector("[data-mi-next]")?.addEventListener("click", next);
    overlay.querySelector("[data-mi-back]")?.addEventListener("click", prev);
    overlay.querySelector("[data-mi-skip]")?.addEventListener("click", () => void finish());
    overlay.addEventListener("click", (e) => {
      const go = e.target.closest?.("[data-mi-go]");
      if (go && overlay.contains(go)) goToTab?.(go.getAttribute("data-mi-go"));
    });
    document.addEventListener("keydown", onKey);
  };

  const globalIntroDone = async () => {
    const bridge = api();
    if (!bridge?.get_config) return true;
    try {
      const cfg = await bridge.get_config();
      return cfg.intro_version === GLOBAL_INTRO_VERSION || cfg.intro_completed === true;
    } catch {
      return true;
    }
  };

  const shouldShow = async () => {
    const bridge = api();
    if (!bridge?.get_config) return false;
    try {
      const cfg = await bridge.get_config();
      if (cfg[DONE_KEY] === MACRO_INTRO_VERSION) return false;
      if (!(await globalIntroDone())) return false;
      if (document.getElementById("blossom-intro-overlay")) return false;
      if (document.getElementById("blossom-license-overlay")) return false;
      return true;
    } catch {
      return false;
    }
  };

  const tryOpen = async () => {
    if (!(await shouldShow())) return;
    if (!MACRO_PAGES.has(pageHeaderTitle?.() || "")) return;
    await open();
  };

  const onMacroPage = () => {
    if (!MACRO_PAGES.has(pageHeaderTitle?.() || "")) return;
    void tryOpen();
  };

  const schedule = () => {
    const run = () => {
      const armMacroIntro = () => {
        window.addEventListener("blossom-intro-done", onMacroPage, { once: true });
        if (observeMain) observeMain(onMacroPage, 200, [...MACRO_PAGES]);
        else if (!document.getElementById("blossom-intro-overlay")) onMacroPage();
      };
      if (window.BlossomLicense?.whenReady) {
        window.BlossomLicense.whenReady(armMacroIntro);
        return;
      }
      armMacroIntro();
    };
    if (window.pywebview?.api) run();
    else window.addEventListener("pywebviewready", run, { once: true });
  };

  window.BlossomMacroIntro = { open, tryOpen, MACRO_INTRO_VERSION };

  schedule();
})();
