(function () {
  const HUB_ID = "blsm-merchant-hub";
  const GRID_ID = "blsm-merchant-grid";
  const PAGE = "Merchant";

  const { observeMain, pageHeaderTitle } = window.Blossom || {};
  const api = () => window.pywebview?.api;

  const isMerchantPage = () => pageHeaderTitle?.() === PAGE;

  const mainEl = () =>
    document.querySelector(".page-content") || document.querySelector(".main-content");

  const cardByTitle = (title) => {
    const cards = Array.from(mainEl()?.querySelectorAll(".card") || []);
    return (
      cards.find((card) => {
        const h3 = card.querySelector("h3");
        return h3 && h3.textContent.trim() === title;
      }) || null
    );
  };

  const configFlagOn = (value) => {
    if (typeof value === "string") {
      return ["1", "true", "yes", "on"].includes(value.trim().toLowerCase());
    }
    return value !== false && Boolean(value);
  };

  const saveReturnToggle = async (enabled) => {
    const bridge = api();
    if (!bridge?.get_config || !bridge?.save_config) return;
    try {
      const config = await bridge.get_config();
      await bridge.save_config({ ...config, merchant_return_to_limbo: Boolean(enabled) });
    } catch (error) {
      console.warn("[merchant-ui] could not save return toggle:", error);
    }
  };

  const ensureHub = () => {
    const main = mainEl();
    if (!main || document.getElementById(HUB_ID)) return document.getElementById(HUB_ID);

    const header = main.querySelector(".page-header");
    if (header) {
      const sub = header.querySelector("p");
      if (sub) {
        sub.textContent =
          "Teleport to the Limbo merchant with your teleporter item, buy from Mari / Jester / Rin, then Blossom uses Portable Crack from your inventory to return to Limbo.";
      }
    }

    const hub = document.createElement("section");
    hub.id = HUB_ID;
    hub.innerHTML = `
      <div class="blsm-merchant-flow" role="list" aria-label="Merchant automation flow">
        <div class="blsm-merchant-flow-step is-active" data-step="1" role="listitem">
          <strong>Merchant Teleporter</strong>
          <span>Inventory → search “teleport” → use item to reach the Limbo merchant.</span>
        </div>
        <div class="blsm-merchant-flow-step is-active" data-step="2" role="listitem">
          <strong>Talk &amp; auto-buy</strong>
          <span>Interact, OCR the merchant name, open the shop, and purchase your enabled items.</span>
        </div>
        <div class="blsm-merchant-flow-step is-active" data-step="3" role="listitem">
          <strong>Portable Crack</strong>
          <span>Inventory → search “crack” → use Portable Crack to teleport back to Limbo.</span>
        </div>
      </div>
      <div class="blsm-merchant-return-toggle">
        <input type="checkbox" id="blsm-merchant-return-cb" checked />
        <label for="blsm-merchant-return-cb">
          <b>Return to Limbo after merchant teleporter</b>
          <span>Uses Portable Crack from inventory when the teleporter round-trip finishes. Requires the same inventory calibrations as BR/SC.</span>
        </label>
      </div>
    `;

    const toggle = hub.querySelector("#blsm-merchant-return-cb");
    toggle?.addEventListener("change", () => {
      void saveReturnToggle(toggle.checked);
    });

    const anchor = header?.nextElementSibling || main.firstChild;
    if (anchor) {
      main.insertBefore(hub, anchor);
    } else {
      main.appendChild(hub);
    }

    void (async () => {
      const bridge = api();
      if (!bridge?.get_config || !toggle) return;
      try {
        const config = await bridge.get_config();
        toggle.checked = config.merchant_return_to_limbo !== false;
      } catch {
        toggle.checked = true;
      }
    })();

    return hub;
  };

  const layoutCards = () => {
    const main = mainEl();
    if (!main || !isMerchantPage()) return;

    document.documentElement.classList.add("blsm-merchant-hub-active");
    ensureHub();

    if (document.getElementById(GRID_ID)) return;

    const teleporter = cardByTitle("Merchant Teleporter");
    const discord = cardByTitle("Discord Pings");
    const mari = cardByTitle("Mari Item Settings");
    const jester = cardByTitle("Jester Item Settings");
    const rin = cardByTitle("Rin Item Settings");
    if (!teleporter) return;

    const grid = document.createElement("div");
    grid.id = GRID_ID;
    grid.className = "blsm-merchant-grid";

    const left = document.createElement("div");
    left.className = "blsm-merchant-grid-col";
    const right = document.createElement("div");
    right.className = "blsm-merchant-grid-col";

    const items = document.createElement("div");
    items.className = "blsm-merchant-items-row";

    grid.appendChild(left);
    grid.appendChild(right);
    if (mari) items.appendChild(mari);
    if (jester) items.appendChild(jester);
    if (rin) items.appendChild(rin);

    const hub = document.getElementById(HUB_ID);
    const insertAfter = hub?.nextSibling;
    if (insertAfter) {
      main.insertBefore(grid, insertAfter);
    } else {
      main.appendChild(grid);
    }

    left.appendChild(teleporter);
    if (discord) right.appendChild(discord);
    if (items.childElementCount) {
      grid.after(items);
    }
  };

  const teardown = () => {
    if (isMerchantPage()) return;
    document.documentElement.classList.remove("blsm-merchant-hub-active");
    document.getElementById(HUB_ID)?.remove();
    document.getElementById(GRID_ID)?.remove();
    document.querySelector(".blsm-merchant-items-row")?.remove();
  };

  const refresh = () => {
    if (!isMerchantPage()) {
      teardown();
      return;
    }
    layoutCards();
  };

  if (observeMain) {
    observeMain(refresh, 120, [PAGE]);
  } else {
    window.addEventListener("pywebviewready", refresh);
    refresh();
  }
})();
