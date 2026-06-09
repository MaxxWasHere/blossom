(function () {
  const { observeMain, pageHeaderTitle, debounce } = window.Blossom || {};
  const POTION_PANEL_ID = "blossom-potion-manager";
  const CRAFT_ID = "coteab-potion-craft-buttons";

  const api = () => window.pywebview && window.pywebview.api;

  const isPotionCraftingPage = () => pageHeaderTitle() === "Potion Crafting";

  const potionNameFromFile = (name) => String(name || "").replace(/\.json$/i, "").trim();

  const findAutoCraftCard = () => {
    const cards = Array.from(document.querySelectorAll(".card"));
    return (
      cards.find((card) => {
        const h3 = card.querySelector("h3");
        return h3 && h3.textContent.trim() === "Auto Craft";
      }) || null
    );
  };

  const findPotionPageHeader = () => {
    const headers = Array.from(document.querySelectorAll(".page-header"));
    return headers.find((el) => el.querySelector("h2")?.textContent?.trim() === "Potion Crafting") || null;
  };

  const findPotionSwitchingCard = () => {
    const cards = Array.from(document.querySelectorAll(".card"));
    return (
      cards.find((card) => {
        const h3 = card.querySelector("h3");
        return h3 && h3.textContent.trim() === "Potion Switching";
      }) || null
    );
  };

  const configFlagOn = (value) => {
    if (typeof value === "string") return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    return Boolean(value);
  };

  const gatePotionSwitching = async () => {
    const craftCard = findAutoCraftCard();
    const switchCard = findPotionSwitchingCard();
    if (!switchCard) return;

    const bridge = api();
    const config = bridge?.get_config ? await bridge.get_config().catch(() => ({})) : {};
    const craftOn = configFlagOn(config.enable_potion_crafting);

    let hint = switchCard.querySelector(".blossom-switch-craft-hint");
    const body = switchCard.querySelector("div[style*='padding']") || switchCard;

    if (!craftOn) {
      switchCard.classList.add("blossom-switching-locked");
      switchCard.style.opacity = "0.55";
      if (!hint) {
        hint = document.createElement("p");
        hint.className = "form-hint blossom-switch-craft-hint";
        hint.style.margin = "0 0 12px";
        hint.style.color = "var(--text-muted)";
        hint.textContent =
          "Enable Auto Craft above first — potion switching only runs when auto craft is on.";
        body.insertBefore(hint, body.firstChild);
      }
      switchCard.querySelectorAll('input[type="checkbox"]').forEach((el) => {
        el.checked = false;
      });
      switchCard.querySelectorAll("input, select, button").forEach((el) => {
        el.disabled = true;
        el.setAttribute("aria-disabled", "true");
      });
      if (configFlagOn(config.enable_potion_switching) && bridge?.save_config) {
        const next = { ...config, enable_potion_switching: false };
        await bridge.save_config(next);
      }
    } else {
      switchCard.classList.remove("blossom-switching-locked");
      switchCard.style.opacity = "";
      hint?.remove();
      switchCard.querySelectorAll("input, select, button").forEach((el) => {
        el.disabled = false;
        el.removeAttribute("aria-disabled");
      });
    }

    if (craftCard && !craftCard.dataset.blossomCraftGate) {
      craftCard.dataset.blossomCraftGate = "1";
      craftCard.addEventListener(
        "change",
        (event) => {
          if (event.target?.type === "checkbox") void gatePotionSwitching();
        },
        true
      );
    }
  };

  const refreshSwitchingSelects = async () => {
    const card = findPotionSwitchingCard();
    if (!card) return;
    const bridge = api();
    if (!bridge?.list_potion_files) return;

    let files = [];
    try {
      files = await bridge.list_potion_files();
    } catch {
      return;
    }

    const config = bridge.get_config ? await bridge.get_config().catch(() => ({})) : {};
    const keys = ["potion_file_1", "potion_file_2", "potion_file_3"];
    const labels = ["Select potion #1", "Select potion #2", "Select potion #3"];
    const groups = Array.from(card.querySelectorAll(".form-group"));
    groups.forEach((group, index) => {
      const label = group.querySelector(".form-label");
      if (!label || !labels.includes(label.textContent.trim())) return;
      const select = group.querySelector("select.form-input");
      if (!select) return;
      const key = keys[labels.indexOf(label.textContent.trim())];
      const current = config[key] || select.value || "";
      select.innerHTML = "";
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "— None —";
      select.appendChild(placeholder);
      for (const file of files) {
        const option = document.createElement("option");
        option.value = file;
        option.textContent = potionNameFromFile(file);
        select.appendChild(option);
      }
      if (current && files.includes(current)) select.value = current;
    });
  };

  const refreshRecipeSelect = async () => {
    const card = findAutoCraftCard();
    if (!card) return;
    const bridge = api();
    if (!bridge?.list_potion_files) return;

    let files = [];
    try {
      files = await bridge.list_potion_files();
    } catch {
      return;
    }

    const select = card.querySelector("select.form-input");
    if (!select) return;

    const config = bridge.get_config ? await bridge.get_config().catch(() => ({})) : {};
    const current = config.selected_potion_file || select.value || "";

    select.innerHTML = "";
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "— Select a potion —";
    select.appendChild(placeholder);

    for (const file of files) {
      const option = document.createElement("option");
      option.value = file;
      option.textContent = potionNameFromFile(file);
      select.appendChild(option);
    }
    if (current && files.includes(current)) select.value = current;

    document.getElementById(CRAFT_ID)?.remove();
  };

  const hideRecorderControls = () => {
    const card = findAutoCraftCard();
    if (!card) return;
    card.querySelectorAll("button").forEach((button) => {
      if ((button.textContent || "").includes("Potion Recorder")) button.remove();
    });
  };

  const ensureCraftButtons = async () => {
    if (!isPotionCraftingPage() || document.getElementById(CRAFT_ID)) return;
    const card = findAutoCraftCard();
    if (!card) return;

    const bridge = api();
    const config = bridge?.get_config ? await bridge.get_config().catch(() => ({})) : {};
    const names = [config.selected_potion_file, config.potion_file_1, config.potion_file_2, config.potion_file_3]
      .map(potionNameFromFile)
      .filter(Boolean);
    const uniqueNames = [...new Set(names)];
    if (!uniqueNames.length) return;

    const panel = document.createElement("div");
    panel.id = CRAFT_ID;
    panel.style.marginTop = "14px";
    panel.style.borderTop = "1px solid var(--border-color)";
    panel.style.paddingTop = "14px";
    panel.innerHTML = `
      <label class="form-label" style="display:block;margin-bottom:8px;">Craft potion by name</label>
      <div class="coteab-potion-name-buttons" style="display:flex;flex-wrap:wrap;gap:8px;"></div>
      <div class="form-hint coteab-potion-craft-status" style="margin-top:10px;"></div>
    `;
    const list = panel.querySelector(".coteab-potion-name-buttons");
    const status = panel.querySelector(".coteab-potion-craft-status");
    for (const name of uniqueNames) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "btn btn-accent";
      button.textContent = name;
      button.addEventListener("click", async () => {
        if (!bridge?.craft_potion_by_name) return;
        const result = await bridge.craft_potion_by_name(name);
        status.textContent = (result && (result.status || result.error)) || `Craft requested: ${name}`;
      });
      list.appendChild(button);
    }
    card.appendChild(panel);
  };

  const placePotionPanel = (panel, pageHeader) => {
    const parent = pageHeader.parentElement;
    if (!parent) return;
    const firstCard = Array.from(parent.children).find(
      (n) => n.classList?.contains("card") && n.id !== POTION_PANEL_ID
    );
    if (!panel.parentElement) {
      if (firstCard) parent.insertBefore(panel, firstCard);
      else pageHeader.insertAdjacentElement("afterend", panel);
      return;
    }
    if (firstCard && panel.nextElementSibling !== firstCard) {
      parent.insertBefore(panel, firstCard);
    }
  };

  const ensurePotionManager = () => {
    if (!isPotionCraftingPage()) return;
    hideRecorderControls();

    const pageHeader = findPotionPageHeader();
    if (!pageHeader?.parentElement) return;

    let panel = document.getElementById(POTION_PANEL_ID);
    if (!panel) {
      panel = document.createElement("div");
      panel.id = POTION_PANEL_ID;
      panel.className = "card";
      panel.style.marginBottom = "16px";
      panel.style.position = "relative";
      panel.innerHTML = `
        <div class="card-header">
          <div class="card-icon">🧪</div>
          <div><h3>Your potions</h3><p>Add names here — they show up in the craft list below</p></div>
        </div>
        <div style="padding:16px 20px 20px;">
          <div style="display:flex;gap:8px;align-items:center;margin-bottom:12px;">
            <input type="text" class="form-input blossom-potion-name-input" placeholder="Potion name" style="flex:1;min-width:0;" />
            <button type="button" class="btn btn-accent blossom-potion-add-btn">Add potion</button>
          </div>
          <div class="blossom-potion-list" style="display:flex;flex-wrap:wrap;gap:8px;min-height:28px;"></div>
          <div class="form-hint blossom-potion-status" style="margin-top:10px;"></div>
        </div>
      `;

      const nameInput = panel.querySelector(".blossom-potion-name-input");
      const addBtn = panel.querySelector(".blossom-potion-add-btn");
      const list = panel.querySelector(".blossom-potion-list");
      const status = panel.querySelector(".blossom-potion-status");

      const renderList = async () => {
        const bridge = api();
        if (!bridge?.list_potion_files) return;
        let files = [];
        try {
          files = await bridge.list_potion_files();
        } catch {
          return;
        }
        list.innerHTML = "";
        if (!files.length) {
          status.textContent = "No potions yet — add one above.";
          return;
        }
        status.textContent = `${files.length} potion${files.length === 1 ? "" : "s"} saved.`;
        for (const file of files) {
          const name = potionNameFromFile(file);
          const chip = document.createElement("div");
          chip.className = "blossom-potion-chip";
          chip.innerHTML = `<span>${name}</span>`;
          const remove = document.createElement("button");
          remove.type = "button";
          remove.className = "btn btn-secondary";
          remove.style.padding = "2px 8px";
          remove.style.fontSize = "11px";
          remove.textContent = "Remove";
          remove.addEventListener("click", async () => {
            if (!bridge.delete_potion || !confirm(`Remove "${name}"?`)) return;
            const result = await bridge.delete_potion(name);
            status.textContent = result?.message || result?.error || `Removed ${name}`;
            await renderList();
            await refreshRecipeSelect();
          });
          chip.appendChild(remove);
          list.appendChild(chip);
        }
      };

      addBtn.addEventListener("click", async () => {
        const bridge = api();
        const name = (nameInput.value || "").trim();
        if (!name) {
          status.textContent = "Enter a potion name first.";
          return;
        }
        if (!bridge?.add_potion) {
          status.textContent = "Add potion is not available.";
          return;
        }
        const result = await bridge.add_potion(name);
        if (result?.ok) {
          nameInput.value = "";
          status.textContent = result.message || `Saved ${result.name || name}`;
          await renderList();
          await refreshRecipeSelect();
        } else {
          status.textContent = result?.error || "Could not add potion";
        }
      });

      nameInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          addBtn.click();
        }
      });

      panel._blossomRenderList = renderList;
      void renderList();
    }

    placePotionPanel(panel, pageHeader);
  };

  let potionListsReady = false;

  const sync = () => {
    if (!isPotionCraftingPage()) {
      potionListsReady = false;
      document.getElementById(POTION_PANEL_ID)?.remove();
      document.getElementById(CRAFT_ID)?.remove();
      return;
    }
    ensurePotionManager();
    ensureCraftButtons();
    void gatePotionSwitching();
    if (!potionListsReady) {
      potionListsReady = true;
      void refreshSwitchingSelects();
      void refreshRecipeSelect();
    }
  };

  if (observeMain) {
    observeMain(sync, 0, "Potion Crafting");
  } else {
    const run = debounce ? debounce(sync, 200) : sync;
    run();
    window.addEventListener("pywebviewready", run);
  }
})();
