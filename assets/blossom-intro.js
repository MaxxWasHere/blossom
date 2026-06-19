(function () {
  const OVERLAY_ID = "blossom-intro-overlay";
  const STYLE_ID = "blossom-intro-style";
  // Bump this whenever the intro changes — it re-shows for everyone (and self-heals
  // past dismissals where only the old boolean `intro_completed` was stored).
  const INTRO_VERSION = 5;
  const DONE_KEY = "intro_version";

  const api = () => window.pywebview?.api;

  // Inline vector icon (falls back to the original emoji if icons aren't loaded).
  const ICO = (name, fallback) => window.BlossomIcons?.svg(name) || fallback || "";

  const firstString = (raw) => {
    if (Array.isArray(raw)) return raw.find((x) => typeof x === "string" && x.trim()) || "";
    if (typeof raw === "string") return raw;
    return "";
  };
  const esc = (s) => String(s == null ? "" : s).replace(/"/g, "&quot;");
  const isValidWebhook = (url) =>
    /^https:\/\/(?:(?:ptb|canary|discordapp)\.)?discord(?:app)?\.com\/api\/webhooks\/\d+\/[\w-]+$/i.test(url);

  const titlebarHeight = () => {
    const bar = document.querySelector(".coteab-injected-titlebar, .titlebar");
    if (!bar) return 40;
    const r = bar.getBoundingClientRect();
    return Math.max(0, Math.round(r.bottom));
  };

  const injectStyles = () => {};

  const close = () => {
    const o = document.getElementById(OVERLAY_ID);
    if (!o) return;
    o.style.animation = "blsm-intro-fade 0.25s ease reverse both";
    setTimeout(() => o.remove(), 220);
    document.removeEventListener("keydown", onKey);
    window.dispatchEvent(new CustomEvent("blossom-intro-done"));
  };

  let state = { idx: 0, count: 0, config: {} };

  const persist = async (patch) => {
    const bridge = api();
    if (!bridge?.get_config || !bridge?.save_config) return false;
    const cur = await bridge.get_config();
    await bridge.save_config({ ...cur, ...patch });
    return true;
  };

  const onKey = (e) => {
    if (!document.getElementById(OVERLAY_ID)) return;
    if (e.key === "ArrowRight") go(1);
    else if (e.key === "ArrowLeft") go(-1);
  };

  let go = () => {};

  const THEMES = [
    ["system", "Match system", "linear-gradient(135deg,#18181b 50%,#fafafa 50%)"],
    ["pink", "Pink", "#e891a8"],
    ["dark", "Dark", "#3f3f46"],
    ["light", "Light", "#fafafa"],
  ];

  const normalizeIntroTheme = (raw) => {
    const k = String(raw || "system").toLowerCase();
    const valid = ["system", "pink", "dark", "light", "oled", "sakura", "midnight", "forest"];
    if (valid.includes(k)) return k;
    const legacy = { blush: "pink", solar: "pink", ocean: "dark", arctic: "light" };
    return legacy[k] || "system";
  };

  const render = (config) => {
    const wh = firstString(config.webhook_url);
    const curTheme = normalizeIntroTheme(config.ui_theme || config.selected_theme);
    const themeBtns = THEMES.map(
      ([id, label, sw]) =>
        `<button type="button" class="blsm-theme ${id === curTheme ? "is-sel" : ""}" data-theme-val="${id}" aria-pressed="${id === curTheme}" style="--sw:${sw}"><span class="sw" aria-hidden="true"></span><span class="blsm-theme-label">${label}</span></button>`
    ).join("");
    const overlay = document.createElement("div");
    overlay.id = OVERLAY_ID;
    overlay.dataset.theme = curTheme;
    overlay.innerHTML = `
      <div class="blsm-bg"></div>
      <div class="blsm-aurora a1"></div>
      <div class="blsm-aurora a2"></div>
      <div class="blsm-aurora a3"></div>
      <div class="blsm-petals"></div>
      <div class="blsm-card" role="dialog" aria-modal="true">
        <div class="blsm-progress"></div>
        <div class="blsm-viewport">
          <section class="blsm-slide" data-slide="0">
            <img class="blsm-logo blsm-stagger" src="./blossom.png" alt="Blossom" onerror="this.style.display='none'"/>
            <div class="blsm-eyebrow blsm-stagger">Welcome</div>
            <h1 class="blsm-stagger">Blossom</h1>
            <p class="blsm-lead blsm-stagger">Sol's RNG macro — pick a theme, optional Discord webhook, and which
              automations to run. About a minute. Use ← → or the buttons below.</p>
          </section>

          <section class="blsm-slide" data-slide="1">
            <div class="blsm-slide-head blsm-stagger">
              <div class="ring blsm-icon">${ICO("flower", "🌸")}</div>
              <div><h2 style="margin:0">What Blossom does</h2><div class="sub">The main tabs and what they run.</div></div>
            </div>
            <div class="blsm-features blsm-stagger">
              <div class="blsm-feature"><span class="fi">${ICO("cart", "🛒")}</span><div><b>Auto Merchant</b><span>Teleports, talks & buys from Mari / Jester automatically.</span></div></div>
              <div class="blsm-feature"><span class="fi">${ICO("scroll", "📜")}</span><div><b>Daily Quests</b><span>Claims daily quest rewards for you.</span></div></div>
              <div class="blsm-feature"><span class="fi">${ICO("dice", "🎲")}</span><div><b>Biome Tools</b><span>Randomizers, Strange Controllers & glitched buffs.</span></div></div>
              <div class="blsm-feature"><span class="fi">${ICO("flask", "⚗️")}</span><div><b>Potions</b><span>Auto-craft and switch potions while you AFK.</span></div></div>
              <div class="blsm-feature"><span class="fi">${ICO("bell", "🔔")}</span><div><b>Webhooks</b><span>Discord pings for rare biomes & merchant sightings.</span></div></div>
              <div class="blsm-feature"><span class="fi">${ICO("keyboard", "⌨️")}</span><div><b>Hotkeys</b><span>Start / stop instantly with your own keybinds.</span></div></div>
            </div>
          </section>

          <section class="blsm-slide" data-slide="2">
            <div class="blsm-slide-head blsm-stagger">
              <div class="ring blsm-icon">${ICO("palette", "🎨")}</div>
              <div><h2 style="margin:0">Pick a theme</h2><div class="sub">Click to preview — change anytime under Appearance.</div></div>
            </div>
            <div class="blsm-themes blsm-stagger">${themeBtns}</div>
          </section>

          <section class="blsm-slide" data-slide="3">
            <div class="blsm-slide-head blsm-stagger">
              <div class="ring blsm-icon">${ICO("bell", "🔔")}</div>
              <div><h2 style="margin:0">Discord notifications</h2><div class="sub">Get pinged for merchant sightings & rare biomes.</div></div>
            </div>
            <div class="blsm-field blsm-stagger">
              <label for="blsm-webhook">Webhook URL</label>
              <input id="blsm-webhook" type="text" placeholder="https://discord.com/api/webhooks/…" value="${esc(wh)}" />
              <div class="blsm-inline">
                <button type="button" class="blsm-test" data-act="test">Send test</button>
              </div>
              <div class="hint">Server Settings → Integrations → Webhooks → New Webhook → Copy URL. Leave blank to skip.</div>
            </div>
          </section>

          <section class="blsm-slide" data-slide="4">
            <div class="blsm-slide-head blsm-stagger">
              <div class="ring blsm-icon">${ICO("gamepad", "🎮")}</div>
              <div><h2 style="margin:0">Your Roblox</h2><div class="sub">Optional — used to label notifications and rejoin links.</div></div>
            </div>
            <div class="blsm-field blsm-stagger">
              <label for="blsm-user">Roblox username</label>
              <input id="blsm-user" type="text" placeholder="YourRobloxName" value="${esc(config.roblox_username)}" />
            </div>
            <div class="blsm-field blsm-stagger">
              <label for="blsm-ps">Private server link</label>
              <input id="blsm-ps" type="text" placeholder="https://www.roblox.com/share?code=…" value="${esc(config.private_server_link)}" />
              <div class="hint">Lets webhook embeds include a one-click rejoin button.</div>
            </div>
          </section>

          <section class="blsm-slide" data-slide="5">
            <div class="blsm-slide-head blsm-stagger">
              <div class="ring blsm-icon">${ICO("sparkle", "✨")}</div>
              <div><h2 style="margin:0">Automations</h2><div class="sub">Toggle what runs. Change anytime in the sidebar.</div></div>
            </div>
            <div class="blsm-auto blsm-stagger">
              <div class="blsm-row ${config.merchant_teleporter ? "on" : ""}" data-key="merchant_teleporter">
                <span class="emoji">${ICO("cart", "🛒")}</span><div class="txt"><b>Auto Merchant</b><span>Teleport, talk & buy from Mari / Jester.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row ${config.fishing_mode ? "on" : ""}" data-key="fishing_mode">
                <span class="emoji">${ICO("fish", "🎣")}</span><div class="txt"><b>Fishing Mode</b><span>Auto cast, reel, sell, and dock trips.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row ${config.auto_claim_daily_quests ? "on" : ""}" data-key="auto_claim_daily_quests">
                <span class="emoji">${ICO("scroll", "📜")}</span><div class="txt"><b>Daily Quests</b><span>Auto-claim daily quest rewards.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row ${config.biome_randomizer ? "on" : ""}" data-key="biome_randomizer">
                <span class="emoji">${ICO("dice", "🎲")}</span><div class="txt"><b>Biome Randomizer</b><span>Use Biome Randomizers on a timer.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row blsm-row-disabled" data-key="biome_selector" data-disabled="1">
                <span class="emoji">${ICO("compass", "🧭")}</span><div class="txt"><b>Biome Selector <span style="color:#ff6b6b;">(Broken / W.I.P.)</span></b><span>Unfinished — leave off for now.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row ${config.strange_controller ? "on" : ""}" data-key="strange_controller">
                <span class="emoji">${ICO("gamepad", "🕹️")}</span><div class="txt"><b>Strange Controller</b><span>Auto-use Strange Controllers.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row ${config.enable_potion_crafting ? "on" : ""}" data-key="enable_potion_crafting">
                <span class="emoji">${ICO("flask", "⚗️")}</span><div class="txt"><b>Potion Crafting</b><span>Auto-craft potions from your recipe files.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row ${config.enable_auto_obby ? "on" : ""}" data-key="enable_auto_obby">
                <span class="emoji">${ICO("run", "🏃")}</span><div class="txt"><b>Auto Obby</b><span>Run a recorded obby path on a timer.</span></div><div class="blsm-switch"></div>
              </div>
            </div>
          </section>

          <section class="blsm-slide" data-slide="6">
            <div class="blsm-slide-head blsm-stagger">
              <div class="ring blsm-icon">${ICO("bulb", "💡")}</div>
              <div><h2 style="margin:0">Tips & shortcuts</h2><div class="sub">Read these once before you AFK.</div></div>
            </div>
            <div class="blsm-tips blsm-stagger">
              <div class="blsm-tip"><span class="ti">1.</span><div>Calibrate first under <b>Macro Calibrations</b> — automations rely on accurate UI positions for your resolution.</div></div>
              <div class="blsm-tip"><span class="ti">2.</span><div>Set a <b>start/stop hotkey</b> in Settings so you can toggle the macro without touching the window.</div></div>
              <div class="blsm-tip"><span class="ti">3.</span><div>Add a <b>private server link</b> so webhook alerts include a one-click rejoin.</div></div>
              <div class="blsm-tip"><span class="ti">4.</span><div>On the <b>beta</b> channel? Expect new features that may occasionally break — report anything odd.</div></div>
              <div class="blsm-tip"><span class="ti">5.</span><div>Everything here lives in the sidebar — revisit this guide by bumping the intro version.</div></div>
            </div>
          </section>

          <section class="blsm-slide" data-slide="7">
            <div class="blsm-eyebrow blsm-stagger" style="margin-top:8px">All set</div>
            <h1 class="blsm-stagger" style="font-size:26px">You're ready to bloom 🌸</h1>
            <p class="blsm-lead blsm-stagger">Quick recap of what you picked. Finish to close this and use the macro.</p>
            <div class="blsm-summary blsm-stagger" data-role="summary"></div>
          </section>
        </div>
        <div class="blsm-status"></div>
        <div class="blsm-foot">
          <button class="blsm-text-link" data-act="skip">Skip setup</button>
          <div style="display:flex; gap:10px;">
            <button class="blsm-btn blsm-ghost" data-act="back">Back</button>
            <button class="blsm-btn blsm-primary" data-act="next">Get started</button>
          </div>
        </div>
      </div>
    `;
    return overlay;
  };

  const spawnPetals = (overlay) => {
    const host = overlay.querySelector(".blsm-petals");
    for (let i = 0; i < 9; i++) {
      const p = document.createElement("span");
      p.className = "blsm-petal";
      p.style.left = Math.random() * 100 + "%";
      p.style.animationDuration = 7 + Math.random() * 9 + "s";
      p.style.animationDelay = -Math.random() * 12 + "s";
      const sc = 0.6 + Math.random() * 1.1;
      p.style.transform = `scale(${sc})`;
      p.style.opacity = "1";
      host.appendChild(p);
    }
  };

  const collect = (overlay) => {
    const webhook = overlay.querySelector("#blsm-webhook")?.value.trim() || "";
    const patch = {
      roblox_username: overlay.querySelector("#blsm-user")?.value.trim() || "",
      private_server_link: overlay.querySelector("#blsm-ps")?.value.trim() || "",
      ui_theme: normalizeIntroTheme(overlay.dataset.theme || "system"),
      selected_theme: normalizeIntroTheme(overlay.dataset.theme || "system"),
    };
    overlay.querySelectorAll(".blsm-row").forEach((row) => {
      const key = row.getAttribute("data-key");
      if (key === "biome_selector") {
        patch[key] = false;
        return;
      }
      if (row.getAttribute("data-disabled")) return;
      patch[key] = row.classList.contains("on");
    });
    return { webhook, patch };
  };

  const updateSummary = (overlay) => {
    const { webhook, patch } = collect(overlay);
    const yn = (b) => (b ? "On" : "Off");
    const themeLabel = (THEMES.find((t) => t[0] === normalizeIntroTheme(patch.ui_theme)) || [])[1] || patch.ui_theme;
    const rows = [
      ["Theme", themeLabel],
      ["Webhook", webhook ? "Connected" : "Skipped"],
      ["Roblox user", patch.roblox_username || "—"],
      ["Auto Merchant", yn(patch.merchant_teleporter)],
      ["Fishing Mode", yn(patch.fishing_mode)],
      ["Daily Quests", yn(patch.auto_claim_daily_quests)],
      ["Biome Randomizer", yn(patch.biome_randomizer)],
      ["Biome Selector", yn(patch.biome_selector)],
      ["Strange Controller", yn(patch.strange_controller)],
      ["Potion Crafting", yn(patch.enable_potion_crafting)],
      ["Auto Obby", yn(patch.enable_auto_obby)],
    ];
    const host = overlay.querySelector('[data-role="summary"]');
    if (host) {
      host.innerHTML = rows
        .map(
          ([k, v]) =>
            `<div class="item"><span>${esc(k)}</span><b>${esc(v)}</b></div>`
        )
        .join("");
    }
  };

  const open = async () => {
    if (document.getElementById(OVERLAY_ID)) return;
    let config = {};
    const bridge = api();
    if (bridge?.get_config) { try { config = await bridge.get_config(); } catch {} }
    state.config = config;

    injectStyles();
    const overlay = render(config);
    const top = titlebarHeight();
    overlay.style.top = top + "px";
    overlay.style.setProperty("--blsm-intro-top", top + "px");
    document.body.appendChild(overlay);
    spawnPetals(overlay);

    const slides = [...overlay.querySelectorAll(".blsm-slide")];
    state.count = slides.length;
    state.idx = 0;
    const dotsHost = overlay.querySelector(".blsm-progress");
    dotsHost.innerHTML = slides.map(() => `<div class="blsm-dot"></div>`).join("");
    const dots = [...dotsHost.querySelectorAll(".blsm-dot")];
    const status = overlay.querySelector(".blsm-status");
    const backBtn = overlay.querySelector('[data-act="back"]');
    const nextBtn = overlay.querySelector('[data-act="next"]');

    const paint = () => {
      slides.forEach((sl, i) => {
        sl.classList.toggle("is-active", i === state.idx);
        sl.classList.toggle("is-prev", i < state.idx);
      });
      dots.forEach((d, i) => {
        d.classList.toggle("is-active", i === state.idx);
        d.classList.toggle("is-done", i < state.idx);
      });
      backBtn.style.visibility = state.idx === 0 ? "hidden" : "visible";
      const last = state.idx === state.count - 1;
      nextBtn.textContent = state.idx === 0 ? "Get started" : last ? "Finish" : "Next";
      status.textContent = "";
      if (last) updateSummary(overlay);
    };

    go = (dir) => {
      const next = state.idx + dir;
      if (next < 0 || next >= state.count) return;
      // Validate webhook before leaving the webhook slide (slide index 3).
      if (dir > 0 && state.idx === 3) {
        const v = overlay.querySelector("#blsm-webhook").value.trim();
        if (v && !isValidWebhook(v)) {
          status.textContent = "That doesn't look like a Discord webhook URL — fix it or clear it.";
          return;
        }
      }
      state.idx = next;
      paint();
    };

    const finish = async () => {
      const { webhook, patch } = collect(overlay);
      if (webhook && !isValidWebhook(webhook)) { state.idx = 3; paint(); return; }
      if (webhook) patch.webhook_url = [webhook];
      patch[DONE_KEY] = INTRO_VERSION;
      status.textContent = "Saving…";
      const ok = await persist(patch);
      if (ok) close(); else status.textContent = "Couldn't save (backend not ready).";
    };

    overlay.addEventListener("click", async (e) => {
      const themeBtn = e.target.closest?.(".blsm-theme");
      if (themeBtn && overlay.contains(themeBtn)) {
        const val = themeBtn.getAttribute("data-theme-val");
        overlay.dataset.theme = val;
        overlay.querySelectorAll(".blsm-theme").forEach((b) => {
          const on = b === themeBtn;
          b.classList.toggle("is-sel", on);
          b.setAttribute("aria-pressed", on ? "true" : "false");
        });
        document.body.setAttribute("data-theme", val);
        return;
      }
      const row = e.target.closest?.(".blsm-row");
      if (row && overlay.contains(row)) {
        if (row.getAttribute("data-disabled")) return;
        row.classList.toggle("on");
        return;
      }
      const act = e.target?.getAttribute?.("data-act");
      if (!act) return;
      if (act === "next") { state.idx === state.count - 1 ? finish() : go(1); }
      else if (act === "back") go(-1);
      else if (act === "skip") { await persist({ [DONE_KEY]: INTRO_VERSION }); close(); }
      else if (act === "test") {
        const url = overlay.querySelector("#blsm-webhook").value.trim();
        if (!url || !isValidWebhook(url)) { status.textContent = "Enter a valid webhook URL first."; return; }
        status.textContent = "Sending test…";
        try {
          // Persist first so the backend test uses the entered URL.
          await persist({ webhook_url: [url] });
          await api()?.send_webhook_status?.("Blossom test — webhook connected!", 15161839);
          status.textContent = "Test sent — check your channel.";
        } catch (err) { status.textContent = "Test failed: " + err; }
      }
    });

    document.addEventListener("keydown", onKey);
    paint();
  };

  const boot = async () => {
    let config = {};
    const bridge = api();
    if (bridge?.get_config) { try { config = await bridge.get_config(); } catch {} }
    if (config[DONE_KEY] !== INTRO_VERSION) await open();
  };

  const scheduleBoot = () => {
    const run = () => {
      if (window.BlossomLicense?.whenReady) {
        window.BlossomLicense.whenReady(() => void boot());
        return;
      }
      void boot();
    };
    if (window.pywebview?.api) run();
    else window.addEventListener("pywebviewready", run, { once: true });
  };

  window.BlossomIntro = { open, INTRO_VERSION };

  scheduleBoot();
})();
