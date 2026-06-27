(function () {
  const LAYER_ID = "blsm-bg-layer";
  const CARD_ID = "blsm-bg-card";
  const PAGE = "Appearance";
  const LS_KEY = "blsm-bg-state-v1";
  const HTML_ACTIVE = "blsm-bg-active";
  const CFG_MAP = {
    bg_enabled: "enabled",
    bg_preset: "preset",
    bg_opacity: "opacity",
    bg_blur: "blur",
    bg_speed: "speed",
    bg_scrim: "scrim",
    bg_media_url: "mediaUrl",
    bg_media_path: "mediaPath",
  };

  const PRESETS = ["none", "aurora", "mesh", "stars", "bubbles", "custom-media"];
  const PRESET_LABELS = {
    none: "None",
    aurora: "Aurora",
    mesh: "Mesh",
    stars: "Stars",
    bubbles: "Bubbles",
    "custom-media": "Custom media",
  };
  const SPEEDS = { slow: 44, normal: 26, fast: 14 };
  const MEDIA_RATES = { slow: 0.5, normal: 1, fast: 1.5 };
  const VIDEO_EXTS = ["mp4", "webm", "ogg", "ogv", "mov", "mkv"];
  const IMAGE_EXTS = ["gif", "png", "jpg", "jpeg", "webp", "apng", "bmp", "svg"];

  const { observeMain, pageHeaderTitle } = window.Blossom || {};
  const api = () => window.pywebview?.api;

  const DEFAULT_STATE = {
    enabled: false,
    preset: "aurora",
    opacity: 0.55,
    blur: 0,
    speed: "normal",
    scrim: 0.5,
    mediaUrl: "",
    mediaPath: "",
  };

  let state = readLocal();
  let layer = null;
  let saveTimer = null;

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
        for (const [cfgKey, stateKey] of Object.entries(CFG_MAP)) patch[cfgKey] = state[stateKey];
        await bridge.save_config({ ...cfg, ...patch });
      } catch (e) { console.warn("[bg] save failed:", e); }
    }, 500);
  };
  const persist = () => { writeLocal(); saveToBridge(); };

  function mergeFromConfig(cfg) {
    if (!cfg || typeof cfg !== "object") return;
    let changed = false;
    if (typeof cfg.bg_enabled === "boolean") { state.enabled = cfg.bg_enabled; changed = true; }
    if (PRESETS.includes(cfg.bg_preset)) { state.preset = cfg.bg_preset; changed = true; }
    if (typeof cfg.bg_opacity === "number") { state.opacity = clamp(cfg.bg_opacity, 0, 1); changed = true; }
    if (typeof cfg.bg_blur === "number") { state.blur = clamp(cfg.bg_blur, 0, 24); changed = true; }
    if (SPEEDS[cfg.bg_speed]) { state.speed = cfg.bg_speed; changed = true; }
    if (typeof cfg.bg_scrim === "number") { state.scrim = clamp(cfg.bg_scrim, 0, 1); changed = true; }
    if (typeof cfg.bg_media_url === "string") { state.mediaUrl = cfg.bg_media_url; changed = true; }
    if (typeof cfg.bg_media_path === "string") { state.mediaPath = cfg.bg_media_path; changed = true; }
    if (changed) writeLocal();
  }
  const clamp = (v, min, max) => Math.min(max, Math.max(min, v));

  function ensureLayer() {
    if (layer && layer.isConnected) return layer;
    layer = document.createElement("div");
    layer.id = LAYER_ID;
    document.body.insertBefore(layer, document.body.firstChild);
    return layer;
  }

  function buildChildren() {
    if (!layer) return;
    layer.innerHTML = "";
    const p = state.preset;
    if (p === "mesh") {
      const colors = [
        "color-mix(in srgb, var(--accent, #e891a8) 90%, transparent)",
        "color-mix(in srgb, #6d8bff 90%, transparent)",
        "color-mix(in srgb, #b06dff 90%, transparent)",
        "color-mix(in srgb, #2ee6a8 85%, transparent)",
      ];
      const anims = ["blsm-bg-blob-a", "blsm-bg-blob-b", "blsm-bg-blob-c", "blsm-bg-blob-a"];
      const spots = [[8, 12, 30], [60, 18, 26], [30, 60, 34], [78, 70, 28]];
      colors.forEach((c, i) => {
        const b = document.createElement("div");
        b.className = "blsm-bg-blob";
        const [l, t, sz] = spots[i];
        b.style.cssText = `left:${l}vw;top:${t}vh;width:${sz}vw;height:${sz}vw;background:${c};animation:${anims[i]} calc(var(--blsm-bg-dur, 26s) * ${1 + i * 0.25}) ease-in-out infinite alternate;`;
        layer.appendChild(b);
      });
    } else if (p === "bubbles") {
      const n = 16;
      for (let i = 0; i < n; i++) {
        const bub = document.createElement("div");
        bub.className = "blsm-bg-bubble";
        const size = 6 + Math.random() * 22;
        const left = Math.random() * 100;
        const dur = (SPEEDS[state.speed] || 26) * (0.6 + Math.random() * 0.9);
        const delay = -Math.random() * dur;
        bub.style.cssText = `left:${left}vw;width:${size}px;height:${size}px;animation-duration:${dur}s;animation-delay:${delay}s;`;
        layer.appendChild(bub);
      }
    } else if (p === "stars") {
      layer.style.setProperty("--blsm-bg-stars", makeStars());
      layer.style.setProperty("--blsm-bg-stars-size", "360px 360px");
    }
  }

  function makeStars() {
    const dots = [];
    for (let i = 0; i < 40; i++) {
      const x = Math.floor(Math.random() * 360);
      const y = Math.floor(Math.random() * 360);
      const a = 0.4 + Math.random() * 0.6;
      dots.push(`radial-gradient(1.4px 1.4px at ${x}px ${y}px, rgba(255,255,255,${a.toFixed(2)}), transparent)`);
    }
    return dots.join(",");
  }

  function extOf(src) {
    const clean = String(src || "").split("?")[0].split("#")[0];
    const dot = clean.lastIndexOf(".");
    const slash = clean.lastIndexOf("/");
    if (dot <= slash) return "";
    return clean.slice(dot + 1).toLowerCase();
  }

  function guessMediaKind(src) {
    const ext = extOf(src);
    if (VIDEO_EXTS.includes(ext)) return "video";
    if (IMAGE_EXTS.includes(ext)) return "image";
    return "video";
  }

  let mediaBuildId = 0;
  async function buildMedia() {
    if (!layer) return;
    const myId = ++mediaBuildId;
    layer.innerHTML = "";
    const resolved = await resolveMediaSource();
    if (!resolved || myId !== mediaBuildId || !layer) return;
    layer.innerHTML = "";
    const reduce = document.documentElement.classList.contains("blsm-reduce-motion");
    if (resolved.kind === "image") {
      const img = document.createElement("img");
      img.className = "blsm-bg-media";
      img.src = resolved.url;
      img.alt = "";
      img.draggable = false;
      layer.appendChild(img);
      return;
    }
    const video = document.createElement("video");
    video.className = "blsm-bg-media";
    video.src = resolved.url;
    video.muted = true;
    video.loop = true;
    video.playsInline = true;
    video.autoplay = true;
    video.playbackRate = MEDIA_RATES[state.speed] || 1;
    video.addEventListener("error", () => {
      if (myId !== mediaBuildId || !layer || !layer.contains(video)) return;
      video.remove();
      const img = document.createElement("img");
      img.className = "blsm-bg-media";
      img.src = resolved.url;
      img.alt = "";
      img.draggable = false;
      layer.appendChild(img);
    });
    layer.appendChild(video);
    if (reduce) { video.pause(); }
    else { try { void video.play(); } catch {} }
  }

  async function resolveMediaSource() {
    const url = String(state.mediaUrl || "").trim();
    if (/^https?:\/\//i.test(url)) {
      return { url, kind: guessMediaKind(url) };
    }
    const path = String(state.mediaPath || url || "").trim();
    if (!path) return null;
    const bridge = api();
    if (!bridge?.bg_media_url) return null;
    try {
      const res = await bridge.bg_media_url(path);
      if (res?.ok && res.url) return { url: res.url, kind: res.kind || guessMediaKind(path) };
      console.warn("[bg] bg_media_url failed:", res?.error);
    } catch (e) { console.warn("[bg] bg_media_url error:", e); }
    return null;
  }

  function apply() {
    const l = ensureLayer();
    const on = state.enabled && state.preset !== "none";
    document.documentElement.classList.toggle(HTML_ACTIVE, on);
    l.style.setProperty("--blsm-bg-opacity", String(state.opacity));
    l.style.setProperty("--blsm-bg-blur", `${state.blur}px`);
    l.style.setProperty("--blsm-bg-scrim", String(state.scrim));
    l.style.setProperty("--blsm-bg-dur", `${SPEEDS[state.speed] || 26}s`);
    PRESETS.forEach((p) => l.classList.remove(`blsm-bg-${p}`));
    if (!on || state.preset !== "custom-media") mediaBuildId++;
    if (on) {
      l.classList.add(`blsm-bg-${state.preset}`);
      if (state.preset === "custom-media") {
        void buildMedia();
      } else {
        buildChildren();
      }
    } else {
      l.innerHTML = "";
    }
    refreshCardFields();
  }

  // ---------- Settings card ----------
  function buildCard() {
    const card = document.createElement("div");
    card.id = CARD_ID;
    card.className = "card blsm-appearance-card";
    card.innerHTML = `
      <div class="card-header blsm-appearance-header">
        <div class="card-icon">🌌</div>
        <div>
          <h3>Animated background</h3>
          <p>Live wallpaper behind the app — pick a preset, then tune opacity and blur.</p>
        </div>
      </div>
      <div class="blsm-appearance-body">
        <div class="blsm-bg-toggle">
          <input type="checkbox" id="blsm-bg-enable" />
          <label for="blsm-bg-enable"><b>Enable animated background</b></label>
        </div>
        <div class="blsm-bg-section">
          <div class="blsm-bg-row">
            <label for="blsm-bg-preset">Preset</label>
            <select id="blsm-bg-preset" class="blsm-bg-select">
              ${PRESETS.map((p) => `<option value="${p}">${PRESET_LABELS[p] || cap(p)}</option>`).join("")}
            </select>
          </div>
          <div class="blsm-bg-row blsm-bg-media-row" data-media-row hidden>
            <label for="blsm-bg-media-url">Source</label>
            <input type="text" id="blsm-bg-media-url" class="blsm-bg-input" placeholder="https://… video, gif or image URL" autocomplete="off" spellcheck="false" />
            <button type="button" class="btn btn-secondary" data-bg-browse>Browse</button>
            <button type="button" class="btn btn-secondary" data-bg-clear>Clear</button>
          </div>
          <p class="blsm-bg-media-status" data-media-status hidden></p>
          <div class="blsm-bg-row">
            <label for="blsm-bg-opacity">Opacity</label>
            <input type="range" id="blsm-bg-opacity" class="blsm-bg-range" min="0" max="100" step="1" />
            <span class="blsm-bg-val" data-val="opacity">55%</span>
          </div>
          <div class="blsm-bg-row">
            <label for="blsm-bg-blur">Blur</label>
            <input type="range" id="blsm-bg-blur" class="blsm-bg-range" min="0" max="20" step="1" />
            <span class="blsm-bg-val" data-val="blur">0px</span>
          </div>
          <div class="blsm-bg-row">
            <label for="blsm-bg-scrim">Dim</label>
            <input type="range" id="blsm-bg-scrim" class="blsm-bg-range" min="0" max="100" step="1" />
            <span class="blsm-bg-val" data-val="scrim">50%</span>
          </div>
          <div class="blsm-bg-row">
            <label>Speed</label>
            <div class="blsm-bg-seg" data-speed>
              <button type="button" data-speed-val="slow">Slow</button>
              <button type="button" data-speed-val="normal">Normal</button>
              <button type="button" data-speed-val="fast">Fast</button>
            </div>
          </div>
          <p class="blsm-bg-hint">Pick a built-in preset, or choose <b>Custom media</b> to use your own video, gif or image (paste a web URL or Browse a local file). Lower opacity or raise Dim if text gets hard to read. Reduces to a static frame when Appearance → Reduce motion is on (videos pause). The background sits behind cards, the toolbar, inputs and sidebar items, so most surfaces stay solid.</p>
        </div>
      </div>
    `;
    wireCard(card);
    return card;
  }

  function cap(s) { return s.charAt(0).toUpperCase() + s.slice(1); }

  function wireCard(card) {
    card.querySelector("#blsm-bg-enable").addEventListener("change", (e) => {
      state.enabled = !!e.target.checked; persist(); apply();
    });
    card.querySelector("#blsm-bg-preset").addEventListener("change", (e) => {
      state.preset = e.target.value; persist(); apply();
    });
    const op = card.querySelector("#blsm-bg-opacity");
    op.addEventListener("input", (e) => {
      state.opacity = e.target.value / 100; apply(); persistDefer();
      card.querySelector('[data-val="opacity"]').textContent = `${e.target.value}%`;
    });
    const bl = card.querySelector("#blsm-bg-blur");
    bl.addEventListener("input", (e) => {
      state.blur = Number(e.target.value); apply(); persistDefer();
      card.querySelector('[data-val="blur"]').textContent = `${e.target.value}px`;
    });
    const sc = card.querySelector("#blsm-bg-scrim");
    sc.addEventListener("input", (e) => {
      state.scrim = e.target.value / 100; apply(); persistDefer();
      card.querySelector('[data-val="scrim"]').textContent = `${e.target.value}%`;
    });
    card.querySelectorAll("[data-speed-val]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.speed = btn.dataset.speedVal; persist(); apply();
      });
    });
    const mediaInput = card.querySelector("#blsm-bg-media-url");
    mediaInput?.addEventListener("input", (e) => {
      state.mediaUrl = e.target.value.trim();
      state.mediaPath = "";
      persistDefer();
      scheduleMediaApply();
      refreshMediaStatus();
    });
    card.querySelector("[data-bg-browse]")?.addEventListener("click", async () => {
      const bridge = api();
      if (!bridge?.pick_bg_media) return;
      try {
        const res = await bridge.pick_bg_media();
        if (!res?.ok) return;
        const picked = String(res.path || "").trim();
        if (!picked) return;
        state.mediaPath = picked;
        state.mediaUrl = "";
        if (mediaInput) mediaInput.value = picked;
        persist();
        apply();
        refreshMediaStatus();
      } catch (e) { console.warn("[bg] pick_bg_media error:", e); }
    });
    card.querySelector("[data-bg-clear]")?.addEventListener("click", () => {
      state.mediaUrl = "";
      state.mediaPath = "";
      if (mediaInput) mediaInput.value = "";
      persist();
      apply();
      refreshMediaStatus();
    });
  }

  let deferTimer = null;
  function persistDefer() {
    if (deferTimer) clearTimeout(deferTimer);
    deferTimer = setTimeout(persist, 250);
  }

  let mediaApplyTimer = null;
  function scheduleMediaApply() {
    if (mediaApplyTimer) clearTimeout(mediaApplyTimer);
    mediaApplyTimer = setTimeout(() => apply(), 350);
  }

  function refreshMediaStatus() {
    const card = document.getElementById(CARD_ID);
    if (!card) return;
    const status = card.querySelector("[data-media-status]");
    if (!status) return;
    const url = String(state.mediaUrl || "").trim();
    const path = String(state.mediaPath || "").trim();
    const src = url || path;
    if (!src) { status.hidden = true; status.textContent = ""; return; }
    const kind = guessMediaKind(url && /^https?:\/\//i.test(url) ? url : path);
    status.hidden = false;
    status.textContent = path && !url
      ? `Local ${kind} selected — ${path.split(/[\\/]/).pop()}`
      : `${kind === "video" ? "Video" : "Image"} URL`;
  }

  function refreshCardFields() {
    const card = document.getElementById(CARD_ID);
    if (!card) return;
    card.querySelector("#blsm-bg-enable").checked = !!state.enabled;
    card.querySelector("#blsm-bg-preset").value = state.preset;
    const op = card.querySelector("#blsm-bg-opacity"); if (op) op.value = String(Math.round(state.opacity * 100));
    const bl = card.querySelector("#blsm-bg-blur"); if (bl) bl.value = String(state.blur);
    const sc = card.querySelector("#blsm-bg-scrim"); if (sc) sc.value = String(Math.round(state.scrim * 100));
    const opv = card.querySelector('[data-val="opacity"]'); if (opv) opv.textContent = `${Math.round(state.opacity * 100)}%`;
    const blv = card.querySelector('[data-val="blur"]'); if (blv) blv.textContent = `${state.blur}px`;
    const scv = card.querySelector('[data-val="scrim"]'); if (scv) scv.textContent = `${Math.round(state.scrim * 100)}%`;
    card.querySelectorAll("[data-speed-val]").forEach((btn) => {
      btn.classList.toggle("is-selected", btn.dataset.speedVal === state.speed);
    });
    const mediaRow = card.querySelector("[data-media-row]");
    if (mediaRow) mediaRow.hidden = state.preset !== "custom-media";
    const mediaInput = card.querySelector("#blsm-bg-media-url");
    if (mediaInput && document.activeElement !== mediaInput) {
      mediaInput.value = state.mediaUrl || state.mediaPath || "";
    }
    refreshMediaStatus();
    const disabled = !state.enabled;
    card.querySelectorAll("select, input[type='range'], [data-speed] button").forEach((el) => {
      el.disabled = disabled;
      el.style.opacity = disabled ? "0.5" : "";
    });
  }

  function findAppearanceParent() {
    const header = Array.from(document.querySelectorAll(".page-header")).find(
      (h) => h.querySelector("h2")?.textContent?.trim() === PAGE
    );
    return header?.parentElement || null;
  }

  function mountCard() {
    const parent = findAppearanceParent();
    if (!parent) return;
    if (document.getElementById(CARD_ID)?.isConnected) { refreshCardFields(); return; }
    const card = buildCard();
    // place it right after the existing appearance card if present
    const sib = parent.querySelector(".blsm-appearance-card");
    if (sib && sib.nextSibling) parent.insertBefore(card, sib.nextSibling);
    else if (sib) sib.after(card);
    else parent.appendChild(card);
    refreshCardFields();
  }

  const isAppearancePage = () => (pageHeaderTitle ? pageHeaderTitle() : document.querySelector(".page-header h2")?.textContent?.trim()) === PAGE;

  function refresh() {
    if (!isAppearancePage()) { document.getElementById(CARD_ID)?.remove(); return; }
    mountCard();
  }

  async function init() {
    ensureLayer();
    const bridge = api();
    if (bridge?.get_config) {
      try { mergeFromConfig(await bridge.get_config()); } catch (e) { console.warn("[bg] config load failed:", e); }
    }
    apply();
    refresh();
  }

  if (observeMain) {
    observeMain(refresh, 0, [PAGE]);
  } else {
    window.addEventListener("pywebviewready", refresh);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => void init());
  } else {
    void init();
  }
  window.addEventListener("pywebviewready", () => void init());
})();
