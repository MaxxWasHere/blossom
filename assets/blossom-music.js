(function () {
  const PAGE_ID = "blsm-music-page";
  const NAV_ITEM_ID = "blsm-music-nav-item";
  const NAV_GROUP_ID = "blsm-music-nav-group";
  const LS_KEY = "blsm-music-state-v2";
  // Only these keys are read-merged-written to config. `music_visible` is
  // intentionally excluded: the player is closed by default on every launch,
  // so open/close state is session-only (kept in localStorage, never config).
  const CFG_KEYS = [
    "music_compact",
    "music_volume", "music_muted", "music_rate", "music_loop", "music_shuffle",
    "music_tracks", "music_index", "music_position",
  ];

  const LOOP_MODES = ["off", "all", "one"];
  const RATES = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

  const { observeMain } = window.Blossom || {};
  const icon = (name) => (window.BlossomIcons?.svg ? window.BlossomIcons.svg(name) : "");
  const api = () => window.pywebview?.api;
  const fmtTime = (s) => {
    if (!Number.isFinite(s) || s < 0) s = 0;
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec < 10 ? "0" : ""}${sec}`;
  };
  const uid = () => "t" + Math.random().toString(36).slice(2, 9) + Date.now().toString(36).slice(-4);
  const clamp = (v, min, max) => Math.min(max, Math.max(min, v));
  const reduceMotion = () => document.documentElement.classList.contains("blsm-reduce-motion");

  const DEFAULT_STATE = {
    visible: false,
    compact: false,
    volume: 0.8,
    muted: false,
    rate: 1,
    loop: "off",
    shuffle: false,
    tracks: [],
    index: -1,
    position: 0,
  };

  let state = readLocal();
  let audio = null;
  let pageEl = null;
  let playerEl = null;
  let saveTimer = null;
  let posTimer = null;
  let pageCloseTimer = null;
  let restorePending = false; // resume saved position on first play after launch
  let booted = false; // first init enforces closed-by-default; later inits only re-merge config
  let musicPageOpen = false; // in-app Music page (sidebar category) is showing
  let navObserver = null;

  function readLocal() {
    try {
      return { ...DEFAULT_STATE, ...JSON.parse(localStorage.getItem(LS_KEY) || "{}") };
    } catch { return { ...DEFAULT_STATE }; }
  }
  function writeLocal() { try { localStorage.setItem(LS_KEY, JSON.stringify(state)); } catch {} }

  const saveToBridge = () => {
    if (saveTimer) clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      const bridge = api();
      if (!bridge?.get_config || !bridge?.save_config) return;
      try {
        const cfg = await bridge.get_config();
        const patch = {};
        for (const k of CFG_KEYS) patch[k] = state[k];
        await bridge.save_config({ ...cfg, ...patch });
      } catch (e) { console.warn("[music] save failed:", e); }
    }, 500);
  };
  const persist = () => { writeLocal(); saveToBridge(); };

  function mergeFromConfig(cfg) {
    if (!cfg || typeof cfg !== "object") return;
    let changed = false;
    if (Array.isArray(cfg.music_tracks)) {
      state.tracks = cfg.music_tracks
        .filter((t) => t && typeof t.url === "string")
        .map((t) => ({ id: t.id || uid(), title: String(t.title || "").trim() || guessTitle(t.url), url: t.url }));
      changed = true;
    }
    for (const k of ["music_compact", "music_muted", "music_shuffle"]) {
      if (typeof cfg[k] === "boolean") { state[k.replace("music_", "")] = cfg[k]; changed = true; }
    }
    if (typeof cfg.music_volume === "number") { state.volume = clamp(cfg.music_volume, 0, 1); changed = true; }
    if (typeof cfg.music_rate === "number" && RATES.includes(cfg.music_rate)) { state.rate = cfg.music_rate; changed = true; }
    if (LOOP_MODES.includes(cfg.music_loop)) { state.loop = cfg.music_loop; changed = true; }
    if (Number.isInteger(cfg.music_index)) { state.index = clamp(cfg.music_index, -1, state.tracks.length - 1); changed = true; }
    if (typeof cfg.music_position === "number") { state.position = Math.max(0, cfg.music_position); changed = true; }
    if (changed) writeLocal();
  }

  function guessTitle(url) {
    try {
      const u = new URL(url, "http://x/");
      const last = u.pathname.split("/").filter(Boolean).pop() || url;
      return decodeURIComponent(last).replace(/\.[a-z0-9]+$/i, "").replace(/[_]+/g, " ").trim() || url;
    } catch { return url; }
  }
  function isLocalPath(s) {
    return /^(?:[a-zA-Z]:\\|\\\\|\/|~)/.test(s) ||
      (!/^https?:\/\//i.test(s) && /\.[a-z0-9]{2,5}$/i.test(s) && !/^data:/i.test(s));
  }

  // ---------- Audio ----------
  function ensureAudio() {
    if (audio) return audio;
    audio = new Audio();
    audio.preload = "metadata";
    audio.volume = state.muted ? 0 : state.volume;
    audio.playbackRate = state.rate;
    audio.loop = false;
    audio.addEventListener("loadedmetadata", () => { renderTimes(); setSeekBg(); });
    audio.addEventListener("timeupdate", () => { renderTimes(); setSeekBg(); savePositionSoft(); });
    audio.addEventListener("ended", () => onEnded());
    audio.addEventListener("play", () => { updatePlayIcon(); });
    audio.addEventListener("pause", () => { updatePlayIcon(); savePositionHard(); });
    audio.addEventListener("error", () => { console.warn("[music] audio error", audio.error); });
    return audio;
  }

  const dataUrlCache = new Map();
  async function resolveSrc(track) {
    if (!track) return "";
    if (/^https?:\/\//i.test(track.url) || /^data:/i.test(track.url)) return track.url;
    if (dataUrlCache.has(track.url)) return dataUrlCache.get(track.url);
    const bridge = api();
    if (bridge?.audio_file_data_url) {
      try {
        const res = await bridge.audio_file_data_url(track.url);
        if (res?.ok && res.dataUrl) {
          dataUrlCache.set(track.url, res.dataUrl);
          if (dataUrlCache.size > 8) dataUrlCache.delete(dataUrlCache.keys().next().value);
          return res.dataUrl;
        }
        console.warn("[music] local resolve failed:", res?.error);
      } catch (e) { console.warn("[music] local resolve error:", e); }
    }
    return track.url;
  }

  async function loadCurrent({ autoplay = false, restorePos = false } = {}) {
    const a = ensureAudio();
    const track = state.tracks[state.index];
    if (!track) { a.removeAttribute("src"); a.load(); renderNow(); return; }
    const src = await resolveSrc(track);
    a.src = src;
    a.playbackRate = state.rate;
    if (restorePos && state.position > 0) {
      a.addEventListener("loadedmetadata", () => {
        try { a.currentTime = state.position; } catch {}
        state.position = 0;
      }, { once: true });
    }
    renderNow();
    if (autoplay) void play();
  }

  async function play() {
    const a = ensureAudio();
    // First play after launch: load the restored track and seek to saved position.
    if (restorePending) {
      restorePending = false;
      if (state.tracks.length) { await loadCurrent({ autoplay: true, restorePos: true }); return; }
    }
    if (!a.src && state.tracks.length) { await loadCurrent({ autoplay: true }); return; }
    if (!a.src) return;
    try { await a.play(); } catch (e) { console.warn("[music] play blocked:", e); }
  }
  function pause() { ensureAudio().pause(); }
  function togglePlay() { if (audio?.paused) play(); else pause(); }

  function onEnded() {
    if (state.loop === "one") { loadCurrent({ autoplay: true }); return; }
    next({ auto: true });
  }

  function next({ auto = false } = {}) {
    if (!state.tracks.length) return;
    if (state.shuffle && state.tracks.length > 1) {
      let idx = state.index;
      while (idx === state.index) idx = Math.floor(Math.random() * state.tracks.length);
      state.index = idx;
    } else {
      state.index = state.index + 1;
      if (state.index >= state.tracks.length) state.index = 0;
    }
    state.position = 0;
    persist();
    const keepPlaying = auto || !audio?.paused || state.loop !== "off";
    loadCurrent({ autoplay: keepPlaying });
    renderList();
  }
  function prev() {
    if (!state.tracks.length) return;
    if (audio && audio.currentTime > 3) { try { audio.currentTime = 0; } catch {} return; }
    state.index = state.index - 1;
    if (state.index < 0) state.index = state.tracks.length - 1;
    state.position = 0;
    persist();
    loadCurrent({ autoplay: !audio?.paused });
    renderList();
  }
  function playIndex(i) {
    if (i < 0 || i >= state.tracks.length) return;
    state.index = i; state.position = 0; persist();
    loadCurrent({ autoplay: true }); renderList();
  }
  function removeTrack(i) {
    if (i < 0 || i >= state.tracks.length) return;
    state.tracks.splice(i, 1);
    if (state.index === i) {
      state.index = Math.min(i, state.tracks.length - 1);
      state.position = 0;
      loadCurrent({ autoplay: !audio?.paused });
    } else if (state.index > i) {
      state.index -= 1;
    }
    persist(); renderList(); renderNow();
  }
  function moveTrack(i, dir) {
    const j = i + dir;
    if (j < 0 || j >= state.tracks.length) return;
    const [t] = state.tracks.splice(i, 1);
    state.tracks.splice(j, 0, t);
    if (state.index === i) state.index = j;
    else if (state.index === j) state.index = i;
    persist(); renderList();
  }
  function addTrack(title, url) {
    const u = String(url || "").trim();
    if (!u) return false;
    state.tracks.push({ id: uid(), title: String(title || "").trim() || guessTitle(u), url: u });
    persist(); renderList();
    if (state.index < 0) { state.index = 0; persist(); loadCurrent({ autoplay: false }); renderNow(); }
    return true;
  }
  function clearAll() {
    pause();
    state.tracks = []; state.index = -1; state.position = 0;
    if (audio) { audio.removeAttribute("src"); audio.load(); }
    persist(); renderList(); renderNow();
  }

  let lastPosSave = 0;
  function savePositionSoft() {
    if (!audio) return;
    const now = Date.now();
    if (now - lastPosSave < 4000) return;
    lastPosSave = now;
    state.position = audio.currentTime || 0; writeLocal();
  }
  function savePositionHard() { if (!audio) return; state.position = audio.currentTime || 0; persist(); }

  // ---------- Shared player body: lives inside the in-app page ----------
  function mountPlayer(host) {
    if (!playerEl || !host) return;
    const slot = host.querySelector("[data-slot]");
    if (slot && playerEl.parentElement !== slot) slot.appendChild(playerEl);
  }

  // ---------- Open / close (in-app page via sidebar category) ----------
  function ensurePageMounted() {
    if (!pageEl) return;
    const main = document.querySelector(".main-content") || document.querySelector(".page-content");
    const host = main || document.body;
    if (pageEl.parentElement !== host) host.appendChild(pageEl);
  }
  function setMusicItemActive(on) {
    const it = document.getElementById(NAV_ITEM_ID);
    if (!it) return;
    it.classList.toggle("active", on);
    it.classList.toggle("is-active", on);
    if (on) it.setAttribute("aria-current", "page"); else it.removeAttribute("aria-current");
  }
  function openPage() {
    if (musicPageOpen) return;
    build();
    ensurePageMounted();
    mountPlayer(pageEl);
    // Take over sidebar selection visually: the html class deactivates real
    // items via CSS (so we never fight React's active state on them), and we
    // mark the injected Music item active. The existing nav motion listener
    // plays the spring select on this item + eased deselect on the previous.
    setMusicItemActive(true);
    pageEl.style.display = "flex";
    document.documentElement.classList.add("blsm-music-page-active");
    musicPageOpen = true;
    if (reduceMotion()) {
      pageEl.classList.add("is-open");
    } else {
      requestAnimationFrame(() => requestAnimationFrame(() => pageEl.classList.add("is-open")));
    }
  }
  function closePage() {
    if (!musicPageOpen) return;
    musicPageOpen = false;
    setMusicItemActive(false);
    pageEl?.classList.remove("is-open");
    if (pageCloseTimer) clearTimeout(pageCloseTimer);
    const finish = () => {
      if (pageEl) pageEl.style.display = "none";
      document.documentElement.classList.remove("blsm-music-page-active");
    };
    if (reduceMotion() || !pageEl) { finish(); return; }
    pageCloseTimer = setTimeout(finish, 340);
  }

  // ---------- Music sidebar category (injected, self-healing) ----------
  function ensureMusicNav() {
    ensureNavMusicItem();
    startNavObserver();
    startNavClickListener();
  }
  function ensureNavMusicItem() {
    const nav = document.querySelector(".sidebar-nav");
    if (!nav) return;
    if (document.getElementById(NAV_ITEM_ID)) return;
    let group = nav.querySelector(":scope > #" + NAV_GROUP_ID);
    if (!group) {
      group = document.createElement("div");
      group.className = "sidebar-group";
      group.id = NAV_GROUP_ID;
      nav.appendChild(group);
      const groups = nav.querySelectorAll(":scope > .sidebar-group");
      group.style.setProperty("--blsm-nav-stagger", String(Math.max(0, groups.length - 1)));
    }
    const item = document.createElement("button");
    item.type = "button";
    item.id = NAV_ITEM_ID;
    item.className = "sidebar-item";
    item.innerHTML = `<span class="icon">${icon("music-note")}</span><span class="label">Music</span>`;
    item.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (musicPageOpen) closePage();
      else openPage();
    });
    group.appendChild(item);
  }
  function startNavObserver() {
    const nav = document.querySelector(".sidebar-nav");
    if (!nav || nav.dataset.blsmMusicWatch === "1") return;
    nav.dataset.blsmMusicWatch = "1";
    navObserver = new MutationObserver(() => {
      if (!document.getElementById(NAV_ITEM_ID)) requestAnimationFrame(ensureNavMusicItem);
    });
    navObserver.observe(nav, { childList: true, subtree: true });
  }
  // Detect navigation to another category while the Music page is open: a click
  // on any real sidebar item closes the page (React routes normally).
  function startNavClickListener() {
    const nav = document.querySelector(".sidebar-nav");
    if (!nav || nav.dataset.blsmMusicNavClick === "1") return;
    nav.dataset.blsmMusicNavClick = "1";
    nav.addEventListener("click", (e) => {
      const item = e.target.closest?.(".sidebar-item");
      if (!item || item.id === NAV_ITEM_ID) return;
      if (musicPageOpen) closePage();
    }, true);
  }

  // ---------- Build DOM ----------
  function build() {
    if (pageEl?.isConnected && playerEl?.isConnected) return;

    if (!pageEl?.isConnected) {
      pageEl = document.getElementById(PAGE_ID) || document.createElement("div");
      pageEl.id = PAGE_ID;
      pageEl.style.display = "none";
      pageEl.innerHTML = `
        <div class="blsm-music-page-head">
          <span class="blsm-music-page-icon">${icon("music-note")}</span>
          <div class="blsm-music-page-titles">
            <div class="blsm-music-page-title">Music</div>
            <div class="blsm-music-page-sub">Blossom player</div>
          </div>
          <button class="blsm-music-page-close" data-act="page-close" title="Close music page">${icon("close")}</button>
        </div>
        <div class="blsm-music-slot" data-slot></div>
      `;
      if (!pageEl.isConnected) (document.querySelector(".main-content") || document.body).appendChild(pageEl);
      wireHost(pageEl, { "page-close": () => closePage() });
    }

    if (!playerEl?.isConnected) {
      playerEl = document.createElement("div");
      playerEl.className = "blsm-music-body";
      playerEl.innerHTML = `
        <div class="blsm-music-now">
          <div class="blsm-music-art"><span>${icon("music-note")}</span></div>
          <div class="blsm-music-meta">
            <div class="blsm-music-track is-empty">No track loaded</div>
            <div class="blsm-music-sub">Add a song below to begin</div>
          </div>
        </div>
        <div class="blsm-music-seek">
          <input type="range" min="0" max="1000" value="0" step="1" data-seek />
          <div class="blsm-music-times"><span data-cur>0:00</span><span data-dur>0:00</span></div>
        </div>
        <div class="blsm-music-transport">
          <button class="blsm-music-btn" data-act="shuffle" title="Shuffle">${icon("shuffle")}</button>
          <button class="blsm-music-btn" data-act="prev" title="Previous">${icon("skip-back")}</button>
          <button class="blsm-music-btn is-primary" data-act="play" title="Play/Pause">${icon("play")}</button>
          <button class="blsm-music-btn" data-act="next" title="Next">${icon("skip-forward")}</button>
          <button class="blsm-music-btn" data-act="loop" title="Repeat">${icon("repeat")}</button>
        </div>
        <div class="blsm-music-options">
          <div class="blsm-music-vol">
            <button class="blsm-music-vol-btn" data-act="mute" title="Mute">${icon("volume")}</button>
            <input type="range" min="0" max="100" value="80" data-vol />
          </div>
          <select class="blsm-music-rate" data-rate title="Playback speed">
            ${RATES.map((r) => `<option value="${r}">${r}×</option>`).join("")}
          </select>
        </div>
        <div class="blsm-music-collapsible">
          <div class="blsm-music-collapsible-inner">
            <div class="blsm-music-list-wrap">
              <div class="blsm-music-list-head">
                <span>Playlist</span><span class="blsm-music-count" data-count>0</span>
              </div>
              <div class="blsm-music-list" data-list></div>
            </div>
            <div class="blsm-music-add">
              <div class="blsm-music-add-row">
                <input type="text" data-title placeholder="Title (optional)" />
              </div>
              <div class="blsm-music-add-row">
                <input type="text" data-url placeholder="Paste URL or local file path" />
                <button class="blsm-music-add-btn" data-act="browse" title="Browse local audio file">${icon("folder")}</button>
              </div>
              <div class="blsm-music-add-row">
                <button class="blsm-music-add-btn is-primary" data-act="add">${icon("plus")} Add to playlist</button>
                <button class="blsm-music-add-btn" data-act="clear" title="Clear playlist">${icon("trash")}</button>
              </div>
              <p class="blsm-music-hint">Stream from the web (https), or browse a local audio file. Volume, speed, shuffle and repeat are saved to your config and persist across launches.</p>
            </div>
          </div>
        </div>
      `;
      mountPlayer(pageEl);
      wirePlayer();
    }
  }

  // Host-level (page header) buttons: only act on their own data-acts,
  // ignoring body acts that bubble up from the shared playerEl.
  function wireHost(host, handlers) {
    host.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-act]");
      if (!btn) return;
      const fn = handlers[btn.dataset.act];
      if (fn) { e.stopPropagation(); fn(); }
    });
  }

  function wirePlayer() {
    playerEl.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-act]");
      if (!btn) return;
      const act = btn.dataset.act;
      if (act === "play") togglePlay();
      else if (act === "next") next();
      else if (act === "prev") prev();
      else if (act === "shuffle") { state.shuffle = !state.shuffle; persist(); renderOptions(); }
      else if (act === "loop") { state.loop = LOOP_MODES[(LOOP_MODES.indexOf(state.loop) + 1) % LOOP_MODES.length]; persist(); renderOptions(); }
      else if (act === "mute") { state.muted = !state.muted; applyVolume(); persist(); renderOptions(); }
      else if (act === "add") doAdd();
      else if (act === "clear") { if (confirm("Clear the whole playlist?")) clearAll(); }
      else if (act === "browse") void browse();
    });

    playerEl.querySelector("[data-seek]").addEventListener("input", (e) => {
      if (!audio || !audio.duration) return;
      audio.currentTime = (e.target.value / 1000) * audio.duration;
    });
    const vol = playerEl.querySelector("[data-vol]");
    vol.addEventListener("input", (e) => {
      state.volume = e.target.value / 100; state.muted = false; applyVolume(); persist(); renderOptions();
    });
    playerEl.querySelector("[data-rate]").addEventListener("change", (e) => {
      state.rate = Number(e.target.value);
      if (audio) audio.playbackRate = state.rate;
      persist();
    });
    playerEl.querySelector("[data-url]").addEventListener("keydown", (e) => { if (e.key === "Enter") doAdd(); });
    playerEl.querySelector("[data-title]").addEventListener("keydown", (e) => { if (e.key === "Enter") playerEl.querySelector("[data-url]").focus(); });

    playerEl.querySelector("[data-list]").addEventListener("click", (e) => {
      const item = e.target.closest("[data-idx]");
      if (!item) return;
      const idx = Number(item.dataset.idx);
      const actBtn = e.target.closest("[data-item-act]");
      if (actBtn) {
        const a = actBtn.dataset.itemAct;
        if (a === "up") moveTrack(idx, -1);
        else if (a === "down") moveTrack(idx, 1);
        else if (a === "remove") removeTrack(idx);
        return;
      }
      playIndex(idx);
    });
  }

  function doAdd() {
    const titleIn = playerEl.querySelector("[data-title]");
    const urlIn = playerEl.querySelector("[data-url]");
    if (addTrack(titleIn.value, urlIn.value)) { titleIn.value = ""; urlIn.value = ""; urlIn.focus(); }
  }
  async function browse() {
    const bridge = api();
    if (!bridge?.pick_audio_file) return;
    try {
      const res = await bridge.pick_audio_file();
      if (res?.ok && res.path) {
        playerEl.querySelector("[data-url]").value = res.path;
        const titleIn = playerEl.querySelector("[data-title]");
        if (!titleIn.value) titleIn.value = guessTitle(res.path);
        titleIn.focus();
      }
    } catch (e) { console.warn("[music] browse failed:", e); }
  }
  function applyVolume() { ensureAudio().volume = state.muted ? 0 : state.volume; }

  // ---------- Render ----------
  function renderOptions() {
    playerEl?.querySelector('[data-act="shuffle"]').classList.toggle("is-active", state.shuffle);
    const loopBtn = playerEl?.querySelector('[data-act="loop"]');
    if (loopBtn) {
      loopBtn.classList.toggle("is-active", state.loop !== "off");
      loopBtn.innerHTML = icon(state.loop === "one" ? "repeat-one" : "repeat");
      loopBtn.title = "Repeat: " + state.loop;
    }
    const muteBtn = playerEl?.querySelector('[data-act="mute"]');
    if (muteBtn) {
      const muted = state.muted || state.volume === 0;
      muteBtn.innerHTML = icon(muted ? "volume-mute" : "volume");
      muteBtn.title = muted ? "Unmute" : "Mute";
    }
    const volEl = playerEl?.querySelector("[data-vol]");
    if (volEl) volEl.value = Math.round(state.volume * 100);
    const rateEl = playerEl?.querySelector("[data-rate]");
    if (rateEl) rateEl.value = String(state.rate);
    setVolBg();
  }
  function updatePlayIcon() {
    const playing = !audio?.paused && !audio?.ended;
    const ic = icon(playing ? "pause" : "play");
    const playBtn = playerEl?.querySelector('.blsm-music-transport [data-act="play"]');
    if (playBtn) playBtn.innerHTML = ic;
    playerEl?.querySelector(".blsm-music-art")?.classList.toggle("is-spin", playing);
  }
  function renderNow() {
    const track = state.tracks[state.index];
    const titleEl = playerEl?.querySelector(".blsm-music-track");
    const subEl = playerEl?.querySelector(".blsm-music-sub");
    if (!titleEl || !subEl) return;
    if (track) {
      titleEl.textContent = track.title;
      titleEl.classList.remove("is-empty");
      subEl.textContent = isLocalPath(track.url) ? "Local file" : track.url;
    } else {
      titleEl.textContent = state.tracks.length ? "Pick a track" : "No track loaded";
      titleEl.classList.add("is-empty");
      subEl.textContent = state.tracks.length ? "Choose from the playlist below" : "Add a song below to begin";
    }
    updatePlayIcon();
    renderTimes();
  }
  function renderTimes() {
    const cur = playerEl?.querySelector("[data-cur]");
    const dur = playerEl?.querySelector("[data-dur]");
    if (cur) cur.textContent = fmtTime(audio?.currentTime || 0);
    if (dur) dur.textContent = fmtTime(audio?.duration || 0);
    setSeekBg();
  }
  function setSeekBg() {
    const seek = playerEl?.querySelector("[data-seek]");
    if (!seek) return;
    if (!audio || !audio.duration) { seek.value = 0; seek.style.backgroundSize = "0% 100%"; return; }
    seek.value = Math.min(1000, (audio.currentTime / audio.duration) * 1000);
    seek.style.backgroundSize = `${(seek.value / 1000) * 100}% 100%`;
  }
  function setVolBg() {
    const v = playerEl?.querySelector("[data-vol]");
    if (v) v.style.backgroundSize = `${state.muted ? 0 : state.volume * 100}% 100%`;
  }
  function renderList() {
    const list = playerEl?.querySelector("[data-list]");
    const count = playerEl?.querySelector("[data-count]");
    if (count) count.textContent = String(state.tracks.length);
    if (!list) return;
    if (!state.tracks.length) {
      list.innerHTML = `<div class="blsm-music-empty">Playlist is empty — add a URL or browse a local file.</div>`;
      return;
    }
    list.innerHTML = state.tracks
      .map((t, i) => `
        <div class="blsm-music-item ${i === state.index ? "is-current" : ""}" data-idx="${i}">
          <span class="blsm-music-item-index">${i === state.index ? icon("volume") : (i + 1)}</span>
          <div class="blsm-music-item-meta">
            <div class="blsm-music-item-title">${escapeHtml(t.title)}</div>
            <div class="blsm-music-item-src">${escapeHtml(isLocalPath(t.url) ? "Local file" : t.url)}</div>
          </div>
          <div class="blsm-music-item-actions">
            <button class="blsm-music-item-act" data-item-act="up" title="Move up">${icon("chevron-up")}</button>
            <button class="blsm-music-item-act" data-item-act="down" title="Move down">${icon("chevron-down")}</button>
            <button class="blsm-music-item-act" data-item-act="remove" title="Remove">${icon("trash")}</button>
          </div>
        </div>`)
      .join("");
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function renderAll() { renderOptions(); renderList(); renderNow(); applyVolume(); }

  // ---------- Boot ----------
  async function init() {
    build();
    ensureAudio();
    ensureMusicNav();
    const bridge = api();
    if (bridge?.get_config) {
      try { mergeFromConfig(await bridge.get_config()); } catch (e) { console.warn("[music] config load failed:", e); }
    }
    if (!booted) {
      // First init (runs at DOMContentLoaded, then again on pywebviewready with
      // the real config). Enforce closed-by-default exactly once, and set up
      // lazy position restore. Later inits only re-merge config + re-render, so
      // a page the user opened between the two is never yanked away.
      state.visible = false;
      musicPageOpen = false;
      writeLocal();
      restorePending = !!(state.tracks.length && state.index >= 0 && state.position > 0);
      booted = true;
    }
    // Playlist + last track are already in `state` from config/localStorage, so
    // the list is populated when the user opens the page. We do NOT load
    // audio on launch (no auto-play, no local-file read until the user plays);
    // the saved position resumes on the first play via `restorePending`.
    renderAll();
  }
  function boot() {
    void init();
    if (!posTimer) posTimer = setInterval(savePositionSoft, 5000);
    window.addEventListener("beforeunload", savePositionHard);
    if (observeMain) observeMain(ensureMusicNav, 0);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
  window.addEventListener("pywebviewready", () => void init());
})();
