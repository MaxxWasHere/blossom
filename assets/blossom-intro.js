(function () {
  const OVERLAY_ID = "blossom-intro-overlay";
  const STYLE_ID = "blossom-intro-style";
  // Bump this whenever the intro changes — it re-shows for everyone (and self-heals
  // past dismissals where only the old boolean `intro_completed` was stored).
  const INTRO_VERSION = 4;
  const DONE_KEY = "intro_version";

  const api = () => window.pywebview?.api;

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

  const injectStyles = () => {
    if (document.getElementById(STYLE_ID)) return;
    const s = document.createElement("style");
    s.id = STYLE_ID;
    s.textContent = `
      #${OVERLAY_ID} {
        position: fixed; left: 0; right: 0; bottom: 0; top: 40px;
        z-index: 900; display: flex; align-items: center; justify-content: center;
        overflow: hidden; font-family: Sarpanch, Inter, -apple-system, "Segoe UI", sans-serif;
        color: var(--text-primary, #e7e3f1);
        animation: blsm-in .35s ease both;
      }
      @keyframes blsm-in { from { opacity: 0 } to { opacity: 1 } }
      #${OVERLAY_ID} .blsm-bg { position: absolute; inset: 0; background: var(--bg-root, #0a0a10); }
      #${OVERLAY_ID} .blsm-aurora {
        position: absolute; border-radius: 50%; filter: blur(80px); opacity: .26; mix-blend-mode: screen;
        animation: blsm-drift 22s ease-in-out infinite alternate;
      }
      #${OVERLAY_ID} .a1 { width: 42vw; height: 42vw; left: -8vw; top: -14vw; background: radial-gradient(circle, #e87cc0, transparent 64%); }
      #${OVERLAY_ID} .a2 { width: 38vw; height: 38vw; right: -10vw; top: 4vw; background: radial-gradient(circle, #e891a8, transparent 64%); animation-duration: 26s; }
      #${OVERLAY_ID} .a3 { width: 34vw; height: 34vw; left: 22vw; bottom: -16vw; background: radial-gradient(circle, #5bd6f5, transparent 64%); animation-duration: 30s; opacity: .18; }
      @keyframes blsm-drift {
        0%   { transform: translate(0,0) scale(1); }
        50%  { transform: translate(3vw,2vw) scale(1.12); }
        100% { transform: translate(-2vw,-1vw) scale(.95); }
      }
      #${OVERLAY_ID} .blsm-petal { position: absolute; top: -8%; width: 11px; height: 11px; border-radius: 60% 0 60% 0;
        background: linear-gradient(140deg, #ffd9ef, #e87cc0); opacity: .0; animation: blsm-fall linear infinite; }
      @keyframes blsm-fall {
        0% { transform: translateY(-10vh) rotate(0deg); opacity: 0; }
        12% { opacity: .8; }
        100% { transform: translateY(112vh) rotate(540deg); opacity: 0; }
      }

      #${OVERLAY_ID} .blsm-card {
        position: relative; z-index: 2; width: min(640px, 94vw);
        background: linear-gradient(180deg, rgba(26,23,38,.95), rgba(17,15,26,.96));
        border: 1px solid rgba(255,255,255,.10);
        border-radius: 18px; box-shadow: 0 24px 64px rgba(0,0,0,.45), inset 0 1px 0 rgba(255,255,255,.04);
        backdrop-filter: blur(10px); -webkit-backdrop-filter: blur(10px);
        display: flex; flex-direction: column; overflow: hidden;
        animation: blsm-pop .5s cubic-bezier(.16,1,.3,1) both;
      }
      @keyframes blsm-pop { from { opacity: 0; transform: translateY(20px) scale(.97); } to { opacity: 1; transform: none; } }

      #${OVERLAY_ID} .blsm-progress { display: flex; gap: 7px; padding: 18px 24px 4px; align-items: center; }
      #${OVERLAY_ID} .blsm-dot { height: 6px; width: 6px; border-radius: 999px; background: rgba(255,255,255,.18);
        transition: width .45s cubic-bezier(.16,1,.3,1), background .45s ease; }
      #${OVERLAY_ID} .blsm-dot.is-active { width: 26px; background: linear-gradient(90deg, #f3a9d8, #e07cc0); }
      #${OVERLAY_ID} .blsm-dot.is-done { background: rgba(232,124,192,.5); }

      #${OVERLAY_ID} .blsm-viewport { position: relative; min-height: 366px; }
      #${OVERLAY_ID} .blsm-slide {
        position: absolute; inset: 0; padding: 14px 30px 6px; display: flex; flex-direction: column;
        opacity: 0; transform: translateX(46px) scale(.95); pointer-events: none;
        transition: opacity .5s ease, transform .6s cubic-bezier(.16,1,.3,1); overflow-y: auto;
      }
      #${OVERLAY_ID} .blsm-slide.is-active { opacity: 1; transform: none; pointer-events: auto; }
      #${OVERLAY_ID} .blsm-slide.is-prev { transform: translateX(-46px) scale(.95); }

      #${OVERLAY_ID} .blsm-stagger { opacity: 0; transform: translateY(14px); transition: opacity .5s ease, transform .55s cubic-bezier(.16,1,.3,1); }
      #${OVERLAY_ID} .is-active .blsm-stagger { opacity: 1; transform: none; }
      #${OVERLAY_ID} .is-active .blsm-stagger:nth-child(1) { transition-delay: .08s; }
      #${OVERLAY_ID} .is-active .blsm-stagger:nth-child(2) { transition-delay: .15s; }
      #${OVERLAY_ID} .is-active .blsm-stagger:nth-child(3) { transition-delay: .22s; }
      #${OVERLAY_ID} .is-active .blsm-stagger:nth-child(4) { transition-delay: .29s; }
      #${OVERLAY_ID} .is-active .blsm-stagger:nth-child(5) { transition-delay: .36s; }
      #${OVERLAY_ID} .is-active .blsm-stagger:nth-child(6) { transition-delay: .43s; }

      #${OVERLAY_ID} .blsm-logo { width: 74px; height: 74px; border-radius: 20px; object-fit: cover; align-self: center;
        box-shadow: 0 10px 24px rgba(0,0,0,.35); animation: blsm-float 5s ease-in-out infinite; }
      @keyframes blsm-float { 0%,100% { transform: translateY(0) rotate(-2deg); } 50% { transform: translateY(-9px) rotate(2deg); } }
      #${OVERLAY_ID} .blsm-eyebrow { text-align: center; font-size: 11px; letter-spacing: .22em; text-transform: uppercase;
        color: #e89bd0; font-weight: 700; margin-top: 14px; }
      #${OVERLAY_ID} h1 { text-align: center; margin: 6px 0 6px; font-size: 30px; font-weight: 800; letter-spacing: .3px;
        background: linear-gradient(90deg, #ffe3f3, #f3a9d8 55%, #c5a8ff); -webkit-background-clip: text; background-clip: text; color: transparent; }
      #${OVERLAY_ID} h2 { margin: 2px 0 14px; font-size: 21px; font-weight: 800; }
      #${OVERLAY_ID} .blsm-lead { text-align: center; color: var(--text-secondary, #b4adc4); font-size: 13.5px; line-height: 1.6; max-width: 460px; align-self: center; }
      #${OVERLAY_ID} .blsm-icon { font-size: 26px; }
      #${OVERLAY_ID} .blsm-slide-head { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
      #${OVERLAY_ID} .blsm-slide-head .ring { width: 44px; height: 44px; border-radius: 13px; display: grid; place-items: center;
        background: rgba(232,124,192,.12); border: 1px solid rgba(232,124,192,.3); }
      #${OVERLAY_ID} .blsm-slide-head .sub { color: var(--text-secondary, #b4adc4); font-size: 12.5px; }

      #${OVERLAY_ID} .blsm-field { margin-top: 16px; }
      #${OVERLAY_ID} .blsm-field label { display: block; font-size: 12px; font-weight: 700; color: #ddd2ea; margin-bottom: 7px; }
      #${OVERLAY_ID} input[type="text"] { width: 100%; box-sizing: border-box; padding: 12px 13px; font-size: 13px;
        color: #f3f0f7; background: rgba(255,255,255,.045); border: 1px solid rgba(255,255,255,.12); border-radius: 12px; outline: none;
        transition: border-color .18s ease, box-shadow .18s ease, background .18s ease; font-family: inherit; }
      #${OVERLAY_ID} input[type="text"]:focus { border-color: rgba(232,124,192,.6); background: rgba(255,255,255,.06);
        box-shadow: 0 0 0 3px rgba(232,124,192,.12); }
      #${OVERLAY_ID} .hint { margin-top: 7px; font-size: 11.5px; color: var(--text-muted, #8b85a0); line-height: 1.5; }
      #${OVERLAY_ID} .blsm-inline { display: flex; gap: 9px; margin-top: 10px; }
      #${OVERLAY_ID} .blsm-test { white-space: nowrap; padding: 0 14px; border-radius: 10px; border: 1px solid rgba(255,255,255,.14);
        background: rgba(255,255,255,.05); color: #ddd2ea; font-weight: 700; font-size: 12px; cursor: pointer; transition: all .15s ease; }
      #${OVERLAY_ID} .blsm-test:hover { border-color: rgba(232,124,192,.5); color: #fff; }

      #${OVERLAY_ID} .blsm-auto { display: grid; gap: 10px; margin-top: 14px; }
      #${OVERLAY_ID} .blsm-row { display: flex; align-items: center; gap: 13px; padding: 13px 15px; cursor: pointer;
        border: 1px solid rgba(255,255,255,.10); border-radius: 14px; background: rgba(255,255,255,.03);
        transition: border-color .18s ease, background .18s ease, transform .18s ease; }
      #${OVERLAY_ID} .blsm-row:hover { border-color: rgba(232,124,192,.4); transform: translateX(3px); }
      #${OVERLAY_ID} .blsm-row .emoji { font-size: 20px; width: 26px; text-align: center; }
      #${OVERLAY_ID} .blsm-row .txt { flex: 1; }
      #${OVERLAY_ID} .blsm-row .txt b { display: block; font-size: 13.5px; }
      #${OVERLAY_ID} .blsm-row .txt span { font-size: 11.5px; color: var(--text-muted, #8b85a0); }
      #${OVERLAY_ID} .blsm-switch { position: relative; width: 42px; height: 24px; border-radius: 999px; flex-shrink: 0;
        background: rgba(255,255,255,.14); transition: background .22s ease; }
      #${OVERLAY_ID} .blsm-switch::after { content: ""; position: absolute; top: 3px; left: 3px; width: 18px; height: 18px;
        border-radius: 50%; background: #fff; transition: transform .26s cubic-bezier(.16,1,.3,1); box-shadow: 0 2px 6px rgba(0,0,0,.4); }
      #${OVERLAY_ID} .blsm-row.on .blsm-switch { background: linear-gradient(90deg, #f3a9d8, #e07cc0); }
      #${OVERLAY_ID} .blsm-row.on .blsm-switch::after { transform: translateX(18px); }

      #${OVERLAY_ID} .blsm-features { margin-top: 14px; display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
      #${OVERLAY_ID} .blsm-feature { display: flex; gap: 10px; padding: 11px 12px; border-radius: 13px;
        background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.08); }
      #${OVERLAY_ID} .blsm-feature .fi { font-size: 19px; line-height: 1; }
      #${OVERLAY_ID} .blsm-feature b { display: block; font-size: 12.5px; margin-bottom: 2px; }
      #${OVERLAY_ID} .blsm-feature span { font-size: 11px; color: var(--text-muted, #8b85a0); line-height: 1.45; }

      #${OVERLAY_ID} .blsm-themes { margin-top: 14px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 9px; }
      #${OVERLAY_ID} .blsm-theme { display: flex; align-items: center; gap: 9px; padding: 10px 11px; cursor: pointer;
        border-radius: 12px; border: 1px solid rgba(255,255,255,.1); background: rgba(255,255,255,.03);
        color: var(--text-secondary, #b4adc4); font: inherit; font-size: 12px; font-weight: 600; text-align: left;
        transition: border-color .15s ease, background .15s ease, transform .14s var(--blsm-ease); }
      #${OVERLAY_ID} .blsm-theme:hover { transform: translateY(-1px); border-color: rgba(232,124,192,.4); }
      #${OVERLAY_ID} .blsm-theme .sw { width: 16px; height: 16px; border-radius: 50%; flex-shrink: 0;
        background: var(--sw, #e891a8); box-shadow: 0 0 0 2px rgba(255,255,255,.08); }
      #${OVERLAY_ID} .blsm-theme.is-sel { border-color: var(--sw, #e87cc0); color: #fff;
        background: color-mix(in srgb, var(--sw, #e87cc0) 16%, transparent); }

      #${OVERLAY_ID} .blsm-tips { margin-top: 14px; display: grid; gap: 9px; }
      #${OVERLAY_ID} .blsm-tip { display: flex; gap: 10px; align-items: flex-start; font-size: 12.5px; line-height: 1.5;
        color: var(--text-secondary, #b4adc4); }
      #${OVERLAY_ID} .blsm-tip .ti { color: #e89bd0; font-weight: 800; }

      #${OVERLAY_ID} .blsm-summary { margin-top: 14px; display: grid; gap: 9px; }
      #${OVERLAY_ID} .blsm-summary .item { display: flex; justify-content: space-between; gap: 12px; padding: 11px 14px;
        border-radius: 12px; background: rgba(255,255,255,.035); border: 1px solid rgba(255,255,255,.08); font-size: 13px; }
      #${OVERLAY_ID} .blsm-summary .item span:first-child { color: var(--text-secondary, #b4adc4); }
      #${OVERLAY_ID} .blsm-summary .item b { color: #fff; text-align: right; max-width: 60%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

      #${OVERLAY_ID} .blsm-status { padding: 0 30px; min-height: 17px; font-size: 12px; color: #e89bd0; text-align: center; }
      #${OVERLAY_ID} .blsm-foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 24px 22px; }
      #${OVERLAY_ID} .blsm-btn { border: none; cursor: pointer; font-family: inherit; font-weight: 700; font-size: 13px; padding: 11px 22px;
        border-radius: 12px; transition: transform .14s ease, filter .18s ease, opacity .18s ease; }
      #${OVERLAY_ID} .blsm-btn:hover { transform: translateY(-1px); }
      #${OVERLAY_ID} .blsm-btn[disabled] { opacity: .4; cursor: default; transform: none; }
      #${OVERLAY_ID} .blsm-ghost { background: rgba(255,255,255,.06); color: #ddd2ea; }
      #${OVERLAY_ID} .blsm-ghost:hover { background: rgba(255,255,255,.1); }
      #${OVERLAY_ID} .blsm-primary { background: linear-gradient(180deg, #f0a3d4, #d873b8); color: #2a0f23;
        box-shadow: 0 6px 16px rgba(216,115,184,.28); }
      #${OVERLAY_ID} .blsm-text-link { background: none; border: none; color: var(--text-muted, #8b85a0); cursor: pointer;
        font-family: inherit; font-size: 12px; text-decoration: underline; padding: 6px; }
      #${OVERLAY_ID} .blsm-text-link:hover { color: #ddd2ea; }
      @media (prefers-reduced-motion: reduce) {
        #${OVERLAY_ID} *, #${OVERLAY_ID} *::after { animation: none !important; transition-duration: .01ms !important; }
      }
    `;
    document.head.appendChild(s);
  };

  const close = () => {
    const o = document.getElementById(OVERLAY_ID);
    if (!o) return;
    o.style.animation = "blsm-in .25s ease reverse both";
    setTimeout(() => o.remove(), 220);
    document.removeEventListener("keydown", onKey);
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
    ["midnight", "Blush", "#e891a8"],
    ["lavender", "Lavender", "#a78bfa"],
    ["cyberpunk", "Cyberpunk", "#ec4899"],
    ["ocean", "Ocean", "#0ea5e9"],
    ["arctic", "Arctic", "#38bdf8"],
    ["neon", "Neon", "#22d3ee"],
    ["forest", "Forest", "#22c55e"],
    ["solar", "Solar", "#f59e0b"],
    ["sunset", "Sunset", "#fb7185"],
  ];

  const render = (config) => {
    const wh = firstString(config.webhook_url);
    const curTheme = config.selected_theme || "midnight";
    const themeBtns = THEMES.map(
      ([id, label, sw]) =>
        `<button type="button" class="blsm-theme ${id === curTheme ? "is-sel" : ""}" data-theme-val="${id}" style="--sw:${sw}"><span class="sw"></span>${label}</button>`
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
              <div class="ring blsm-icon">🌸</div>
              <div><h2 style="margin:0">What Blossom does</h2><div class="sub">The main tabs and what they run.</div></div>
            </div>
            <div class="blsm-features blsm-stagger">
              <div class="blsm-feature"><span class="fi">🛒</span><div><b>Auto Merchant</b><span>Teleports, talks & buys from Mari / Jester automatically.</span></div></div>
              <div class="blsm-feature"><span class="fi">📜</span><div><b>Daily Quests</b><span>Claims daily quest rewards for you.</span></div></div>
              <div class="blsm-feature"><span class="fi">🎲</span><div><b>Biome Tools</b><span>Randomizers, Strange Controllers & glitched buffs.</span></div></div>
              <div class="blsm-feature"><span class="fi">⚗️</span><div><b>Potions</b><span>Auto-craft and switch potions while you AFK.</span></div></div>
              <div class="blsm-feature"><span class="fi">🔔</span><div><b>Webhooks</b><span>Discord pings for rare biomes & merchant sightings.</span></div></div>
              <div class="blsm-feature"><span class="fi">⌨️</span><div><b>Hotkeys</b><span>Start / stop instantly with your own keybinds.</span></div></div>
            </div>
          </section>

          <section class="blsm-slide" data-slide="2">
            <div class="blsm-slide-head blsm-stagger">
              <div class="ring blsm-icon">🎨</div>
              <div><h2 style="margin:0">Pick a theme</h2><div class="sub">Click to preview live — change it anytime in the header.</div></div>
            </div>
            <div class="blsm-themes blsm-stagger">${themeBtns}</div>
          </section>

          <section class="blsm-slide" data-slide="3">
            <div class="blsm-slide-head blsm-stagger">
              <div class="ring blsm-icon">🔔</div>
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
              <div class="ring blsm-icon">🎮</div>
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
              <div class="ring blsm-icon">✨</div>
              <div><h2 style="margin:0">Automations</h2><div class="sub">Toggle what runs. Change anytime in the sidebar.</div></div>
            </div>
            <div class="blsm-auto blsm-stagger">
              <div class="blsm-row ${config.merchant_teleporter ? "on" : ""}" data-key="merchant_teleporter">
                <span class="emoji">🛒</span><div class="txt"><b>Auto Merchant</b><span>Teleport, talk & buy from Mari / Jester.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row ${config.auto_claim_daily_quests ? "on" : ""}" data-key="auto_claim_daily_quests">
                <span class="emoji">📜</span><div class="txt"><b>Daily Quests</b><span>Auto-claim daily quest rewards.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row ${config.biome_randomizer ? "on" : ""}" data-key="biome_randomizer">
                <span class="emoji">🎲</span><div class="txt"><b>Biome Randomizer</b><span>Use Biome Randomizers on a timer.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row ${config.biome_selector ? "on" : ""}" data-key="biome_selector">
                <span class="emoji">🧭</span><div class="txt"><b>Biome Selector</b><span>OCR drive list, confirm each enabled row.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row ${config.strange_controller ? "on" : ""}" data-key="strange_controller">
                <span class="emoji">🕹️</span><div class="txt"><b>Strange Controller</b><span>Auto-use Strange Controllers.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row ${config.enable_potion_crafting ? "on" : ""}" data-key="enable_potion_crafting">
                <span class="emoji">⚗️</span><div class="txt"><b>Potion Crafting</b><span>Auto-craft potions from your recipe files.</span></div><div class="blsm-switch"></div>
              </div>
              <div class="blsm-row ${config.enable_auto_obby ? "on" : ""}" data-key="enable_auto_obby">
                <span class="emoji">🏃</span><div class="txt"><b>Auto Obby</b><span>Run a recorded obby path on a timer.</span></div><div class="blsm-switch"></div>
              </div>
            </div>
          </section>

          <section class="blsm-slide" data-slide="6">
            <div class="blsm-slide-head blsm-stagger">
              <div class="ring blsm-icon">💡</div>
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
      selected_theme: overlay.dataset.theme || "midnight",
    };
    overlay.querySelectorAll(".blsm-row").forEach((row) => {
      patch[row.getAttribute("data-key")] = row.classList.contains("on");
    });
    return { webhook, patch };
  };

  const updateSummary = (overlay) => {
    const { webhook, patch } = collect(overlay);
    const yn = (b) => (b ? "On" : "Off");
    const themeLabel = (THEMES.find((t) => t[0] === patch.selected_theme) || [])[1] || patch.selected_theme;
    const rows = [
      ["Theme", themeLabel],
      ["Webhook", webhook ? "Connected" : "Skipped"],
      ["Roblox user", patch.roblox_username || "—"],
      ["Auto Merchant", yn(patch.merchant_teleporter)],
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
        .map(([k, v]) => `<div class="item"><span>${k}</span><b>${esc(v)}</b></div>`)
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
    overlay.style.top = titlebarHeight() + "px";
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
        overlay.querySelectorAll(".blsm-theme").forEach((b) => b.classList.toggle("is-sel", b === themeBtn));
        document.body.setAttribute("data-theme", val); // live preview
        return;
      }
      const row = e.target.closest?.(".blsm-row");
      if (row && overlay.contains(row)) { row.classList.toggle("on"); return; }
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

  if (window.pywebview?.api) boot();
  else window.addEventListener("pywebviewready", boot, { once: true });
})();
