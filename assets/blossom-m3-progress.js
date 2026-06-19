/**
 * Material 3 Expressive linear progress — thick capsule track, accent fill, spring width.
 * Determinate: eased fill grows left→right. Indeterminate: sliding accent segment (CSS).
 */
(function () {
  "use strict";

  const instances = new WeakMap();

  const GEOM = {
    progressLerp: 0.14,
    progressSnap: 0.05,
  };

  function resolveColors(hostEl) {
    const root =
      hostEl.closest(
        ".blossom-loading-overlay, .bootstrap-splash-root, .window-frame, .blossom-update-overlay, .blsm-rt-card"
      ) || document.documentElement;
    const cs = getComputedStyle(root);
    return {
      accent: (cs.getPropertyValue("--accent") || "#e891a8").trim(),
      track: (cs.getPropertyValue("--text-muted") || "#6e6468").trim(),
    };
  }

  function reducedMotion() {
    return (
      window.matchMedia("(prefers-reduced-motion: reduce)").matches ||
      document.documentElement.classList.contains("blsm-reduce-motion")
    );
  }

  function smoothProgress(inst) {
    const delta = inst.targetPercent - inst.displayPercent;
    if (Math.abs(delta) > GEOM.progressSnap) {
      inst.displayPercent += delta * GEOM.progressLerp;
    } else {
      inst.displayPercent = inst.targetPercent;
    }
  }

  function resetProgress(inst) {
    inst.targetPercent = 0;
    inst.displayPercent = 0;
    if (inst.fill) inst.fill.style.width = "0%";
    if (inst.root) inst.root.removeAttribute("aria-valuenow");
  }

  function applyMode(inst) {
    const indet = inst.indeterminate;
    inst.host.dataset.indeterminate = indet ? "true" : "false";
    inst.host.classList.toggle("blsm-reduce-motion", inst.reduced);
    if (inst.root) {
      inst.root.dataset.state = indet ? "indeterminate" : "determinate";
      if (indet) inst.root.removeAttribute("aria-valuenow");
    }
    if (inst.fill) inst.fill.hidden = indet;
    if (inst.indet) inst.indet.hidden = !indet;
  }

  function tick(inst) {
    if (!instances.has(inst.host)) return;
    if (!inst.indeterminate) {
      smoothProgress(inst);
      const pct = Math.max(0, Math.min(100, inst.displayPercent));
      if (inst.fill) inst.fill.style.width = pct + "%";
      if (inst.root) inst.root.setAttribute("aria-valuenow", String(Math.round(pct)));
    }
    inst.rafId = requestAnimationFrame(() => tick(inst));
  }

  function mount(hostEl) {
    if (!hostEl || instances.has(hostEl)) return;

    hostEl.innerHTML = "";
    hostEl.classList.add("blossom-m3-progress-host");

    const root = document.createElement("div");
    root.className = "blossom-m3-progress";
    root.setAttribute("role", "progressbar");
    root.setAttribute("aria-valuemin", "0");
    root.setAttribute("aria-valuemax", "100");

    const rail = document.createElement("div");
    rail.className = "blossom-m3-progress-rail";

    const fill = document.createElement("div");
    fill.className = "blossom-m3-progress-fill";
    const shimmer = document.createElement("span");
    shimmer.className = "blossom-m3-progress-shimmer";
    shimmer.setAttribute("aria-hidden", "true");
    fill.appendChild(shimmer);

    const indet = document.createElement("div");
    indet.className = "blossom-m3-progress-indet";
    indet.setAttribute("aria-hidden", "true");
    const indetSeg = document.createElement("span");
    indetSeg.className = "blossom-m3-progress-indet-seg";
    indet.appendChild(indetSeg);

    rail.appendChild(fill);
    rail.appendChild(indet);
    root.appendChild(rail);
    hostEl.appendChild(root);

    const colors = resolveColors(hostEl);
    hostEl.style.setProperty("--blsm-m3-progress-accent", colors.accent);
    hostEl.style.setProperty("--blsm-m3-progress-track", colors.track);

    const inst = {
      host: hostEl,
      root,
      fill,
      indet,
      targetPercent: 0,
      displayPercent: 0,
      indeterminate: true,
      reduced: reducedMotion(),
      rafId: 0,
    };
    instances.set(hostEl, inst);
    applyMode(inst);
    inst.rafId = requestAnimationFrame(() => tick(inst));
  }

  function unmount(hostEl) {
    const inst = instances.get(hostEl);
    if (!inst) return;
    cancelAnimationFrame(inst.rafId);
    hostEl.innerHTML = "";
    hostEl.classList.remove("blossom-m3-progress-host", "blsm-reduce-motion");
    hostEl.removeAttribute("data-indeterminate");
    instances.delete(hostEl);
  }

  function update(hostEl, options) {
    if (!hostEl) return;
    const opts = options || {};
    const wasMounted = instances.has(hostEl);
    if (!wasMounted) mount(hostEl);
    const inst = instances.get(hostEl);
    if (!inst) return;

    if (opts.reset) resetProgress(inst);

    inst.reduced = reducedMotion();

    if (opts.indeterminate !== undefined) {
      const next = !!opts.indeterminate;
      if (next && !inst.indeterminate) resetProgress(inst);
      inst.indeterminate = next;
    }

    if (opts.percent !== undefined) {
      inst.targetPercent = Math.max(0, Math.min(100, Number(opts.percent) || 0));
      if (!inst.indeterminate && inst.reduced) {
        inst.displayPercent = inst.targetPercent;
        if (inst.fill) inst.fill.style.width = inst.displayPercent + "%";
      }
    }

    applyMode(inst);
  }

  function isDeterminate(percent, total) {
    const pct = Number(percent);
    if (!Number.isFinite(pct) || pct < 0) return false;
    const totalN = Number(total) || 0;
    return totalN > 0 || pct >= 100;
  }

  window.BlossomM3Progress = { mount, unmount, update, isDeterminate };
})();
