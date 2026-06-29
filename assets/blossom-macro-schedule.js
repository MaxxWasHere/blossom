(function () {
  "use strict";

  const ACTIVITIES = [
    { id: "fishing", label: "Fishing Mode", icon: "fishing", short: "Fishing" },
    { id: "potion", label: "Auto Potion Craft", icon: "flask", short: "Potion" },
    { id: "merchant", label: "Merchant Teleporter", icon: "cart", short: "Merchant" },
    { id: "idle", label: "Idle (pause automations)", icon: "pause", short: "Idle" },
  ];

  const PROPS_PANEL_ID = "blsm-schedule-props-panel";
  const CONTEXT_MENU_ID = "blsm-schedule-context-menu";
  const MIN_BLOCK_PX = 56;
  const BASE_PX_PER_MINUTE = 1.35;
  const RESIZE_PX_PER_MIN = 2.2;
  const ZOOM_LS_KEY = "blsm-macro-schedule-zoom";
  const ZOOM_MIN = 0.5;
  const ZOOM_MAX = 3;
  const ZOOM_STEP = 0.1;

  const activityMeta = (id) => ACTIVITIES.find((a) => a.id === id) || ACTIVITIES[3];

  const iconMarkup = (name) => window.BlossomIcons?.svg(name) || "";

  const api = () => window.pywebview?.api;

  const defaultSteps = () => [
    { activity: "fishing", hours: 2, minutes: 0 },
    { activity: "potion", hours: 3, minutes: 0 },
  ];

  const reduceMotion = () => document.documentElement.classList.contains("blsm-reduce-motion");

  const newProfileId = () => {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID().replace(/-/g, "").slice(0, 12);
    }
    return `p${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
  };

  const cloneSteps = (steps) =>
    (Array.isArray(steps) ? steps : []).map((s) => ({
      activity: String(s?.activity || "idle"),
      hours: Number(s?.hours) || 0,
      minutes: Number(s?.minutes) || 0,
    }));

  const cloneProfile = (profile) => ({
    id: String(profile?.id || newProfileId()),
    name: String(profile?.name || "Untitled"),
    loop: profile?.loop !== false,
    steps: cloneSteps(profile?.steps).length ? cloneSteps(profile?.steps) : defaultSteps(),
  });

  const stepMinutes = (step) => Math.max(1, (step.hours || 0) * 60 + (step.minutes || 0));

  const profileCycleMinutes = (profile) =>
    (profile?.steps || []).reduce((sum, s) => sum + stepMinutes(s), 0);

  const formatCycleLabel = (mins) => {
    const h = Math.floor(mins / 60);
    const m = mins % 60;
    if (h && m) return `${h}h ${String(m).padStart(2, "0")}m cycle`;
    if (h) return `${h}h cycle`;
    return `${m}m cycle`;
  };

  const minutesToStep = (totalMins) => {
    const mins = Math.max(1, Math.min(48 * 60, Math.round(totalMins)));
    return { hours: Math.floor(mins / 60), minutes: mins % 60 };
  };

  let zoomLevel = 1;
  let zoomSaveTimer = null;

  const pxPerMinute = () => BASE_PX_PER_MINUTE * zoomLevel;

  const blockWidthPx = (step) => Math.max(MIN_BLOCK_PX, stepMinutes(step) * pxPerMinute());

  const applyZoomCss = () => {
    document.documentElement.style.setProperty(
      "--blsm-schedule-px-per-min",
      String(pxPerMinute())
    );
  };

  const loadZoom = async () => {
    try {
      const cached = localStorage.getItem(ZOOM_LS_KEY);
      if (cached) {
        const z = parseFloat(cached);
        if (Number.isFinite(z)) zoomLevel = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z));
      }
    } catch {}
    const bridge = api();
    if (bridge?.get_config) {
      try {
        const cfg = await bridge.get_config();
        if (cfg?.macro_schedule_zoom != null) {
          const z = Number(cfg.macro_schedule_zoom);
          if (Number.isFinite(z)) zoomLevel = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, z));
        }
      } catch {}
    }
    applyZoomCss();
  };

  const persistZoom = () => {
    try {
      localStorage.setItem(ZOOM_LS_KEY, String(zoomLevel));
    } catch {}
    const bridge = api();
    if (!bridge?.get_config || !bridge?.save_config) return;
    clearTimeout(zoomSaveTimer);
    zoomSaveTimer = setTimeout(async () => {
      try {
        const cur = await bridge.get_config();
        await bridge.save_config({ ...cur, macro_schedule_zoom: zoomLevel });
      } catch {}
    }, 400);
  };

  const setZoom = (root, next) => {
    zoomLevel = Math.max(ZOOM_MIN, Math.min(ZOOM_MAX, next));
    applyZoomCss();
    persistZoom();
    syncZoomUi(root);
    if (mountedState && root) {
      syncRuler(root);
      syncTrackWidth(root);
      renderTrack(root);
    }
  };

  const syncZoomUi = (root) => {
    if (!root) return;
    const slider = root.querySelector(".blsm-schedule-zoom-slider");
    const label = root.querySelector("[data-zoom-label]");
    const pct = Math.round(zoomLevel * 100);
    if (slider) slider.value = String(pct);
    if (label) label.textContent = `${pct}%`;
  };

  /** @type {{ loop: boolean, steps: Array<{activity:string,hours:number,minutes:number}> } | null} */
  let mountedState = null;
  /** @type {{ enabled: boolean, profiles: Array<{id:string,name:string,loop:boolean,steps:Array}>, activeProfileId: string } | null} */
  let appState = null;
  /** @type {{ id: string, name: string, loop: boolean, steps: Array } | null} */
  let draftProfile = null;
  let viewMode = "picker";
  let liveInterval = null;
  let selectedIndex = -1;
  /** @type {HTMLElement | null} */
  let mountedHost = null;
  /** @type {HTMLElement | null} */
  let mountedRoot = null;
  let propsPanel = null;
  /** @type {null | (() => void)} */
  let timelineScrollUnmount = null;
  /** @type {null | ((e: KeyboardEvent) => void)} */
  let globalKeyHandler = null;
  /** @type {null | ((e: MouseEvent) => void)} */
  let globalClickHandler = null;

  const editorRoot = () => mountedHost?.querySelector(".blsm-schedule-editor .blsm-schedule-root") || null;

  const wireTimelineScroll = (root) => {
    if (timelineScrollUnmount) {
      timelineScrollUnmount();
      timelineScrollUnmount = null;
    }
    const scrollEl = root?.querySelector(".blsm-schedule-track-scroll");
    if (!scrollEl || !window.BlossomScroll?.mountTimelineScroll) return;
    const handle = window.BlossomScroll.mountTimelineScroll(scrollEl);
    handle.bindDragAutoScroll(() => Boolean(drag));
    timelineScrollUnmount = () => handle.destroy();
  };

  const bindDraftMountedState = () => {
    if (!draftProfile) {
      mountedState = null;
      return;
    }
    mountedState = {
      loop: draftProfile.loop,
      steps: draftProfile.steps,
    };
  };

  const persistProfiles = async () => {
    if (!appState) return;
    const bridge = api();
    if (!bridge?.save_macro_schedule_profiles && !bridge?.save_macro_schedule) return;
    const payload = {
      enabled: appState.enabled,
      active_profile_id: appState.activeProfileId,
      profiles: appState.profiles,
    };
    try {
      if (bridge.save_macro_schedule_profiles) {
        await bridge.save_macro_schedule_profiles(payload);
      } else {
        const active = appState.profiles.find((p) => p.id === appState.activeProfileId) || appState.profiles[0];
        await bridge.save_macro_schedule({
          enabled: appState.enabled,
          active_profile_id: appState.activeProfileId,
          profiles: appState.profiles,
          loop: active?.loop !== false,
          steps: active?.steps || [],
        });
      }
    } catch (error) {
      console.warn("[macro-schedule] save failed:", error);
    }
  };

  const loadProfilesFromBridge = async () => {
    const bridge = api();
    let remote = null;
    if (bridge?.get_macro_schedule_profiles) {
      try {
        remote = await bridge.get_macro_schedule_profiles();
      } catch {}
    }
    if (!remote?.profiles && bridge?.get_macro_schedule) {
      try {
        remote = await bridge.get_macro_schedule();
      } catch {}
    }
    if (!remote?.profiles && bridge?.get_config) {
      try {
        const cfg = await bridge.get_config();
        const steps = cloneSteps(cfg?.macro_schedule_steps);
        remote = {
          enabled: Boolean(cfg?.macro_schedule_enabled),
          active_profile_id: cfg?.macro_schedule_active_profile_id || "default",
          profiles: [
            {
              id: "default",
              name: "Default",
              loop: cfg?.macro_schedule_loop !== false,
              steps: steps.length ? steps : defaultSteps(),
            },
          ],
        };
      } catch {}
    }
    const profiles = (remote?.profiles || []).map(cloneProfile);
    if (!profiles.length) profiles.push(cloneProfile({ id: "default", name: "Default" }));
    let activeId = String(remote?.active_profile_id || profiles[0].id);
    if (!profiles.some((p) => p.id === activeId)) activeId = profiles[0].id;
    appState = {
      enabled: Boolean(remote?.enabled),
      profiles,
      activeProfileId: activeId,
    };
  };

  const formatDuration = (step) => {
    const h = step.hours || 0;
    const m = step.minutes || 0;
    if (h && m) return `${h}h ${String(m).padStart(2, "0")}m`;
    if (h) return `${h}h 00m`;
    return `${m}m`;
  };

  const totalTimelineMinutes = () =>
    mountedState?.steps.reduce((sum, s) => sum + stepMinutes(s), 0) || 0;

  const rulerIntervalMins = () => {
    const ppm = pxPerMinute();
    if (ppm < 0.9) return 60;
    if (ppm < 1.6) return 30;
    if (ppm < 2.8) return 15;
    return 5;
  };

  const syncRuler = (root) => {
    const ruler = root.querySelector(".blsm-schedule-ruler");
    if (!ruler || !mountedState) return;
    const ppm = pxPerMinute();
    const totalMins = totalTimelineMinutes();
    const totalPx = Math.max(280, totalMins * ppm + 100);
    ruler.style.width = `${totalPx}px`;
    const interval = rulerIntervalMins();
    const parts = [];
    for (let m = 0; m <= totalMins; m += interval) {
      const left = m * ppm;
      let label = "";
      if (m === 0) label = "0";
      else if (m % 60 === 0) label = `${m / 60}h`;
      else if (m > 60 && m % 60 !== 0) label = `${Math.floor(m / 60)}:${String(m % 60).padStart(2, "0")}`;
      else label = `${m}m`;
      parts.push(
        `<span class="blsm-schedule-ruler-tick" style="left:${left}px"><span class="blsm-schedule-ruler-mark"></span><span class="blsm-schedule-ruler-label">${label}</span></span>`
      );
    }
    ruler.innerHTML = parts.join("");
  };

  const syncTrackWidth = (root) => {
    const track = root.querySelector(".blsm-schedule-track");
    if (!track || !mountedState) return;
    const ppm = pxPerMinute();
    const totalMins = totalTimelineMinutes();
    track.style.minWidth = `${Math.max(320, totalMins * ppm + 140)}px`;
  };

  const blockHtml = (step, index, liveIndex) => {
    const meta = activityMeta(step.activity);
    const liveCls = liveIndex === index ? " is-live" : "";
    const selCls = selectedIndex === index ? " is-selected" : "";
    const w = blockWidthPx(step);
    return `
      <div class="blsm-schedule-block${liveCls}${selCls}" data-index="${index}" data-activity="${step.activity}" tabindex="0" role="button" aria-label="${meta.short} step, ${formatDuration(step)}. Press Enter to edit." style="--block-w:${w}px">
        <div class="blsm-schedule-edge blsm-schedule-edge-left" data-edge="left" title="Drag to adjust duration"></div>
        <div class="blsm-schedule-block-body">
          <span class="blsm-schedule-grip" aria-hidden="true">${iconMarkup("grip-horizontal")}</span>
          <div class="blsm-schedule-block-icon" aria-hidden="true">${iconMarkup(meta.icon)}</div>
          <div class="blsm-schedule-block-meta">
            <div class="blsm-schedule-block-label">${meta.short}</div>
            <div class="blsm-schedule-block-dur">${formatDuration(step)}</div>
          </div>
        </div>
        <div class="blsm-schedule-edge blsm-schedule-edge-right" data-edge="right" title="Drag to adjust duration"></div>
      </div>`;
  };

  const insertHtml = (slot) =>
    `<div class="blsm-schedule-insert" data-insert="${slot}" aria-hidden="true"></div>`;

  const paletteHtml = () =>
    ACTIVITIES.map(
      (a) =>
        `<button type="button" class="blsm-schedule-chip" draggable="false" data-palette="${a.id}"><span class="blsm-schedule-chip-icon" aria-hidden="true">${iconMarkup(a.icon)}</span> ${a.short}</button>`
    ).join("");

  const profilePreviewIcons = (profile) => {
    const icons = (profile.steps || []).slice(0, 4).map((s) => activityMeta(s.activity).icon);
    if (!icons.length) return iconMarkup("calendar");
    return icons.map((n) => `<span class="blsm-schedule-profile-preview-icon">${iconMarkup(n)}</span>`).join("");
  };

  const shellTemplate = () => `
    <div class="blsm-schedule-app">
      <section class="blsm-schedule-picker" data-schedule-view="picker" hidden></section>
      <section class="blsm-schedule-editor" data-schedule-view="editor" hidden></section>
    </div>`;

  const pickerTemplate = () => `
    <div class="blsm-schedule-picker-inner">
      <div class="blsm-schedule-toolbar blsm-schedule-picker-toolbar">
        <label class="blsm-schedule-toggle">
          <input type="checkbox" id="blsm-schedule-enabled" />
          <span><b>Use schedule when macro runs</b><span>Active profile overrides fishing / potion / merchant toggles per step.</span></span>
        </label>
      </div>
      <div class="blsm-schedule-profiles-head">
        <div>
          <h3 class="blsm-schedule-profiles-title">Schedule profiles</h3>
          <p class="blsm-schedule-profiles-sub">Pick a plan to edit, or add a new one. The active profile runs when the schedule is enabled.</p>
        </div>
      </div>
      <div class="blsm-schedule-profiles-grid" role="list" data-profiles-grid></div>
      <div class="blsm-schedule-live-pill" data-schedule-live><span class="dot"></span><span data-schedule-live-text>Schedule off — macro uses your manual toggles.</span></div>
    </div>`;

  const editorTemplate = () => `
    <div class="blsm-schedule-root">
      <header class="blsm-schedule-profile-header">
        <button type="button" class="blsm-schedule-profile-back" data-profile-back aria-label="Back to profiles">${iconMarkup("layers")}<span>Profiles</span></button>
        <div class="blsm-schedule-profile-name-wrap">
          <span class="blsm-schedule-profile-name-icon" aria-hidden="true">${iconMarkup("calendar")}</span>
          <input type="text" class="blsm-schedule-profile-name" data-profile-name maxlength="48" aria-label="Profile name" />
        </div>
        <div class="blsm-schedule-profile-actions">
          <button type="button" class="blsm-schedule-profile-delete btn btn-secondary" data-profile-delete>${iconMarkup("trash")}<span>Delete</span></button>
          <button type="button" class="blsm-schedule-profile-cancel btn btn-secondary" data-profile-cancel>Cancel</button>
          <button type="button" class="blsm-schedule-profile-save btn btn-primary" data-profile-save>${iconMarkup("check")}<span>Save</span></button>
        </div>
      </header>
      <div class="blsm-schedule-toolbar">
        <label class="blsm-schedule-toggle">
          <input type="checkbox" id="blsm-schedule-loop" />
          <span><b>Loop after last step</b><span>Return to step 1 when the last block ends. Off = stop macro at end.</span></span>
        </label>
      </div>
      <div class="blsm-schedule-timeline-head">
        <span class="blsm-schedule-timeline-total" data-timeline-total></span>
        <div class="blsm-schedule-timeline-actions">
          <span class="blsm-schedule-timeline-hint">Drag blocks to reorder · edges to resize · right-click for properties</span>
          <div class="blsm-schedule-zoom" data-schedule-zoom>
            <button type="button" class="blsm-schedule-zoom-btn" data-zoom="out" aria-label="Zoom out">${iconMarkup("minus")}</button>
            <input type="range" class="blsm-schedule-zoom-slider" min="50" max="300" step="5" value="100" aria-label="Timeline zoom" />
            <button type="button" class="blsm-schedule-zoom-btn" data-zoom="in" aria-label="Zoom in">${iconMarkup("plus")}</button>
            <span class="blsm-schedule-zoom-label" data-zoom-label>100%</span>
          </div>
        </div>
      </div>
      <div class="blsm-schedule-track-wrap">
        <div class="blsm-schedule-track-scroll">
          <div class="blsm-schedule-ruler" aria-hidden="true"></div>
          <div class="blsm-schedule-track" role="list" aria-label="Schedule timeline"></div>
        </div>
      </div>
      <div class="blsm-schedule-palette">
        <div class="blsm-schedule-palette-label"><span class="blsm-schedule-palette-label-icon" aria-hidden="true">${iconMarkup("plus")}</span>Drag to add</div>
        ${paletteHtml()}
      </div>
      <div class="blsm-schedule-live-pill" data-schedule-live><span class="dot"></span><span data-schedule-live-text>Schedule off — macro uses your manual toggles.</span></div>
    </div>`;

  const profileCardHtml = (profile) => {
    const mins = profileCycleMinutes(profile);
    const stepCount = profile.steps?.length || 0;
    const isActive = appState?.activeProfileId === profile.id;
    const activeBadge = isActive
      ? `<span class="blsm-schedule-profile-badge">${iconMarkup("check")} Active</span>`
      : "";
    return `
      <button type="button" class="blsm-schedule-profile-card${isActive ? " is-active" : ""}" role="listitem" data-profile-id="${profile.id}">
        <div class="blsm-schedule-profile-card-top">
          <span class="blsm-schedule-profile-card-icon" aria-hidden="true">${iconMarkup("layers")}</span>
          ${activeBadge}
        </div>
        <div class="blsm-schedule-profile-card-name">${profile.name}</div>
        <div class="blsm-schedule-profile-card-meta">${stepCount} step${stepCount === 1 ? "" : "s"} · ${formatCycleLabel(mins)}</div>
        <div class="blsm-schedule-profile-card-preview" aria-hidden="true">${profilePreviewIcons(profile)}</div>
      </button>`;
  };

  const addProfileCardHtml = () => `
    <button type="button" class="blsm-schedule-profile-card blsm-schedule-profile-add" role="listitem" data-profile-add>
      <span class="blsm-schedule-profile-add-icon" aria-hidden="true">${iconMarkup("plus")}</span>
      <span class="blsm-schedule-profile-add-title">Add profile</span>
      <span class="blsm-schedule-profile-add-sub">New timed automation plan</span>
    </button>`;

  const renderProfileGrid = () => {
    const grid = mountedHost?.querySelector("[data-profiles-grid]");
    if (!grid || !appState) return;
    const cards = appState.profiles.map(profileCardHtml).join("");
    grid.innerHTML = cards + addProfileCardHtml();
  };

  const showPicker = () => {
    if (!mountedHost || !appState) return;
    viewMode = "picker";
    draftProfile = null;
    mountedState = null;
    mountedRoot = null;
    exitEditMode();
    document.documentElement.classList.remove("blsm-schedule-profile-editing");

    const picker = mountedHost.querySelector(".blsm-schedule-picker");
    const editor = mountedHost.querySelector(".blsm-schedule-editor");
    if (!picker) return;

    picker.hidden = false;
    if (editor) editor.hidden = true;

    if (!picker.dataset.blsmPickerReady) {
      picker.innerHTML = pickerTemplate();
      picker.dataset.blsmPickerReady = "1";

      const enabled = picker.querySelector("#blsm-schedule-enabled");
      enabled?.addEventListener("change", async () => {
        if (!appState) return;
        appState.enabled = Boolean(enabled.checked);
        await persistProfiles();
        void syncLive(picker);
      });

      picker.addEventListener("click", (e) => {
        if (!(e.target instanceof Element)) return;
        const addBtn = e.target.closest("[data-profile-add]");
        if (addBtn) {
          enterProfileEditor(null);
          return;
        }
        const card = e.target.closest("[data-profile-id]");
        if (!card || !appState) return;
        const id = card.getAttribute("data-profile-id");
        const profile = appState.profiles.find((p) => p.id === id);
        if (profile) enterProfileEditor(profile);
      });
    }

    const enabled = picker.querySelector("#blsm-schedule-enabled");
    if (enabled) enabled.checked = appState.enabled;
    renderProfileGrid();
    void syncLive(picker);
  };

  const enterProfileEditor = (profileOrNull) => {
    if (!mountedHost || !appState) return;
    viewMode = "editor";
    draftProfile = profileOrNull
      ? cloneProfile(profileOrNull)
      : cloneProfile({ id: newProfileId(), name: "New profile", steps: [], loop: true });
    if (!draftProfile.steps.length) draftProfile.steps = defaultSteps();
    bindDraftMountedState();

    const picker = mountedHost.querySelector(".blsm-schedule-picker");
    const editor = mountedHost.querySelector(".blsm-schedule-editor");
    if (picker) picker.hidden = true;
    if (!editor) return;
    editor.hidden = false;

    if (!editor.dataset.blsmEditorReady) {
      editor.innerHTML = editorTemplate();
      editor.dataset.blsmEditorReady = "1";
      bindEditorChrome(editor);
    }

    mountedRoot = editor.querySelector(".blsm-schedule-root");
    if (!mountedRoot) return;

    document.documentElement.classList.add("blsm-schedule-profile-editing");

    const nameInput = editor.querySelector("[data-profile-name]");
    const loop = editor.querySelector("#blsm-schedule-loop");
    const deleteBtn = editor.querySelector("[data-profile-delete]");
    if (nameInput) nameInput.value = draftProfile.name;
    if (loop) loop.checked = draftProfile.loop;
    if (deleteBtn) {
      const isExisting = appState.profiles.some((p) => p.id === draftProfile.id);
      deleteBtn.hidden = !isExisting || appState.profiles.length <= 1;
    }

    if (editor.dataset.blsmZoomBound !== "1") {
      bindZoomControls(mountedRoot);
    }
    if (mountedRoot.dataset.blsmGlobalBound !== "1") {
      bindGlobalHandlers(mountedRoot);
    }

    renderTrack(mountedRoot);
    wireTimelineScroll(mountedRoot);
    void syncLive(mountedRoot);

    if (!draftProfile.id || profileOrNull === null) {
      nameInput?.focus();
      nameInput?.select();
    }
  };

  const bindEditorChrome = (editor) => {
    editor.querySelector("[data-profile-back]")?.addEventListener("click", () => cancelProfileEditor());
    editor.querySelector("[data-profile-cancel]")?.addEventListener("click", () => cancelProfileEditor());
    editor.querySelector("[data-profile-save]")?.addEventListener("click", () => void saveProfileEditor());
    editor.querySelector("[data-profile-delete]")?.addEventListener("click", () => void deleteProfileEditor());

    const nameInput = editor.querySelector("[data-profile-name]");
    nameInput?.addEventListener("input", () => {
      if (!draftProfile) return;
      draftProfile.name = String(nameInput.value || "").trim() || "Untitled";
    });

    const loop = editor.querySelector("#blsm-schedule-loop");
    loop?.addEventListener("change", () => {
      if (!draftProfile) return;
      draftProfile.loop = Boolean(loop.checked);
      if (mountedState) mountedState.loop = draftProfile.loop;
    });
  };

  const cancelProfileEditor = () => {
    draftProfile = null;
    showPicker();
  };

  const saveProfileEditor = async () => {
    if (!appState || !draftProfile || !mountedHost) return;
    const nameInput = mountedHost.querySelector("[data-profile-name]");
    const loop = mountedHost.querySelector("#blsm-schedule-loop");
    draftProfile.name = String(nameInput?.value || draftProfile.name).trim() || "Untitled";
    draftProfile.loop = loop?.checked !== false;
    draftProfile.steps = cloneSteps(mountedState?.steps || draftProfile.steps);

    const idx = appState.profiles.findIndex((p) => p.id === draftProfile.id);
    const saved = cloneProfile(draftProfile);
    if (idx >= 0) appState.profiles[idx] = saved;
    else appState.profiles.push(saved);
    appState.activeProfileId = saved.id;

    await persistProfiles();
    draftProfile = null;
    showPicker();
  };

  const deleteProfileEditor = async () => {
    if (!appState || !draftProfile) return;
    if (appState.profiles.length <= 1) return;
    const name = draftProfile.name || "this profile";
    if (!window.confirm(`Delete "${name}"? This cannot be undone.`)) return;

    appState.profiles = appState.profiles.filter((p) => p.id !== draftProfile.id);
    if (appState.activeProfileId === draftProfile.id) {
      appState.activeProfileId = appState.profiles[0]?.id || "";
    }
    await persistProfiles();
    draftProfile = null;
    showPicker();
  };

  const syncTimelineMeta = (root) => {
    const totalEl = root.querySelector("[data-timeline-total]");
    if (totalEl && mountedState) {
      const mins = totalTimelineMinutes();
      const h = Math.floor(mins / 60);
      const m = mins % 60;
      totalEl.textContent = h ? `Total cycle: ${h}h ${String(m).padStart(2, "0")}m` : `Total cycle: ${m}m`;
    }
  };

  const bindZoomControls = (root) => {
    if (root.dataset.blsmZoomBound === "1") return;
    root.dataset.blsmZoomBound = "1";
    syncZoomUi(root);

    root.querySelector("[data-zoom=out]")?.addEventListener("click", () => {
      setZoom(root, zoomLevel - ZOOM_STEP);
    });
    root.querySelector("[data-zoom=in]")?.addEventListener("click", () => {
      setZoom(root, zoomLevel + ZOOM_STEP);
    });
    root.querySelector(".blsm-schedule-zoom-slider")?.addEventListener("input", (e) => {
      const pct = Number(e.target?.value) || 100;
      setZoom(root, pct / 100);
    });
  };

  const renderTrack = (root, liveIndex = -1) => {
    const track = root.querySelector(".blsm-schedule-track");
    if (!track || !mountedState) return;
    const parts = [];
    mountedState.steps.forEach((step, i) => {
      parts.push(insertHtml(i));
      parts.push(blockHtml(step, i, liveIndex));
    });
    parts.push(insertHtml(mountedState.steps.length));
    parts.push(
      `<div class="blsm-schedule-dropzone" data-drop-end><span class="blsm-schedule-dropzone-icon" aria-hidden="true">${iconMarkup("plus")}</span><span>Add blocks here or drag from the palette below</span></div>`
    );
    track.innerHTML = parts.join("");
    syncTimelineMeta(root);
    syncRuler(root);
    syncTrackWidth(root);
    bindDrag(root);
    bindResize(root);
    bindBlockSelection(root);
  };

  const syncLive = async (scope) => {
    const root = scope || (viewMode === "editor" ? mountedRoot : mountedHost?.querySelector(".blsm-schedule-picker"));
    const pill = root?.querySelector("[data-schedule-live]");
    const textEl = root?.querySelector("[data-schedule-live-text]");
    if (!pill || !textEl || !appState) return;

    let live = null;
    if (api()?.get_session_stats) {
      try {
        const stats = await api().get_session_stats();
        live = stats?.schedule || null;
      } catch {}
    }

    if (viewMode === "editor" && mountedState && mountedRoot) {
      const liveIndex =
        live?.active && Number.isFinite(live.step_index) ? Number(live.step_index) : -1;
      renderTrack(mountedRoot, liveIndex);
    }

    if (!live?.active) {
      const activeName =
        appState.profiles.find((p) => p.id === appState.activeProfileId)?.name || "Active profile";
      textEl.textContent = appState.enabled
        ? `Schedule armed — "${activeName}" starts at step 1 when you press Start.`
        : "Schedule off — macro uses your manual toggles.";
      pill.classList.remove("is-running");
      return;
    }
    const n = (live.step_index || 0) + 1;
    const total = live.step_count || mountedState?.steps.length || 0;
    const mins = Math.ceil((live.step_remaining_seconds || 0) / 60);
    const act = activityMeta(live.step_activity || mountedState?.steps?.[live.step_index]?.activity);
    textEl.textContent = `Step ${n}/${total}: ${act.short} — ~${mins} min left`;
    pill.classList.add("is-running");
  };

  const ensurePropsPanel = () => {
    if (propsPanel?.isConnected) return propsPanel;
    const sidebar = document.querySelector(".sidebar");
    if (!sidebar) return null;

    propsPanel = document.getElementById(PROPS_PANEL_ID);
    if (!propsPanel) {
      propsPanel = document.createElement("aside");
      propsPanel.id = PROPS_PANEL_ID;
      propsPanel.className = "blsm-schedule-props-panel";
      propsPanel.setAttribute("aria-label", "Schedule step properties");
      propsPanel.hidden = true;
      propsPanel.innerHTML = `
        <div class="blsm-schedule-props-head">
          <h3>Step properties</h3>
          <button type="button" class="blsm-schedule-props-done" aria-label="Done editing">Done</button>
        </div>
        <div class="blsm-schedule-props-body">
          <p class="blsm-schedule-props-empty" hidden>No step selected — click a block on the timeline or add one from the palette below.</p>
          <div class="blsm-schedule-props-field">
            <span class="blsm-schedule-props-label">Activity</span>
            <div class="blsm-schedule-props-activities" role="group" aria-label="Activity type"></div>
          </div>
          <div class="blsm-schedule-props-field blsm-schedule-props-duration">
            <span class="blsm-schedule-props-label">Duration</span>
            <div class="blsm-schedule-props-dur-row">
              <label><input type="number" class="blsm-schedule-props-hours" min="0" max="48" aria-label="Hours" /><span>h</span></label>
              <label><input type="number" class="blsm-schedule-props-minutes" min="0" max="59" aria-label="Minutes" /><span>m</span></label>
            </div>
          </div>
          <p class="blsm-schedule-props-note">Drag left or right edges on the timeline to remap time, or edit hours and minutes here.</p>
          <button type="button" class="blsm-schedule-props-delete btn btn-secondary">Delete step</button>
        </div>`;
      sidebar.appendChild(propsPanel);

      propsPanel.querySelector(".blsm-schedule-props-done")?.addEventListener("click", () => exitEditMode());
      propsPanel.querySelector(".blsm-schedule-props-delete")?.addEventListener("click", () => {
        if (!mountedState || selectedIndex < 0) return;
        deleteStepAt(selectedIndex);
      });

      const actHost = propsPanel.querySelector(".blsm-schedule-props-activities");
      if (actHost) {
        actHost.innerHTML = ACTIVITIES.map(
          (a) =>
            `<button type="button" class="blsm-schedule-props-act" data-act="${a.id}"><span aria-hidden="true">${iconMarkup(a.icon)}</span>${a.short}</button>`
        ).join("");
        actHost.addEventListener("click", (e) => {
          const btn = e.target instanceof Element ? e.target.closest("[data-act]") : null;
          if (!btn || !mountedState || selectedIndex < 0) return;
          const id = btn.getAttribute("data-act");
          if (!id) return;
          mountedState.steps[selectedIndex].activity = id;
          syncPropsPanel();
          if (mountedRoot) renderTrack(mountedRoot);
        });
      }

      const onDurChange = () => {
        if (!mountedState || selectedIndex < 0) return;
        const h = Math.max(0, parseInt(propsPanel.querySelector(".blsm-schedule-props-hours")?.value || "0", 10) || 0);
        const m = Math.max(0, parseInt(propsPanel.querySelector(".blsm-schedule-props-minutes")?.value || "0", 10) || 0);
        const total = Math.max(1, Math.min(48 * 60, h * 60 + m));
        Object.assign(mountedState.steps[selectedIndex], minutesToStep(total));
        if (mountedRoot) renderTrack(mountedRoot);
      };
      propsPanel.querySelector(".blsm-schedule-props-hours")?.addEventListener("change", onDurChange);
      propsPanel.querySelector(".blsm-schedule-props-minutes")?.addEventListener("change", onDurChange);
    }
    return propsPanel;
  };

  const syncPropsPanel = () => {
    const panel = ensurePropsPanel();
    if (!panel || !mountedState) return;
    if (!document.documentElement.classList.contains("blsm-schedule-edit-mode")) return;

    const emptyEl = panel.querySelector(".blsm-schedule-props-empty");
    const editable = panel.querySelectorAll(
      ".blsm-schedule-props-field, .blsm-schedule-props-note, .blsm-schedule-props-delete"
    );
    const step = selectedIndex >= 0 ? mountedState.steps[selectedIndex] : null;

    if (!step) {
      if (emptyEl) emptyEl.hidden = false;
      editable.forEach((el) => {
        el.hidden = true;
      });
      return;
    }

    if (emptyEl) emptyEl.hidden = true;
    editable.forEach((el) => {
      el.hidden = false;
    });
    panel.querySelector(".blsm-schedule-props-hours").value = String(step.hours || 0);
    panel.querySelector(".blsm-schedule-props-minutes").value = String(step.minutes || 0);
    panel.querySelectorAll(".blsm-schedule-props-act").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-act") === step.activity);
    });
  };

  const deselectBlock = () => {
    if (!document.documentElement.classList.contains("blsm-schedule-edit-mode")) return;
    selectedIndex = -1;
    hideContextMenu();
    if (mountedRoot) {
      mountedRoot.querySelectorAll(".blsm-schedule-block.is-selected").forEach((el) => {
        el.classList.remove("is-selected");
      });
    }
    syncPropsPanel();
  };

  const deleteStepAt = (index) => {
    if (!mountedState || index < 0 || mountedState.steps.length <= 1) return;
    const inEdit = document.documentElement.classList.contains("blsm-schedule-edit-mode");
    mountedState.steps.splice(index, 1);
    if (inEdit) {
      selectedIndex = Math.min(index, mountedState.steps.length - 1);
    } else {
      selectedIndex = -1;
    }
    if (mountedRoot) {
      renderTrack(mountedRoot);
      if (inEdit) syncPropsPanel();
    }
  };

  const enterEditMode = (index) => {
    if (!mountedState || index < 0 || index >= mountedState.steps.length) return;
    selectedIndex = index;
    document.documentElement.classList.add("blsm-schedule-edit-mode");
    const panel = ensurePropsPanel();
    if (panel) {
      panel.hidden = false;
      syncPropsPanel();
    }
    if (mountedRoot) {
      mountedRoot.querySelectorAll(".blsm-schedule-block").forEach((el) => {
        el.classList.toggle("is-selected", Number(el.getAttribute("data-index")) === index);
      });
    }
  };

  const exitEditMode = () => {
    selectedIndex = -1;
    document.documentElement.classList.remove("blsm-schedule-edit-mode");
    if (propsPanel) propsPanel.hidden = true;
    hideContextMenu();
    if (mountedRoot) {
      mountedRoot.querySelectorAll(".blsm-schedule-block.is-selected").forEach((el) => {
        el.classList.remove("is-selected");
      });
    }
  };

  const hideContextMenu = () => {
    document.getElementById(CONTEXT_MENU_ID)?.remove();
  };

  const showContextMenu = (x, y, index) => {
    hideContextMenu();
    const menu = document.createElement("div");
    menu.id = CONTEXT_MENU_ID;
    menu.className = "blsm-schedule-context-menu";
    menu.innerHTML = `
      <button type="button" data-cmd="properties">Properties</button>
      <button type="button" data-cmd="duplicate">Duplicate</button>
      <button type="button" data-cmd="delete" class="is-danger">Delete</button>`;
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    document.body.appendChild(menu);

    const close = () => hideContextMenu();
    const onDoc = (e) => {
      if (!(e.target instanceof Element) || !menu.contains(e.target)) close();
      document.removeEventListener("pointerdown", onDoc, true);
    };
    setTimeout(() => document.addEventListener("pointerdown", onDoc, true), 0);

    menu.addEventListener("click", (e) => {
      const btn = e.target instanceof Element ? e.target.closest("[data-cmd]") : null;
      if (!btn || !mountedState) return;
      const cmd = btn.getAttribute("data-cmd");
      if (cmd === "properties") enterEditMode(index);
      else if (cmd === "duplicate") {
        const copy = { ...mountedState.steps[index] };
        mountedState.steps.splice(index + 1, 0, copy);
        if (mountedRoot) renderTrack(mountedRoot);
      } else if (cmd === "delete") {
        deleteStepAt(index);
      }
      close();
    });
  };

  const bindBlockSelection = (root) => {
    root.querySelectorAll(".blsm-schedule-block").forEach((block) => {
      if (block.dataset.blsmSelectBound === "1") return;
      block.dataset.blsmSelectBound = "1";
      block.addEventListener("click", (e) => {
        if (e.target instanceof Element && e.target.closest(".blsm-schedule-edge")) return;
        const index = Number(block.getAttribute("data-index"));
        if (!Number.isFinite(index)) return;
        enterEditMode(index);
      });
      block.addEventListener("contextmenu", (e) => {
        e.preventDefault();
        const index = Number(block.getAttribute("data-index"));
        if (!Number.isFinite(index)) return;
        enterEditMode(index);
        showContextMenu(e.clientX, e.clientY, index);
      });
      block.addEventListener("keydown", (e) => {
        const index = Number(block.getAttribute("data-index"));
        if (!Number.isFinite(index) || !mountedState) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          enterEditMode(index);
        } else if (e.key === "Delete" || e.key === "Backspace") {
          e.preventDefault();
          deleteStepAt(index);
        }
      });
    });
  };

  const bindResize = (root) => {
    const track = root.querySelector(".blsm-schedule-track");
    if (!track) return;

    /** @type {null | { index: number, edge: string, startX: number, startMins: number, block: HTMLElement }} */
    let resize = null;

    const applyResizeVisual = (mins) => {
      if (!resize) return;
      const w = Math.max(MIN_BLOCK_PX, mins * pxPerMinute());
      resize.block.style.setProperty("--block-w", `${w}px`);
      const durEl = resize.block.querySelector(".blsm-schedule-block-dur");
      if (durEl) durEl.textContent = formatDuration(minutesToStep(mins));
    };

    const endResize = () => {
      if (!resize) return;
      resize.block.classList.remove("is-resizing");
      resize = null;
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      document.removeEventListener("pointercancel", onUp);
      if (mountedRoot) {
        syncTimelineMeta(mountedRoot);
        syncRuler(mountedRoot);
        syncTrackWidth(mountedRoot);
        syncPropsPanel();
      }
    };

    const onMove = (e) => {
      if (!resize || !mountedState) return;
      const dx = e.clientX - resize.startX;
      const deltaMins =
        resize.edge === "right" ? dx / RESIZE_PX_PER_MIN : -dx / RESIZE_PX_PER_MIN;
      const newMins = Math.max(1, Math.min(48 * 60, resize.startMins + deltaMins));
      Object.assign(mountedState.steps[resize.index], minutesToStep(newMins));
      applyResizeVisual(newMins);
    };

    const onUp = () => endResize();

    track.querySelectorAll(".blsm-schedule-edge").forEach((edge) => {
      if (edge.dataset.blsmResizeBound === "1") return;
      edge.dataset.blsmResizeBound = "1";
      edge.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        const block = edge.closest(".blsm-schedule-block");
        const index = Number(block?.getAttribute("data-index"));
        if (!block || !Number.isFinite(index) || !mountedState) return;
        e.preventDefault();
        e.stopPropagation();
        const edgeName = edge.getAttribute("data-edge") || "right";
        resize = {
          index,
          edge: edgeName,
          startX: e.clientX,
          startMins: stepMinutes(mountedState.steps[index]),
          block,
        };
        block.classList.add("is-resizing");
        enterEditMode(index);
        try {
          edge.setPointerCapture(e.pointerId);
        } catch {}
        document.addEventListener("pointermove", onMove);
        document.addEventListener("pointerup", onUp);
        document.addEventListener("pointercancel", onUp);
      });
    });
  };

  /** @type {null | { kind: 'reorder'|'palette', index: number, activity: string, el: HTMLElement, ghost: HTMLElement, pointerId: number, offsetX: number, offsetY: number, ghostX: number, ghostY: number, targetX: number, targetY: number, insertSlot: number, raf: number, track: HTMLElement, root: HTMLElement }} */
  let drag = null;

  const bindDrag = (root) => {
    const track = root.querySelector(".blsm-schedule-track");
    if (!track) {
      bindPaletteDrag(root);
      return;
    }

    const clearInsert = () => {
      track.querySelectorAll(".blsm-schedule-insert.is-open").forEach((el) => el.classList.remove("is-open"));
    };

    const slotFromX = (clientX) => {
      const inserts = [...track.querySelectorAll(".blsm-schedule-insert")];
      for (const ins of inserts) {
        const r = ins.getBoundingClientRect();
        const mid = r.left + r.width / 2;
        if (clientX < mid + 8) {
          return Number(ins.getAttribute("data-insert"));
        }
      }
      return mountedState?.steps.length || 0;
    };

    const applyReorder = (from, to) => {
      if (!mountedState || from === to || from === to - 1) return;
      const steps = mountedState.steps.slice();
      const [item] = steps.splice(from, 1);
      const dest = to > from ? to - 1 : to;
      steps.splice(Math.max(0, Math.min(dest, steps.length)), 0, item);
      mountedState.steps = steps;
      if (selectedIndex === from) selectedIndex = dest;
      else if (selectedIndex > from && selectedIndex <= dest) selectedIndex -= 1;
      else if (selectedIndex < from && selectedIndex >= dest) selectedIndex += 1;
      renderTrack(root);
    };

    const addStepAt = (activity, slot) => {
      if (!mountedState) return;
      const step = { activity, hours: 1, minutes: 0 };
      const idx = Math.max(0, Math.min(slot, mountedState.steps.length));
      mountedState.steps.splice(idx, 0, step);
      renderTrack(root);
      enterEditMode(idx);
    };

    const setGhostPos = (ghost, x, y, decor = "") => {
      ghost.style.left = `${x}px`;
      ghost.style.top = `${y}px`;
      ghost.style.transform = decor;
    };

    const springLoop = () => {
      if (!drag) return;
      if (reduceMotion()) {
        setGhostPos(drag.ghost, drag.targetX, drag.targetY);
      } else {
        const k = 0.28;
        drag.ghostX += (drag.targetX - drag.ghostX) * k;
        drag.ghostY += (drag.targetY - drag.ghostY) * k;
        const tilt = (drag.targetX - drag.ghostX) * 0.04;
        setGhostPos(drag.ghost, drag.ghostX, drag.ghostY, `rotate(${tilt}deg) scale(1.03)`);
      }
      drag.raf = requestAnimationFrame(springLoop);
    };

    const endDrag = () => {
      if (!drag) return;
      const { kind, index, activity, insertSlot, track: dragTrack } = drag;
      cancelAnimationFrame(drag.raf);
      drag.ghost.remove();
      if (kind === "reorder") {
        const block = dragTrack.querySelector(`.blsm-schedule-block[data-index="${index}"]`);
        block?.classList.remove("is-dragging");
        block?.style.removeProperty("opacity");
        applyReorder(index, insertSlot);
        if (document.documentElement.classList.contains("blsm-schedule-edit-mode")) {
          syncPropsPanel();
        }
      } else if (kind === "palette") {
        addStepAt(activity, insertSlot);
      }
      clearInsert();
      drag = null;
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      document.removeEventListener("pointercancel", onUp);
    };

    const onMove = (e) => {
      if (!drag || e.pointerId !== drag.pointerId) return;
      drag.targetX = e.clientX - drag.offsetX;
      drag.targetY = e.clientY - drag.offsetY;
      const slot = slotFromX(e.clientX);
      drag.insertSlot = slot;
      clearInsert();
      const ins = track.querySelector(`.blsm-schedule-insert[data-insert="${slot}"]`);
      ins?.classList.add("is-open");
      const dropEnd = track.querySelector(".blsm-schedule-dropzone");
      dropEnd?.classList.toggle("is-over", slot >= (mountedState?.steps.length || 0));
    };

    const onUp = (e) => {
      if (!drag || e.pointerId !== drag.pointerId) return;
      track.querySelector(".blsm-schedule-dropzone")?.classList.remove("is-over");
      endDrag();
    };

    const beginDrag = (e, kind, payload) => {
      if (e.button !== 0 || drag) return;
      const target = payload.el || e.currentTarget;
      if (!(target instanceof HTMLElement)) return;
      e.preventDefault();
      e.stopPropagation();

      const block = target.closest(".blsm-schedule-block");
      const rect = (block || target).getBoundingClientRect();
      const ghost = block?.cloneNode(true) || target.cloneNode(true);
      ghost.classList.add("blsm-schedule-ghost");
      if (kind === "reorder") ghost.classList.add("blsm-schedule-block");
      else ghost.classList.add("blsm-schedule-chip");
      ghost.classList.remove("is-selected", "is-live", "is-dragging");
      ghost.style.width = `${rect.width}px`;
      ghost.style.height = `${rect.height}px`;
      document.body.appendChild(ghost);

      const startX = rect.left;
      const startY = rect.top;
      setGhostPos(ghost, startX, startY, reduceMotion() ? "" : "scale(1.03)");

      drag = {
        kind,
        index: payload.index ?? -1,
        activity: payload.activity,
        el: target,
        ghost,
        pointerId: e.pointerId,
        offsetX: e.clientX - rect.left,
        offsetY: e.clientY - rect.top,
        ghostX: startX,
        ghostY: startY,
        targetX: startX,
        targetY: startY,
        insertSlot: payload.index ?? 0,
        raf: 0,
        track,
        root,
      };

      if (kind === "reorder") {
        block?.classList.add("is-dragging");
      }

      try {
        target.setPointerCapture(e.pointerId);
      } catch {}

      drag.raf = requestAnimationFrame(springLoop);
      document.addEventListener("pointermove", onMove);
      document.addEventListener("pointerup", onUp);
      document.addEventListener("pointercancel", onUp);
    };

    window.__blsmScheduleBeginDrag = beginDrag;

    if (track.dataset.blsmDragBound !== "1") {
      track.dataset.blsmDragBound = "1";
      track.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        const edge = e.target instanceof Element ? e.target.closest(".blsm-schedule-edge") : null;
        if (edge) return;
        const block = e.target instanceof Element ? e.target.closest(".blsm-schedule-block") : null;
        if (!block || !track.contains(block)) return;
        const index = Number(block.getAttribute("data-index"));
        if (!Number.isFinite(index)) return;
        beginDrag(e, "reorder", { index, el: block });
      });
    }

    bindPaletteDrag(root);
  };

  const bindPaletteDrag = (root) => {
    root.querySelectorAll(".blsm-schedule-palette .blsm-schedule-chip").forEach((chip) => {
      if (chip.dataset.blsmPaletteBound === "1") return;
      chip.dataset.blsmPaletteBound = "1";
      chip.addEventListener("pointerdown", (e) => {
        const id = chip.getAttribute("data-palette");
        if (!id) return;
        const begin = window.__blsmScheduleBeginDrag;
        if (begin) begin(e, "palette", { activity: id, index: mountedState?.steps.length || 0, el: chip });
      });
    });
  };

  const bindGlobalHandlers = (root) => {
    if (root.dataset.blsmGlobalBound === "1") return;
    root.dataset.blsmGlobalBound = "1";

    globalKeyHandler = (e) => {
      if (e.key === "Escape" && document.documentElement.classList.contains("blsm-schedule-edit-mode")) {
        exitEditMode();
      }
    };
    document.addEventListener("keydown", globalKeyHandler);

    // Document-scoped (not root-scoped) so clicking anywhere outside the
    // editor — page header, WIP banner, page background — also deselects the
    // active block instead of leaving it accent-colored.
    globalClickHandler = (e) => {
      if (!(e.target instanceof Element)) return;
      if (
        e.target.closest(
          ".blsm-schedule-block, .blsm-schedule-props-panel, .blsm-schedule-context-menu, .blsm-schedule-palette, .blsm-schedule-zoom, .blsm-schedule-profile-header"
        )
      ) {
        return;
      }
      if (document.documentElement.classList.contains("blsm-schedule-edit-mode")) {
        deselectBlock();
      }
    };
    document.addEventListener("click", globalClickHandler);
  };

  const mountTrack = async (host) => {
    if (!host) return null;
    host.innerHTML = shellTemplate();
    mountedHost = host;

    await loadZoom();
    await loadProfilesFromBridge();
    showPicker();

    if (liveInterval) clearInterval(liveInterval);
    liveInterval = setInterval(() => {
      if (host.isConnected) void syncLive();
    }, 4000);

    return {
      refresh: () => void syncLive(),
      destroy: () => {
        exitEditMode();
        if (globalKeyHandler) {
          document.removeEventListener("keydown", globalKeyHandler);
          globalKeyHandler = null;
        }
        if (globalClickHandler) {
          document.removeEventListener("click", globalClickHandler);
          globalClickHandler = null;
        }
        if (timelineScrollUnmount) {
          timelineScrollUnmount();
          timelineScrollUnmount = null;
        }
        document.documentElement.classList.remove("blsm-schedule-profile-editing");
        if (liveInterval) {
          clearInterval(liveInterval);
          liveInterval = null;
        }
        mountedState = null;
        appState = null;
        draftProfile = null;
        mountedRoot = null;
        mountedHost = null;
        host.innerHTML = "";
      },
    };
  };

  window.BlossomMacroSchedule = {
    mountTrack,
    exitEditMode,
    ACTIVITIES,
    formatDuration,
    activityMeta,
  };
})();
