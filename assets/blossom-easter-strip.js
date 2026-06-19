(function () {
  const HIDDEN_KEYS = new Set([
    "collect_easter",
    "egg_ocr_detect_special",
    "egg_playback_multiplier",
    "enable_auto_egg_pathing",
    "auto_egg_pathing",
  ]);

  const HIDDEN_LABELS = [
    /easter/i,
    /egg\s*ocr/i,
    /auto\s*egg/i,
    /collect\s*easter/i,
  ];

  const { observeMain } = window.Blossom || {};

  const hideRow = (row) => {
    if (!row || row.dataset.blsmEasterHidden === "1") return;
    row.dataset.blsmEasterHidden = "1";
    row.setAttribute("hidden", "");
    row.setAttribute("aria-hidden", "true");
    row.style.display = "none";
  };

  const rowForToggle = (input) => {
    if (!(input instanceof HTMLInputElement)) return null;
    return (
      input.closest(".toggle-row") ||
      input.closest(".form-group") ||
      input.closest("label")?.parentElement
    );
  };

  const stripEasterUi = () => {
    document.querySelectorAll("input, select, textarea").forEach((el) => {
      const key =
        el.getAttribute("name") ||
        el.getAttribute("id") ||
        el.getAttribute("data-key") ||
        "";
      if (HIDDEN_KEYS.has(key)) {
        hideRow(rowForToggle(el) || el.parentElement);
        return;
      }
      const label = el.closest("label")?.textContent || "";
      const row = rowForToggle(el);
      const rowText = row?.textContent || "";
      if (HIDDEN_LABELS.some((re) => re.test(label) || re.test(rowText))) {
        hideRow(row);
      }
    });

    document.querySelectorAll("label, .form-label, h3, h4, strong").forEach((el) => {
      const text = el.textContent || "";
      if (!HIDDEN_LABELS.some((re) => re.test(text))) return;
      const row =
        el.closest(".toggle-row") ||
        el.closest(".form-group") ||
        el.closest(".card")?.querySelector(".form-group");
      hideRow(row || el.parentElement);
    });
  };

  if (observeMain) {
    observeMain(stripEasterUi, 200);
  } else {
    stripEasterUi();
    window.addEventListener("pywebviewready", stripEasterUi);
  }
})();
