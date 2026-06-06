(function () {
  const HUB_ID = "blsm-biome-webhooks-hub";
  const RARE = new Set(["GLITCHED", "DREAMSPACE", "CYBERSPACE"]);
  const ORDER = [
    "GLITCHED",
    "DREAMSPACE",
    "CYBERSPACE",
    "WINDY",
    "RAINY",
    "SNOWY",
    "SAND STORM",
    "HELL",
    "STARFALL",
    "CORRUPTION",
    "NULL",
    "AURORA",
    "HEAVEN",
    "EGGLAND",
    "SINGULARITY",
  ];

  const COLOR_FALLBACK = {
    GLITCHED: "#bfff00",
    DREAMSPACE: "#ea9dda",
    CYBERSPACE: "#0A1A3D",
    WINDY: "#9ae5ff",
    RAINY: "#027cbd",
    SNOWY: "#Dceff9",
    "SAND STORM": "#8F7057",
    HELL: "#ff4719",
    STARFALL: "#011ab7",
    CORRUPTION: "#6d32a8",
    NULL: "#838383",
    AURORA: "#56d6a0",
    HEAVEN: "#dfaf63",
    EGGLAND: "#d4fc8d",
    SINGULARITY: "#cf4023",
  };

  const { observeMain } = window.Blossom || {};
  const api = () => window.pywebview?.api;

  let saveTimer = null;
  let state = null;

  const isWebhookPage = () => {
    const h = document.querySelector(".page-header h2");
    return h && h.textContent.trim() === "Webhook";
  };

  const parseIds = (text) => {
    const out = [];
    const seen = new Set();
    for (const part of String(text || "").split(/[\s,;]+/)) {
      const id = part.trim();
      if (/^\d+$/.test(id) && !seen.has(id)) {
        seen.add(id);
        out.push(id);
      }
    }
    return out;
  };

  const joinIds = (list) => (Array.isArray(list) ? list.join(", ") : "");

  const sortBiomes = (names) => {
    const set = new Set(names.filter((n) => n && n !== "NORMAL"));
    return [...set].sort((a, b) => {
      const ia = ORDER.indexOf(a);
      const ib = ORDER.indexOf(b);
      if (ia !== -1 && ib !== -1) return ia - ib;
      if (ia !== -1) return -1;
      if (ib !== -1) return 1;
      return a.localeCompare(b);
    });
  };

  const biomeColor = (name, biomeData) => {
    const raw = biomeData?.[name]?.color;
    if (typeof raw === "string" && raw.startsWith("0x")) {
      return `#${raw.slice(2)}`;
    }
    return COLOR_FALLBACK[name] || "#9ca3af";
  };

  const defaultPing = (biome, globalRare) => ({
    users: [],
    roles: [],
    mention_everyone: RARE.has(biome) && globalRare !== "users",
    rare_mention_mode: RARE.has(biome) ? globalRare : "users",
  });

  const ensurePing = (config, biome) => {
    const globalRare = config.rare_biome_mention_mode || "both";
    const pings = config.biome_pings || {};
    const key = biome;
    const cur = pings[key] || pings[biome.toUpperCase()];
    if (cur && Array.isArray(cur.users) && Array.isArray(cur.roles)) {
      return { ...defaultPing(biome, globalRare), ...cur };
    }
    if (cur && cur.id) {
      const type = String(cur.type || "userid").toLowerCase();
      const id = String(cur.id || "").trim();
      if (type.includes("role") && id) {
        return { ...defaultPing(biome, globalRare), roles: [id], users: [] };
      }
      if (id && /^\d+$/.test(id)) {
        return { ...defaultPing(biome, globalRare), users: [id], roles: [] };
      }
    }
    return defaultPing(biome, globalRare);
  };

  const notifyOn = (config, biome) => {
    const notifier = config.biome_notifier || {};
    const val = notifier[biome] ?? notifier[biome.toUpperCase()];
    if (typeof val === "boolean") return val;
    if (val == null) return false;
    const s = String(val).trim().toLowerCase();
    if (["none", "off", "false", "0", ""].includes(s)) return false;
    if (["message", "on", "true", "1", "yes"].includes(s)) return true;
    return Boolean(val);
  };

  const scheduleSave = (patch) => {
    if (!state) return;
    Object.assign(state, patch);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(async () => {
      const bridge = api();
      if (!bridge?.save_config) return;
      try {
        await bridge.save_config({ ...state });
      } catch (err) {
        console.warn("[biome-webhooks] save failed", err);
      }
    }, 280);
  };

  const setNotifier = (biome, enabled) => {
    const notifier = { ...(state.biome_notifier || {}) };
    notifier[biome] = enabled;
    scheduleSave({ biome_notifier: notifier });
    const row = document.querySelector(`tr[data-biome="${biome}"] input.blsm-bwh-notify-cb`);
    if (row) row.checked = enabled;
  };

  const setPingField = (biome, field, value) => {
    const pings = { ...(state.biome_pings || {}) };
    const entry = ensurePing(state, biome);
    if (field === "users" || field === "roles") {
      entry[field] = parseIds(value);
    } else if (field === "rare_mention_mode") {
      entry.rare_mention_mode = value;
      entry.mention_everyone = value === "everyone" || value === "both";
    }
    pings[biome] = entry;
    scheduleSave({ biome_pings: pings });
  };

  const hideLegacyCard = () => {
    document.documentElement.classList.add("blsm-biome-webhooks-active");
    for (const card of document.querySelectorAll(".card")) {
      const h3 = card.querySelector("h3");
      if (h3 && h3.textContent.trim() === "Biome Configuration") {
        card.classList.add("blsm-legacy-biome-config-card");
      }
    }
  };

  const unhideLegacy = () => {
    document.documentElement.classList.remove("blsm-biome-webhooks-active");
    document.querySelectorAll(".blsm-legacy-biome-config-card").forEach((el) => {
      el.classList.remove("blsm-legacy-biome-config-card");
    });
  };

  const renderRow = (biome, biomeData) => {
    const tr = document.createElement("tr");
    tr.dataset.biome = biome;
    if (RARE.has(biome)) tr.classList.add("blsm-bwh-row-rare");

    const ping = ensurePing(state, biome);
    const enabled = notifyOn(state, biome);
    const color = biomeColor(biome, biomeData);

    tr.innerHTML = `
      <td>
        <div class="blsm-bwh-name">
          <span class="blsm-bwh-dot" style="background:${color}"></span>
          <span>${biome}</span>
          ${RARE.has(biome) ? '<span class="blsm-bwh-rare-badge">Rare</span>' : ""}
        </div>
      </td>
      <td class="blsm-bwh-notify">
        <input type="checkbox" class="blsm-bwh-notify-cb" ${enabled ? "checked" : ""} aria-label="Notify ${biome}" />
      </td>
      <td>
        <input class="form-input blsm-bwh-users" type="text" placeholder="123456789, …" value="${joinIds(ping.users)}" />
      </td>
      <td>
        <input class="form-input blsm-bwh-roles" type="text" placeholder="987654321, …" value="${joinIds(ping.roles)}" />
      </td>
      <td class="blsm-bwh-rare-cell"></td>
    `;

    tr.querySelector(".blsm-bwh-notify-cb").addEventListener("change", (e) => {
      setNotifier(biome, !!e.target.checked);
    });
    tr.querySelector(".blsm-bwh-users").addEventListener("change", (e) => {
      setPingField(biome, "users", e.target.value);
    });
    tr.querySelector(".blsm-bwh-roles").addEventListener("change", (e) => {
      setPingField(biome, "roles", e.target.value);
    });

    const rareCell = tr.querySelector(".blsm-bwh-rare-cell");
    if (RARE.has(biome)) {
      const sel = document.createElement("select");
      sel.className = "form-input blsm-bwh-rare-mode";
      for (const mode of [
        ["users", "Ping users/roles only"],
        ["everyone", "@everyone only"],
        ["both", "@everyone + users/roles"],
      ]) {
        const opt = document.createElement("option");
        opt.value = mode[0];
        opt.textContent = mode[1];
        sel.appendChild(opt);
      }
      sel.value = ping.rare_mention_mode || state.rare_biome_mention_mode || "both";
      sel.addEventListener("change", (e) => setPingField(biome, "rare_mention_mode", e.target.value));
      rareCell.appendChild(sel);
    } else {
      rareCell.innerHTML = '<span style="color:var(--text-muted);font-size:11px;">—</span>';
    }

    return tr;
  };

  const mountHub = async () => {
    const main =
      document.querySelector(".page-content") ||
      document.querySelector(".main-content");
    if (!main || document.getElementById(HUB_ID)) return;

    const bridge = api();
    if (!bridge?.get_config) return;

    let config = {};
    let biomeData = {};
    try {
      config = await bridge.get_config();
      biomeData = (await bridge.get_biome_data?.()) || {};
    } catch (err) {
      console.warn("[biome-webhooks] load failed", err);
      return;
    }

    state = config;
    const biomes = sortBiomes([
      ...Object.keys(biomeData || {}),
      ...Object.keys(config.biome_notifier || {}),
      ...Object.keys(config.biome_pings || {}),
    ]);

    const hub = document.createElement("div");
    hub.id = HUB_ID;
    hub.className = "card";
    hub.innerHTML = `
      <div class="corner-bracket tl"></div><div class="corner-bracket tr"></div>
      <div class="corner-bracket bl"></div><div class="corner-bracket br"></div>
      <div class="card-header">
        <div class="card-icon">🌍</div>
        <div>
          <h3>Biome Notifier</h3>
          <p>Turn on alerts per biome and choose who gets pinged in Discord</p>
        </div>
      </div>
      <div class="blsm-bwh-toolbar">
        <span class="form-hint" style="margin:0;">Comma-separated numeric IDs. Rare biomes can use @everyone, specific users, or both.</span>
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <button type="button" class="btn btn-secondary blsm-bwh-all-on">Enable all</button>
          <button type="button" class="btn btn-secondary blsm-bwh-all-off">Disable all</button>
        </div>
      </div>
      <div class="blsm-bwh-global">
        <label>
          <span>Default rare-biome ping mode</span>
          <select class="form-input blsm-bwh-global-rare">
            <option value="both">@everyone + users/roles</option>
            <option value="everyone">@everyone only</option>
            <option value="users">Users/roles only</option>
          </select>
        </label>
      </div>
      <div class="blsm-bwh-table-wrap">
        <table class="blsm-bwh-table">
          <thead>
            <tr>
              <th>Biome</th>
              <th style="width:72px;text-align:center;">Notify</th>
              <th>User ID(s)</th>
              <th>Role ID(s)</th>
              <th style="min-width:180px;">Rare ping mode</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="blsm-bwh-footnote">
        <span class="blsm-bwh-footnote-tag">Rare ping mode</span>
        <p>
          GLITCHED, DREAMSPACE, and CYBERSPACE can ping @everyone — choose how in the Rare ping mode column.
          Every other biome only pings the user and role IDs you enter; @everyone is never used for them.
        </p>
      </div>
    `;

    const header = main.querySelector(".page-header");
    if (header) header.insertAdjacentElement("afterend", hub);
    else main.prepend(hub);

    const tbody = hub.querySelector("tbody");
    for (const biome of biomes) {
      tbody.appendChild(renderRow(biome, biomeData));
    }

    const globalRare = hub.querySelector(".blsm-bwh-global-rare");
    globalRare.value = state.rare_biome_mention_mode || "both";
    globalRare.addEventListener("change", (e) => {
      scheduleSave({ rare_biome_mention_mode: e.target.value });
    });

    hub.querySelector(".blsm-bwh-all-on").addEventListener("click", () => {
      const notifier = { ...(state.biome_notifier || {}) };
      for (const biome of biomes) notifier[biome] = true;
      scheduleSave({ biome_notifier: notifier });
      hub.querySelectorAll(".blsm-bwh-notify-cb").forEach((cb) => {
        cb.checked = true;
      });
    });
    hub.querySelector(".blsm-bwh-all-off").addEventListener("click", () => {
      const notifier = { ...(state.biome_notifier || {}) };
      for (const biome of biomes) notifier[biome] = false;
      scheduleSave({ biome_notifier: notifier });
      hub.querySelectorAll(".blsm-bwh-notify-cb").forEach((cb) => {
        cb.checked = false;
      });
    });

    hideLegacyCard();
  };

  const sync = async () => {
    if (!isWebhookPage()) {
      document.getElementById(HUB_ID)?.remove();
      unhideLegacy();
      state = null;
      return;
    }
    await mountHub();
  };

  if (observeMain) observeMain(() => sync(), 0, "Webhook");
  else {
    sync();
    window.addEventListener("pywebviewready", sync);
  }
})();
