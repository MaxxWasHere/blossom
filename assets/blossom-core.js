(function () {
  const FLUSH_MS = 420;

  const debounce = (fn, ms) => {
    let t;
    return (...args) => {
      clearTimeout(t);
      t = setTimeout(() => fn(...args), ms);
    };
  };

  const subscribers = [];
  let observer = null;
  let flushTimer = null;
  let rafCoalesce = 0;

  const pageHeaderTitle = () =>
    document.querySelector(".page-header h2")?.textContent?.trim() || "";

  const MACRO_CAL_PAGE = "Macro Calibrations";
  const WEBHOOK_PAGE = "Webhook";

  // Mark the old React "Biome Configuration" card so CSS can hide it before it
  // paints. Runs in the pre-paint pass instead of the debounced module flush, so
  // the legacy card never flashes before the Biome Notifier hub takes over.
  const markLegacyWebhookCard = (active) => {
    if (!active) return;
    const main = document.querySelector(".page-content, .main-content");
    if (!main) return;
    for (const card of main.querySelectorAll(".card")) {
      if (card.id === "blsm-biome-webhooks-hub") continue;
      const h3 = card.querySelector("h3");
      if (h3 && h3.textContent.trim() === "Biome Configuration") {
        card.classList.add("blsm-legacy-biome-config-card");
      }
    }
  };

  const setPageAttr = () => {
    const title = pageHeaderTitle();
    const main = document.querySelector(".page-content, .main-content");
    if (main && title) main.setAttribute("data-blossom-page", title);
    document.documentElement.classList.toggle("blsm-page-macro-calibrations", title === MACRO_CAL_PAGE);
    const onWebhook = title === WEBHOOK_PAGE;
    document.documentElement.classList.toggle("blsm-biome-webhooks-active", onWebhook);
    markLegacyWebhookCard(onWebhook);
  };

  const pageMatches = (pages, title) => {
    if (!pages || !pages.length) return true;
    return pages.some((p) => p === title);
  };

  const normalizePages = (pages) => {
    if (!pages) return null;
    if (Array.isArray(pages)) return pages.filter(Boolean);
    return [String(pages)];
  };

  const doFlush = () => {
    flushTimer = null;
    setPageAttr();
    const title = pageHeaderTitle();
    for (const sub of subscribers) {
      if (!pageMatches(sub.pages, title)) continue;
      try {
        sub.fn();
      } catch (err) {
        console.warn("[Blossom] subscriber error:", err);
      }
    }
  };

  const scheduleFlush = () => {
    if (rafCoalesce) return;
    rafCoalesce = requestAnimationFrame(() => {
      rafCoalesce = 0;
      setPageAttr();
      if (flushTimer) clearTimeout(flushTimer);
      flushTimer = setTimeout(doFlush, FLUSH_MS);
    });
  };

  const ensureObserver = () => {
    if (observer) return;
    const root =
      document.querySelector(".main-content") ||
      document.querySelector(".page-content") ||
      document.getElementById("root") ||
      document.body;
    observer = new MutationObserver(scheduleFlush);
    observer.observe(root, { childList: true, subtree: true });
    window.addEventListener("pywebviewready", scheduleFlush);
  };

  const goToTab = (label) => {
    const needle = String(label || "").trim().toLowerCase();
    if (!needle) return false;
    const items = document.querySelectorAll(".sidebar-item");
    for (const item of items) {
      const text = (item.textContent || "").trim().toLowerCase();
      if (text === needle || text.includes(needle)) {
        item.click();
        setTimeout(() => {
          setPageAttr();
          scheduleFlush();
        }, 80);
        return true;
      }
    }
    return false;
  };

  /** One shared DOM observer; optional `pages` limits when fn runs (string or array). */
  const observeMain = (fn, _debounceMs, pages) => {
    const entry = { fn, pages: normalizePages(pages) };
    subscribers.push(entry);
    ensureObserver();
    scheduleFlush();
    return () => {
      const i = subscribers.indexOf(entry);
      if (i >= 0) subscribers.splice(i, 1);
    };
  };

  window.Blossom = {
    debounce,
    pageHeaderTitle,
    goToTab,
    observeMain,
    setPageAttr,
    scheduleUiSync: scheduleFlush,
  };
})();
