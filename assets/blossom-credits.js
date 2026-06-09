(function () {
  const PANEL_ID = "blossom-credits-panel";
  const CREDITS_PAGE = "Credits";

  const personCard = ({ img, alt, name, role, body, links }) => `
    <div class="blossom-credits-card">
      <div class="blossom-credits-person">
        ${img ? `<img src="${img}" alt="${alt || name}" onerror="this.onerror=null;this.src='./blossom_avatar.png'" />` : ""}
        <div>
          <strong>${name}</strong>
          <div class="role">${role}</div>
          <p>${body}</p>
          ${links || ""}
        </div>
      </div>
    </div>`;

  const buildPanel = () => {
    const panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.className = "blossom-credits-root";
    panel.innerHTML = `
      <p class="blossom-credits-section-title">Blossom</p>
      <div class="blossom-credits-card">
        <div class="blossom-credits-hero">
          <img src="./blossom.png" alt="Blossom" />
          <div>
            <h3>Blossom</h3>
            <p>
              Fork of the
              <a href="https://github.com/xVapure/Noteab-Macro" target="_blank" rel="noreferrer">Coteab macro</a>
              for Sol's RNG — the macro most players run, itself built on the original Noteab biome macro.
              Same idea — automate merchants, potions, biomes — with Blossom's own UI and backend.
              Apache 2.0; keep upstream credit if you redistribute.
            </p>
            <p style="margin:8px 0 0;font-size:13px">
              <a href="https://github.com/MaxxWasHere/blossom-macro" target="_blank" rel="noreferrer">github.com/MaxxWasHere/blossom-macro</a>
            </p>
          </div>
        </div>
      </div>

      ${personCard({
        img: "./tea.png",
        alt: "MaxxWasHere",
        name: "MaxxWasHere",
        role: "Blossom author & maintainer",
        body:
          "Maintains Blossom — UI, Python backend, releases, and whatever breaks next patch.",
        links: `<p style="margin:8px 0 0;font-size:13px">
            <a href="https://github.com/MaxxWasHere/blossom-macro" target="_blank" rel="noreferrer">github.com/MaxxWasHere/blossom-macro</a>
          </p>`,
      })}

      <p class="blossom-credits-section-title">What Blossom adds</p>
      <div class="blossom-credits-card">
        <ul class="blossom-credits-list">
          <li>Sakura branding and sidebar layout</li>
          <li>Potion crafting, rotation, Start / Stop hotkeys</li>
          <li>Config under <code>%LOCALAPPDATA%\\Blossom\\</code> (settings, paths, potion files)</li>
          <li>Discord webhooks from the Python backend</li>
          <li>Macro Calibrations hub and fishing mode</li>
        </ul>
      </div>

      <p class="blossom-credits-section-title">Noteab / Coteab Macro (upstream)</p>
      <div class="blossom-credits-stack">
        ${personCard({
          name: "Vapure (xVapure)",
          role: "Coteab Macro maintainer",
          body:
            "Maintains the macro most players use today — merchant OCR & auto-buy, log-based biome & aura detection, Discord webhooks, auto-pop potions, calibrations, and releases on the upstream repo.",
          links: `<p style="margin:8px 0 0;font-size:13px">
            <a href="https://github.com/xVapure/Noteab-Macro" target="_blank" rel="noreferrer">github.com/xVapure/Noteab-Macro</a>
          </p>`,
        })}
        ${personCard({
          img: "./maxstellar.png",
          alt: "maxstellar",
          name: "maxstellar",
          role: "Upstream contributor — assets",
          body:
            "Biome thumbnail art and related imagery for the original Noteab / Coteab UI (hosted at maxstellar.github.io/biome_thumb and bundled as maxstellar.png in the upstream repo). Not the Blossom fork maintainer.",
          links: `<p style="margin:8px 0 0;font-size:13px">
            <a href="https://maxstellar.github.io/biome_thumb/" target="_blank" rel="noreferrer">maxstellar.github.io/biome_thumb</a>
          </p>`,
        })}
        <div class="blossom-credits-card">
          <div class="blossom-credits-person">
            <div>
              <strong>NotWindyZ</strong>
              <div class="role">Original Noteab's Biome Macro</div>
              <p>
                Earliest public biome-macro foundation this lineage grew from. Blossom and Coteab inherit ideas and
                structure from that Apache 2.0 codebase.
              </p>
              <p style="margin:8px 0 0;font-size:13px">
                <a href="https://github.com/NotWindyZ/Noteab-Macro" target="_blank" rel="noreferrer">github.com/NotWindyZ/Noteab-Macro</a>
              </p>
            </div>
          </div>
        </div>
      </div>

      <p class="blossom-credits-section-title">License & thanks</p>
      <div class="blossom-credits-card">
        <p class="blossom-credits-muted" style="margin-bottom:10px">
          Blossom builds on Noteab / Coteab under the
          <a href="https://www.apache.org/licenses/LICENSE-2.0" target="_blank" rel="noreferrer">Apache License 2.0</a>.
          See LICENSE.txt in the repo.
        </p>
        <p class="blossom-credits-muted">
          Thanks to testers, donors, and bug reporters — and to Vapure, maxstellar, and the Noteab crowd for the macro
          this fork started from.
        </p>
      </div>`;
    return panel;
  };

  const pageRoot = () =>
    document.querySelector(".page-content[data-blossom-page], .main-content[data-blossom-page]") ||
    document.querySelector(".page-content, .main-content");

  const removePanel = () => {
    document.getElementById(PANEL_ID)?.remove();
    pageRoot()?.removeAttribute("data-blossom-credits-active");
  };

  const enhanceHeader = () => {
    const header = pageRoot()?.querySelector(".page-header");
    const subtitle = header?.querySelector("p");
    if (subtitle) {
      subtitle.textContent =
        "Blossom by MaxxWasHere — fork of Noteab / Coteab (Vapure, maxstellar, upstream)";
    }
  };

  const syncCredits = () => {
    const title =
      window.Blossom?.pageHeaderTitle?.() ||
      document.querySelector(".page-header h2")?.textContent?.trim() ||
      "";

    if (title !== CREDITS_PAGE) {
      removePanel();
      return;
    }

    const root = pageRoot();
    const header = root?.querySelector(".page-header");
    if (!root || !header) return;

    root.setAttribute("data-blossom-credits-active", "1");
    enhanceHeader();

    if (!document.getElementById(PANEL_ID)) {
      header.insertAdjacentElement("afterend", buildPanel());
    }
  };

  const boot = () => {
    const run = () => syncCredits();
    if (window.Blossom?.observeMain) {
      window.Blossom.observeMain(run, 0, CREDITS_PAGE);
    } else {
      run();
      window.addEventListener("pywebviewready", run);
    }
  };

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
