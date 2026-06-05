(function () {
  const HUB_ID = "blsm-cal-hub";
  const LINK_ID = "blossom-potion-cal-link";
  const { observeMain, pageHeaderTitle, goToTab, triggerMorphSwap, debounce } = window.Blossom || {};

  const CHEVRON =
    '<svg class="blsm-cal-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';

  const NATIVE_HIDE_TITLES = new Set([
    "Movements Calibration",
    "Quest Claim Calibration",
    "Merchant Calibrations",
    "Enable Buff Calibration",
    "Equip Aura Calibration",
    "Inventory Click Calibration",
    "Potion Crafting Calibration",
    "Auto Merchant Calibration (Mari / Jester)",
    "Currency Screenshot",
    "Biome Selector calibration",
    "Fishing Calibration",
  ]);

  const NATIVE_HIDE_TITLE_PATTERNS = [
    /^Movements Calibration$/i,
    /^Quest Claim Calibration$/i,
    /^Merchant Calibrations$/i,
    /^Enable Buff Calibration$/i,
    /^Equip Aura Calibration$/i,
    /^Inventory Click Calibration$/i,
    /^Potion Crafting Calibration$/i,
    /^Fishing Calibration$/i,
    /^Auto Merchant Calibration/i,
    /^Currency Screenshot$/i,
    /^Biome Selector calibration$/i,
  ];

  let legacyHideObserver = null;
  let hideLegacyDebounced = null;

  const legacyHideIgnoresMutation = (mutation) => {
    const nodes = [mutation.target, mutation.previousSibling, mutation.nextSibling];
    for (const node of nodes) {
      if (!(node instanceof Element)) continue;
      if (node.id === HUB_ID || node.closest?.(`#${HUB_ID}`)) return true;
      if (node.id === "blsm-mouse-cal-root" || node.closest?.("#blsm-mouse-cal-root")) return true;
      if (node.closest?.(".blsm-cal-section")) return true;
    }
    return false;
  };

  const SECTIONS = [
    {
      id: "movements",
      tone: "violet",
      icon: "🧭",
      title: "Movements",
      subsections: [
        {
          id: "mv-collections",
          short: "Collections",
          marks: [
            ["collections_button", "Open collections"],
            ["exit_collections_button", "Exit collections"],
          ],
        },
        {
          id: "mv-chat",
          short: "Chat",
          marks: [
            ["chat_hover_pos", "Hover chat"],
            ["chat_tab_ocr_pos", "Chat tab OCR"],
            ["chat_close_button", "Close chat"],
            ["chat_box_ocr_pos", "Chat box OCR"],
          ],
        },
        {
          id: "mv-reconnect",
          short: "Reconnect",
          marks: [["reconnect_start_button", "Start / reconnect"]],
        },
      ],
    },
    {
      id: "quest",
      tone: "indigo",
      icon: "📜",
      title: "Quest claim",
      marks: [
        ["quest_menu", "Quest menu"],
        ["quest1_button", "Quest slot 1"],
        ["quest2_button", "Quest slot 2"],
        ["quest3_button", "Quest slot 3"],
        ["claim_quest_button", "Claim"],
        ["quest_reroll_button", "Reroll"],
      ],
    },
    {
      id: "merchant-tp",
      tone: "sky",
      icon: "🏪",
      title: "Merchant (teleporter)",
      marks: [
        ["merchant_dialogue_box", "Dialogue box", "point"],
        ["merchant_open_button", "Open merchant", "point"],
        ["merchant_name_ocr_pos", "Merchant name OCR"],
        ["item_name_ocr_pos", "Item name OCR"],
        ["merchant_slot_1_pos", "Slot 1", "point"],
        ["merchant_slot_2_pos", "Slot 2", "point"],
        ["merchant_slot_3_pos", "Slot 3", "point"],
        ["merchant_slot_4_pos", "Slot 4", "point"],
        ["merchant_slot_5_pos", "Slot 5", "point"],
        ["purchase_amount_button", "Purchase amount", "point"],
        ["merchant_set_max_button", "Set max", "point"],
        ["purchase_button", "Purchase", "point"],
        ["merchant_close_button", "Close merchant", "point"],
      ],
    },
    {
      id: "buff",
      tone: "yellow",
      icon: "⚡",
      title: "Enable buff",
      marks: [
        ["glitched_menu_button", "Glitched menu"],
        ["glitched_settings_button", "Settings"],
        ["glitched_buff_enable_button", "Enable buff"],
      ],
    },
    {
      id: "aura",
      tone: "purple",
      icon: "✨",
      title: "Equip aura",
      marks: [
        ["aura_menu", "Aura menu"],
        ["aura_search_bar", "Search bar"],
        ["first_aura_slot_pos", "First aura slot"],
        ["equip_aura_button", "Equip"],
      ],
    },
    {
      id: "inventory",
      tone: "lime",
      icon: "🎒",
      title: "Inventory",
      marks: [
        ["inventory_menu", "Open inventory"],
        ["items_tab", "Items tab"],
        ["search_bar", "Search bar"],
        ["first_item_inventory_slot_pos", "First slot"],
        ["first_item_slot_ocr_pos", "First slot OCR (failsafe)"],
        ["amount_box", "Amount box"],
        ["use_button", "Use"],
        ["inventory_close_button", "Close inventory"],
      ],
    },
    {
      id: "potion",
      tone: "amber",
      icon: "⚗",
      title: "Potion crafting",
      marks: [
        ["potion_items_tab", "Items tab"],
        ["potion_search_bar", "Search bar"],
        ["potion_first_potion_slot_pos", "First result"],
        ["potion_recipe_auto_button", "Auto (pre-recipe)"],
        ["potion_recipe_button", "Open recipe"],
        ["potion_auto_add_button", "Add everything"],
        ["potion_craft_button", "Craft"],
      ],
    },
    {
      id: "merchant",
      tone: "cyan",
      icon: "🛒",
      title: "Auto merchant (Mari / Jester)",
      marks: [
        ["merchant_dialogue_box", "Dialogue box", "point"],
        ["merchant_open_button", "Open shop", "point"],
        ["merchant_name_ocr_pos", "Merchant name OCR"],
        ["item_name_ocr_pos", "Item name OCR"],
        ["merchant_slot_1_pos", "Slot 1", "point"],
        ["merchant_slot_2_pos", "Slot 2", "point"],
        ["merchant_slot_3_pos", "Slot 3", "point"],
        ["merchant_slot_4_pos", "Slot 4", "point"],
        ["merchant_slot_5_pos", "Slot 5", "point"],
        ["purchase_amount_button", "Purchase amount", "point"],
        ["merchant_set_max_button", "Set max", "point"],
        ["purchase_button", "Purchase", "point"],
        ["merchant_close_button", "Close", "point"],
      ],
    },
    {
      id: "currency",
      tone: "green",
      icon: "💰",
      title: "Currency screenshot",
      marks: [["currency_region", "Currency region"]],
      currencyControls: true,
    },
    {
      id: "fishing",
      tone: "teal",
      icon: "🎣",
      title: "Fishing",
      subsections: [
        {
          id: "fish-minigame",
          short: "Minigame",
          marks: [
            ["fishing_bar_region", "Bar region"],
            ["fishing_detect_pixel", "Detect pixel"],
            ["fishing_click_position", "Click position"],
            ["fishing_midbar_sample_pos", "Mid-bar sample"],
            ["fishing_close_button_pos", "Close minigame"],
          ],
        },
        {
          id: "fish-shop",
          short: "Flarg & shop",
          marks: [
            ["fishing_flarg_dialogue_box", "Flarg dialogue"],
            ["fishing_shop_open_button", "Open shop"],
            ["fishing_shop_sell_tab", "Sell tab"],
            ["fishing_shop_close_button", "Close shop"],
            ["fishing_shop_first_fish", "First fish slot"],
            ["fishing_shop_sell_all_button", "Sell all"],
            ["fishing_confirm_sell_all_button", "Confirm sell all"],
          ],
        },
      ],
    },
    {
      id: "biome-selector",
      tone: "rose",
      icon: "🗺",
      title: "Biome Selector",
      subsections: [
        {
          id: "bs-ui",
          short: "In-game UI",
          steps: [
            {
              key: "biome_selector_frame_pos",
              title: "Selector window",
              hint: "Full BIOME SELECTOR frame",
            },
            {
              key: "biome_selector_first_drive_pos",
              title: "First drive",
              hint: "Top row — sets W/H",
            },
            {
              key: "biome_selector_confirm_pos",
              title: "Confirm",
              hint: "Popup Confirm button",
            },
          ],
        },
        {
          id: "bs-layout",
          short: "Layout",
          layout: true,
        },
      ],
    },
  ];

  const api = () => window.pywebview?.api;

  const configFlagOn = (value) => {
    if (typeof value === "string") return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    return Boolean(value);
  };

  const potionCraftingOn = (config) => configFlagOn(config?.enable_potion_crafting);

  const syncCurrencySectionVisibility = (hub, config) => {
    if (!hub) return;
    const sec = hub.querySelector('[data-section-id="currency"]');
    if (!sec) return;
    const hidden = potionCraftingOn(config);
    sec.hidden = hidden;
    sec.classList.toggle("blsm-cal-section-suppressed", hidden);
  };

  const formatValue = (raw) => {
    if (!Array.isArray(raw) || raw.length < 2) return "not set";
    if (raw.length >= 4) {
      const cx = Math.round(Number(raw[0]) + Number(raw[2]) / 2);
      const cy = Math.round(Number(raw[1]) + Number(raw[3]) / 2);
      return `${cx}, ${cy} · ${Math.round(raw[2])}×${Math.round(raw[3])}`;
    }
    return raw.slice(0, 2).join(", ");
  };

  const isMarked = (config, key) => {
    const raw = config[key];
    return Array.isArray(raw) && raw.length >= 2;
  };

  const countSectionProgress = (section, config) => {
    let total = 0;
    let done = 0;
    const bump = (key) => {
      total += 1;
      if (isMarked(config, key)) done += 1;
    };
    if (section.marks) section.marks.forEach(([key]) => bump(key));
    if (section.subsections) {
      for (const sub of section.subsections) {
        sub.marks?.forEach(([key]) => bump(key));
        sub.steps?.forEach((s) => bump(s.key));
      }
    }
    return { done, total };
  };

  const cardTitle = (card) =>
    card.querySelector(":scope > .card-header h3")?.textContent?.trim() ||
    card.querySelector(".card-header h3")?.textContent?.trim() ||
    card.querySelector("h3")?.textContent?.trim() ||
    "";

  const isCalibrationAccordionCard = (card) => {
    if (!card?.classList?.contains("card")) return false;
    const sub = card.querySelector(":scope > .card-header p, .card-header p");
    if (sub?.textContent?.includes("Click to view/edit coordinates")) return true;
    const title = cardTitle(card);
    if (!title) return false;
    if (NATIVE_HIDE_TITLES.has(title)) return true;
    return NATIVE_HIDE_TITLE_PATTERNS.some((re) => re.test(title));
  };

  const shouldKeepMacroCalCard = (card) => {
    if (card.id === HUB_ID) return true;
    if (card.classList.contains("blsm-mouse-cal-card")) return true;
    if (card.classList.contains("blsm-cal-preset-card")) return true;
    if (cardTitle(card) === "Macro Calibrations Preset") return true;
    return false;
  };

  const macroCalRoot = () =>
    document.querySelector('.page-content[data-blossom-page="Macro Calibrations"]') ||
    (pageHeaderTitle?.() === "Macro Calibrations"
      ? document.querySelector(".page-content") || document.querySelector(".main-content")
      : null);

  const relocateCalHint = () => {
    const hub = document.getElementById(HUB_ID);
    const root = macroCalRoot();
    if (!hub || !root) return;
    const hintSlot = hub.querySelector(".blsm-cal-hub-hint");
    if (!hintSlot) return;
    const banner = root.querySelector(":scope > .info-banner");
    if (!banner || hintSlot.contains(banner)) return;
    banner.classList.add("blsm-cal-hint-in-hub");
    hintSlot.appendChild(banner);
  };

  const enhancePresetCard = () => {
    const root = macroCalRoot();
    if (!root) return;
    const hub = document.getElementById(HUB_ID);
    const slot = hub?.querySelector(".blsm-cal-preset-slot");
    for (const card of root.querySelectorAll(".card")) {
      const title = cardTitle(card);
      if (title !== "Macro Calibrations Preset") continue;
      card.classList.add("blsm-cal-preset-card", "blsm-md-card");
      card.style.marginBottom = "0";
      if (slot) {
        if (card.parentElement !== slot) slot.appendChild(card);
        return;
      }
      if (hub?.parentElement && card.parentElement === hub.parentElement) {
        hub.parentElement.insertBefore(card, hub);
      }
    }
  };

  const hideLegacyCalibrationUI = () => {
    const root = macroCalRoot();
    if (!root) return;
    relocateCalHint();
    for (const card of root.querySelectorAll(".card")) {
      const title = cardTitle(card);
      if (title === "Macro Calibrations Preset") {
        card.classList.add("blsm-cal-preset-card", "blsm-md-card");
        card.classList.remove("blsm-cal-legacy-hidden", "blsm-cal-native-hidden", "blsm-native-cal");
        card.removeAttribute("hidden");
        card.hidden = false;
        continue;
      }
      if (shouldKeepMacroCalCard(card)) continue;
      if (isCalibrationAccordionCard(card) || card.classList.contains("blsm-native-cal")) {
        card.classList.add("blsm-native-cal", "blsm-cal-legacy-hidden", "blsm-cal-native-hidden");
        card.setAttribute("hidden", "");
        card.setAttribute("aria-hidden", "true");
      }
    }
    root.querySelectorAll(".blsm-native-cal-list, #blsm-native-cal-list").forEach((el) => {
      el.classList.add("blsm-cal-native-hidden");
      el.remove();
    });
    enhancePresetCard();
  };

  hideLegacyDebounced =
    typeof debounce === "function" ? debounce(hideLegacyCalibrationUI, 100) : hideLegacyCalibrationUI;

  const teardownLegacyHideWatch = () => {
    legacyHideObserver?.disconnect();
    legacyHideObserver = null;
  };

  const armLegacyHideWatch = (root) => {
    hideLegacyCalibrationUI();
    if (!legacyHideObserver) {
      legacyHideObserver = new MutationObserver((mutations) => {
        if (mutations.length && mutations.every(legacyHideIgnoresMutation)) return;
        (hideLegacyDebounced || hideLegacyCalibrationUI)();
      });
      legacyHideObserver.observe(root, { childList: true, subtree: true });
    }
  };

  const armMark = async (bridge, key, statusEl, coordsEl, onSaved, mode = "region") => {
    const begin = bridge?.create_calibration_window || bridge?.begin_calibration_point;
    if (!begin) return;
    const fn = bridge.create_calibration_window || bridge.begin_calibration_point;
    const captureMode = mode === "point" ? "point" : "region";
    const result = await fn.call(bridge, key, captureMode);
    statusEl.textContent = result?.status || result?.error || "Drag a box in Roblox (ESC cancels).";
    if (!result || result.ok === false) return;
    const startSeq = Number(result.seq || 0);
    let attempts = 0;
    const poll = setInterval(async () => {
      attempts += 1;
      let capture = null;
      try {
        capture = (await bridge.get_calibration_status?.())?.capture;
      } catch {}
      if (
        capture &&
        capture.key === key &&
        Number(capture.seq || 0) > startSeq &&
        Array.isArray(capture.value)
      ) {
        coordsEl.textContent = formatValue(capture.value);
        statusEl.textContent = `Saved ${key}`;
        clearInterval(poll);
        if (onSaved) onSaved(key, capture.value);
      } else if (attempts >= 40) {
        statusEl.textContent = "No drag saved — try again.";
        clearInterval(poll);
      }
    }, 450);
  };

  const markSpec = (entry) => {
    const [key, label, mode] = entry;
    return { key, label, mode: mode || "region" };
  };

  const buildMarkRow = (bridge, statusEl, config, key, label, onSaved, mode = "region") => {
    const row = document.createElement("div");
    row.className = "blsm-cal-mark-row" + (isMarked(config, key) ? " is-done" : "");
    row.dataset.calKey = key;
    row.innerHTML = `
      <span class="blsm-cal-mark-label">${label}</span>
      <span class="blsm-cal-mark-coords">${formatValue(config[key])}</span>
    `;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-accent";
    btn.textContent = "Mark";
    btn.addEventListener("click", async () => {
      const coordsEl = row.querySelector(".blsm-cal-mark-coords");
      await armMark(bridge, key, statusEl, coordsEl, (k, val) => {
        row.classList.add("is-done");
        if (onSaved) onSaved(k, val);
      }, mode);
    });
    row.appendChild(btn);
    return row;
  };

  const buildMarkList = (host, bridge, statusEl, config, marks, onSaved) => {
    host.innerHTML = "";
    const list = document.createElement("div");
    list.className = "blsm-cal-mark-list";
    for (const entry of marks) {
      const { key, label, mode } = markSpec(entry);
      list.appendChild(buildMarkRow(bridge, statusEl, config, key, label, onSaved, mode));
    }
    host.appendChild(list);
  };

  const buildStepList = (host, bridge, statusEl, config, steps, onSaved) => {
    host.innerHTML = "";
    const list = document.createElement("div");
    list.className = "blsm-cal-step-list";
    steps.forEach((step, i) => {
      const row = document.createElement("div");
      row.className = "blsm-cal-step-row" + (isMarked(config, step.key) ? " is-done" : "");
      row.dataset.calKey = step.key;
      row.innerHTML = `
        <div class="blsm-cal-step-num">${i + 1}</div>
        <div class="blsm-cal-step-copy">
          <strong>${step.title}</strong>
          <span>${step.hint}</span>
          <span class="blsm-cal-mark-coords">${formatValue(config[step.key])}</span>
        </div>
      `;
      const markBtn = document.createElement("button");
      markBtn.type = "button";
      markBtn.className = "btn btn-accent";
      markBtn.textContent = "Mark";
      markBtn.addEventListener("click", async () => {
        const coordsEl = row.querySelector(".blsm-cal-mark-coords");
        await armMark(bridge, step.key, statusEl, coordsEl, (k, val) => {
          row.classList.add("is-done");
          coordsEl.textContent = formatValue(val);
          if (onSaved) onSaved(k, val);
        });
      });
      row.appendChild(markBtn);
      list.appendChild(row);
    });
    host.appendChild(list);
  };

  const buildLayoutBlock = (host, bridge) => {
    host.setAttribute("data-layout-host", "1");
    host.innerHTML = `
      <p class="form-hint" style="margin:0 0 6px;font-size:10px;">
        Row Y = first Y + index × (height + gap). Default gap 2px.
      </p>
      <div class="blsm-cal-layout-grid">
        <label>W<input type="number" min="20" class="form-input blsm-cal-layout-w" /></label>
        <label>H<input type="number" min="12" class="form-input blsm-cal-layout-h" /></label>
        <label>Rows<input type="number" min="1" max="24" class="form-input blsm-cal-layout-n" /></label>
        <label>Gap<input type="number" min="0" max="40" class="form-input blsm-cal-layout-gap" /></label>
      </div>
      <div class="blsm-cal-preview blsm-cal-preview-body"></div>
    `;
    const saveLayout = async () => {
      if (!bridge?.save_biome_selector_layout) return;
      await bridge.save_biome_selector_layout({
        biome_selector_button_width: Number(host.querySelector(".blsm-cal-layout-w").value),
        biome_selector_button_height: Number(host.querySelector(".blsm-cal-layout-h").value),
        biome_selector_button_count: Number(host.querySelector(".blsm-cal-layout-n").value),
        biome_selector_button_spacing: Number(host.querySelector(".blsm-cal-layout-gap").value),
      });
      await refreshBiomeLayout(host, bridge);
    };
    for (const el of host.querySelectorAll(".blsm-cal-layout-w, .blsm-cal-layout-h, .blsm-cal-layout-n, .blsm-cal-layout-gap")) {
      el.addEventListener("change", saveLayout);
    }
    refreshBiomeLayout(host, bridge);
  };

  const refreshBiomeLayout = async (host, bridge) => {
    if (!bridge?.get_biome_selector_status) return;
    let status = {};
    try {
      status = await bridge.get_biome_selector_status();
    } catch {
      return;
    }
    const layout = status.layout || {};
    const w = host.querySelector(".blsm-cal-layout-w");
    const h = host.querySelector(".blsm-cal-layout-h");
    const n = host.querySelector(".blsm-cal-layout-n");
    const g = host.querySelector(".blsm-cal-layout-gap");
    if (w) w.value = layout.button_width ?? 280;
    if (h) h.value = layout.button_height ?? 32;
    if (n) n.value = layout.button_count ?? 8;
    if (g) g.value = layout.button_spacing ?? 2;
    const preview = host.querySelector(".blsm-cal-preview-body");
    if (!preview) return;
    const slots = status.slots || [];
    if (!slots.length) {
      preview.innerHTML = '<p class="form-hint" style="margin:0;padding:6px;">Mark first drive for row preview.</p>';
      return;
    }
    preview.innerHTML = `<table><thead><tr><th>#</th><th>X</th><th>Y</th></tr></thead><tbody>${slots
      .map((s) => `<tr><td>${s.index}</td><td>${s.x}</td><td>${s.y}</td></tr>`)
      .join("")}</tbody></table>`;
  };

  const buildCurrencyExtra = (host, bridge) => {
    bridge?.get_config?.().then((config) => {
      config = config || {};
      if (potionCraftingOn(config)) return;
      const enabled = !!config.currency_screenshot;
      const interval = Number(config.currency_screenshot_interval) || 15;
      const wrap = document.createElement("div");
      wrap.innerHTML = `
        <div class="blsm-cal-currency-extra">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
            <input type="checkbox" class="blsm-cal-cur-on" ${enabled ? "checked" : ""} />
            <span>Webhook currency screenshots</span>
          </label>
          <label style="display:flex;align-items:center;gap:8px;">
            <span style="min-width:88px;">Every (min)</span>
            <input type="number" min="1" class="form-input blsm-cal-cur-int" value="${interval}" style="max-width:72px;" />
          </label>
          <button type="button" class="btn btn-accent blsm-cal-cur-send">Send now</button>
        </div>
      `;
      host.appendChild(wrap);
      const persist = async (patch) => {
        const cur = await bridge.get_config();
        await bridge.save_config({ ...cur, ...patch });
      };
      wrap.querySelector(".blsm-cal-cur-on").addEventListener("change", (e) => {
        persist({ currency_screenshot: !!e.target.checked });
      });
      wrap.querySelector(".blsm-cal-cur-int").addEventListener("change", (e) => {
        const v = Math.max(1, Math.round(Number(e.target.value) || 15));
        e.target.value = v;
        persist({ currency_screenshot_interval: v });
      });
      wrap.querySelector(".blsm-cal-cur-send").addEventListener("click", async () => {
        const status = document.querySelector(`#${HUB_ID} .blsm-cal-status`);
        if (status) status.textContent = "Sending…";
        try {
          const res = await bridge.send_currency_screenshot_now?.();
          if (status) status.textContent = res?.status || res?.error || "Done";
        } catch (e) {
          if (status) status.textContent = String(e);
        }
      });
    });
  };

  const buildSectionTabs = (section, bridge, statusEl, config, onSaved) => {
    const wrap = document.createElement("div");
    wrap.className = "blsm-cal-tabs-wrap";
    const nav = document.createElement("div");
    nav.className = "blsm-cal-tab-nav";
    nav.setAttribute("role", "tablist");
    const panels = document.createElement("div");
    panels.className = "blsm-cal-tab-panels blsm-morph-tab-panels";

    const activate = (tabId) => {
      nav.querySelectorAll(".blsm-cal-tab").forEach((t) => {
        const on = t.dataset.tabId === tabId;
        t.classList.toggle("is-active", on);
        t.setAttribute("aria-selected", on ? "true" : "false");
      });
      panels.querySelectorAll(".blsm-cal-tab-panel").forEach((p) => {
        const on = p.dataset.tabId === tabId;
        p.classList.toggle("is-active", on);
        p.hidden = !on;
      });
      const scroll = wrap.closest(".blsm-morph-panel, .blsm-cal-section-scroll");
      if (triggerMorphSwap) triggerMorphSwap(scroll);
      else if (scroll) {
        scroll.classList.remove("blsm-morph-swap");
        void scroll.offsetWidth;
        scroll.classList.add("blsm-morph-swap");
      }
    };

    section.subsections.forEach((sub, i) => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = "blsm-cal-tab" + (i === 0 ? " is-active" : "");
      tab.textContent = sub.short || sub.title;
      tab.dataset.tabId = sub.id;
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", i === 0 ? "true" : "false");
      tab.addEventListener("click", () => activate(sub.id));
      nav.appendChild(tab);

      const panel = document.createElement("div");
      panel.className = "blsm-cal-tab-panel blsm-morph-tab-panel" + (i === 0 ? " is-active" : "");
      panel.dataset.tabId = sub.id;
      panel.setAttribute("role", "tabpanel");
      panel.hidden = i !== 0;
      if (sub.marks) buildMarkList(panel, bridge, statusEl, config, sub.marks, onSaved);
      if (sub.steps) buildStepList(panel, bridge, statusEl, config, sub.steps, onSaved);
      if (sub.layout) buildLayoutBlock(panel, bridge);
      panels.appendChild(panel);
    });

    wrap.appendChild(nav);
    wrap.appendChild(panels);
    return wrap;
  };

  const closeOtherSections = (hub, keepSec) => {
    hub.querySelectorAll(".blsm-cal-section.is-open").forEach((s) => {
      if (s === keepSec) return;
      s.classList.remove("is-open");
      const head = s.querySelector(".blsm-cal-section-head");
      if (head) head.setAttribute("aria-expanded", "false");
    });
  };

  const refreshHub = async (hub) => {
    const bridge = api();
    if (!bridge?.get_config) return;
    let config = {};
    try {
      config = await bridge.get_config();
    } catch {
      return;
    }
    for (const section of SECTIONS) {
      const prog = countSectionProgress(section, config);
      const progEl = hub.querySelector(`[data-section-progress="${section.id}"]`);
      if (progEl) progEl.textContent = prog.total ? `${prog.done}/${prog.total}` : "";
    }
    hub.querySelectorAll("[data-cal-key]").forEach((row) => {
      const key = row.dataset.calKey;
      if (!key) return;
      row.classList.toggle("is-done", isMarked(config, key));
      const coords = row.querySelector(".blsm-cal-mark-coords");
      if (coords) coords.textContent = formatValue(config[key]);
    });
    const layoutHost = hub.querySelector("[data-layout-host]");
    if (layoutHost) refreshBiomeLayout(layoutHost, bridge);
    syncCurrencySectionVisibility(hub, config);
    hideLegacyCalibrationUI();
  };

  const mountHub = async () => {
    if (document.getElementById(HUB_ID)) {
      hideLegacyCalibrationUI();
      relocateCalHint();
      enhancePresetCard();
      return;
    }

    const bridge = api();
    let config = {};
    if (bridge?.get_config) {
      try {
        config = await bridge.get_config();
      } catch {}
    }

    const hub = document.createElement("div");
    hub.id = HUB_ID;
    hub.className = "card blsm-md-card";
    hub.dataset.blsmMd = "1";
    hub.innerHTML = `
      <div class="blsm-cal-hub-top">
        <div>
          <h3>Macro calibrations</h3>
          <p>All macro marks in one panel — expand a category, use tabs for sub-groups, then Mark in Roblox. One section open at a time.</p>
        </div>
      </div>
      <div class="blsm-cal-hub-hint" aria-label="Calibration tips"></div>
      <div class="blsm-cal-sections"></div>
      <div class="blsm-cal-preset-slot" aria-label="Macro calibrations preset"></div>
      <p class="blsm-cal-status" role="status"></p>
    `;

    const sectionsHost = hub.querySelector(".blsm-cal-sections");
    const statusEl = hub.querySelector(".blsm-cal-status");
    const onSaved = () => refreshHub(hub);

    for (const section of SECTIONS) {
      const prog = countSectionProgress(section, config);
      const sec = document.createElement("section");
      const openDefault = section.id === "movements";
      sec.className = "blsm-cal-section" + (openDefault ? " is-open" : "");
      sec.dataset.sectionId = section.id;
      if (section.tone) sec.dataset.tone = section.tone;
      sec.innerHTML = `
        <button type="button" class="blsm-cal-section-head" aria-expanded="${openDefault}">
          <div class="blsm-cal-section-title">
            <span class="blsm-cal-section-icon">${section.icon}</span>
            <div class="blsm-cal-section-text">
              <strong>${section.title}</strong>
            </div>
          </div>
          <div class="blsm-cal-section-meta">
            <span class="blsm-cal-progress" data-section-progress="${section.id}">${prog.done}/${prog.total}</span>
            ${CHEVRON}
          </div>
        </button>
        <div class="blsm-cal-section-body blsm-morph-body">
          <div class="blsm-cal-section-collapse blsm-morph-collapse">
            <div class="blsm-cal-section-scroll blsm-cal-section-content blsm-morph-panel"></div>
          </div>
        </div>
      `;

      const head = sec.querySelector(".blsm-cal-section-head");
      head.addEventListener("click", (e) => {
        e.stopPropagation();
        const opening = !sec.classList.contains("is-open");
        if (opening) closeOtherSections(hub, sec);
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

      const content = sec.querySelector(".blsm-cal-section-content");
      if (section.subsections) {
        content.appendChild(buildSectionTabs(section, bridge, statusEl, config, onSaved));
      } else if (section.marks) {
        buildMarkList(content, bridge, statusEl, config, section.marks, onSaved);
        if (section.currencyControls) buildCurrencyExtra(content, bridge);
      }

      sectionsHost.appendChild(sec);
    }

    const header = document.querySelector(".page-header");
    const mouseCal = document.querySelector(".blsm-mouse-cal-card");
    if (mouseCal) mouseCal.insertAdjacentElement("afterend", hub);
    else if (header) header.insertAdjacentElement("afterend", hub);
    else document.querySelector(".page-content")?.prepend(hub);

    hideLegacyCalibrationUI();
    relocateCalHint();
    enhancePresetCard();

    window.onCalibrationResult = () => refreshHub(hub);

    await refreshHub(hub);
    syncCurrencySectionVisibility(hub, config);
    hideLegacyCalibrationUI();
    relocateCalHint();
    enhancePresetCard();
  };

  const ensurePotionCraftingLink = () => {
    if (pageHeaderTitle() !== "Potion Crafting") {
      document.getElementById(LINK_ID)?.remove();
      return;
    }
    if (document.getElementById(LINK_ID)) return;
    const header = document.querySelector(".page-header");
    if (!header) return;
    const banner = document.createElement("div");
    banner.id = LINK_ID;
    banner.className = "card blossom-cal-link-card";
    banner.style.marginBottom = "16px";
    banner.innerHTML = `
      <div style="padding:14px 18px;display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;">
        <div>
          <div style="font-weight:700;color:var(--accent-text);margin-bottom:4px;">Calibrations</div>
          <div class="form-hint" style="margin:0;">All marks live under grouped sections on Macro Calibrations.</div>
        </div>
        <button type="button" class="btn btn-accent blossom-open-calibrations">Open Macro Calibrations</button>
      </div>
    `;
    banner.querySelector(".blossom-open-calibrations").addEventListener("click", () => {
      goToTab?.("Calibrations");
    });
    header.insertAdjacentElement("afterend", banner);
  };

  const sync = async () => {
    const title = pageHeaderTitle();
    if (title === "Potion Crafting") {
      document.getElementById(HUB_ID)?.remove();
      ensurePotionCraftingLink();
      return;
    }
    document.getElementById(LINK_ID)?.remove();
    if (title !== "Macro Calibrations") {
      document.getElementById(HUB_ID)?.remove();
      teardownLegacyHideWatch();
      return;
    }
    await mountHub();
    hideLegacyCalibrationUI();
    relocateCalHint();
    enhancePresetCard();
    const root = macroCalRoot();
    if (root) armLegacyHideWatch(root);
  };

  window.Blossom = window.Blossom || {};
  window.Blossom.hideMacroCalibrationLegacy = hideLegacyCalibrationUI;

  if (observeMain) observeMain(() => sync(), 0, ["Macro Calibrations", "Potion Crafting"]);
  else {
    sync();
    window.addEventListener("pywebviewready", sync);
  }
})();
