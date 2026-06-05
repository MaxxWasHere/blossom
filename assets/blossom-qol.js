(function () {

  const B = window.Blossom || {};

  const TOP_ID = "blsm-top";



  const mainEl = () =>

    document.querySelector(".page-content") ||

    document.querySelector(".main-content") ||

    document.querySelector(".page-content, .main-content");



  /* ——— Back-to-top pill (rebinds if the scroll container is replaced) ——— */

  let boundScroller = null;

  let rafPending = false;



  const ensureTopBtn = () => {

    let btn = document.getElementById(TOP_ID);

    if (!btn) {

      btn = document.createElement("button");

      btn.id = TOP_ID;

      btn.type = "button";

      btn.setAttribute("aria-label", "Scroll to top");

      btn.innerHTML =

        '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M18 15l-6-6-6 6"/></svg>';

      btn.addEventListener("click", () => {

        const sc = boundScroller;

        if (sc) sc.scrollTo({ top: 0, behavior: "smooth" });

      });

      const frame = document.querySelector(".window-frame") || document.body;

      frame.appendChild(btn);

    }

    return btn;

  };



  const reflectScroll = () => {

    rafPending = false;

    const btn = document.getElementById(TOP_ID);

    if (!btn || !boundScroller) return;

    btn.classList.toggle("is-visible", boundScroller.scrollTop > 320);

  };



  const onScroll = () => {

    if (rafPending) return;

    rafPending = true;

    requestAnimationFrame(reflectScroll);

  };



  const bindScroller = () => {

    const sc = mainEl();

    if (!sc || sc === boundScroller) return;

    if (boundScroller) boundScroller.removeEventListener("scroll", onScroll);

    boundScroller = sc;

    boundScroller.addEventListener("scroll", onScroll, { passive: true });

    ensureTopBtn();

    reflectScroll();

  };



  const tick = () => {

    bindScroller();

  };



  const boot = () => {

    if (B.observeMain) {

      B.observeMain(tick, 180);

    } else {

      const root = document.querySelector(".main-content") || document.body;

      const obs = new MutationObserver(() => tick());

      obs.observe(root, { childList: true, subtree: true });

      window.addEventListener("pywebviewready", tick);

    }

    tick();

  };



  if (document.readyState === "loading") {

    document.addEventListener("DOMContentLoaded", boot);

  } else {

    boot();

  }

})();


