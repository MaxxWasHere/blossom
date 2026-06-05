(function () {
  const wrapMorphShell = (body) => {
    if (!body || body.classList.contains("blsm-morph-shell")) return body;
    body.classList.add("blsm-morph-shell", "blsm-morph-body");
    if (body.querySelector(":scope > .blsm-morph-collapse")) return body;

    const collapse = document.createElement("div");
    collapse.className = "blsm-morph-collapse";
    const panel = document.createElement("div");
    panel.className = "blsm-morph-panel";
    while (body.firstChild) panel.appendChild(body.firstChild);
    collapse.appendChild(panel);
    body.appendChild(collapse);
    return body;
  };

  const isBodyOpen = (body) => {
    if (!body) return false;
    const panel = body.querySelector(":scope > .blsm-morph-collapse > .blsm-morph-panel");
    const h = panel ? panel.getBoundingClientRect().height : body.getBoundingClientRect().height;
    return h > 8;
  };

  const lockMorphDisplay = (body) => {
    if (!body?.classList.contains("blsm-morph-shell")) return;
    body.style.setProperty("display", "grid", "important");
  };

  const triggerMorphSwap = (el) => {
    if (!el) return;
    el.classList.remove("blsm-morph-swap");
    void el.offsetWidth;
    el.classList.add("blsm-morph-swap");
  };

  window.Blossom = window.Blossom || {};
  window.Blossom.wrapMorphShell = wrapMorphShell;
  window.Blossom.lockMorphDisplay = lockMorphDisplay;
  window.Blossom.triggerMorphSwap = triggerMorphSwap;
  window.Blossom.isMorphOpen = isBodyOpen;
})();
