(function () {
  "use strict";

  if (window.__blsmPills) return;
  window.__blsmPills = true;

  var POS_KEY = "blsm_dock_top";
  var api = function () {
    return (window.pywebview && window.pywebview.api) || null;
  };
  var call = function (name, args) {
    var a = api();
    if (!a || typeof a[name] !== "function") return Promise.reject(new Error("no " + name));
    try {
      return Promise.resolve(a[name].apply(a, args || []));
    } catch (e) {
      return Promise.reject(e);
    }
  };

  var ICONS = {
    stats:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><rect x="7" y="11" width="3" height="6"/><rect x="12" y="7" width="3" height="10"/><rect x="17" y="13" width="3" height="4"/></svg>',
    settings:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="4" y1="8" x2="20" y2="8"/><circle cx="9" cy="8" r="2.4" fill="currentColor" stroke="none"/><line x1="4" y1="16" x2="20" y2="16"/><circle cx="15" cy="16" r="2.4" fill="currentColor" stroke="none"/></svg>',
    grip:
      '<svg viewBox="0 0 18 10" fill="currentColor"><circle cx="3" cy="3" r="1.3"/><circle cx="9" cy="3" r="1.3"/><circle cx="15" cy="3" r="1.3"/><circle cx="3" cy="7" r="1.3"/><circle cx="9" cy="7" r="1.3"/><circle cx="15" cy="7" r="1.3"/></svg>',
    close:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></svg>',
  };

  var PILLS = [
    { id: "stats", label: "Stats", icon: ICONS.stats, dot: true },
    { id: "settings", label: "Quick", icon: ICONS.settings, dot: false },
  ];

  var dock, panel, panelTitle, panelBody;
  var current = null;
  var pollTimer = null;

  function fmtUptime(sec) {
    sec = Math.max(0, Math.floor(sec || 0));
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = sec % 60;
    var pad = function (n) {
      return (n < 10 ? "0" : "") + n;
    };
    return (h > 0 ? h + ":" : "") + pad(m) + ":" + pad(s);
  }

  function setDot(on) {
    var d = dock.querySelector('.blsm-pill[data-pill="stats"] .dot');
    if (d) d.classList.toggle("on", !!on);
  }

  function renderStats(data) {
    data = data || {};
    var running = !!data.running;
    setDot(running);
    return (
      '<div class="blsm-stat"><span class="k">Status</span>' +
      '<span class="v"><span class="blsm-statusdot ' +
      (running ? "on" : "") +
      '"></span>' +
      (running ? "Running" : "Idle") +
      "</span></div>" +
      '<div class="blsm-stat"><span class="k">Uptime</span><span class="v mono">' +
      fmtUptime(data.uptime_seconds) +
      "</span></div>" +
      '<div class="blsm-stat"><span class="k">Active modules</span><span class="v mono">' +
      (data.active_modules || 0) +
      " / " +
      (data.enabled_modules || 0) +
      "</span></div>" +
      '<div class="blsm-stat"><span class="k">Always on top</span><span class="v">' +
      (data.always_on_top ? "On" : "Off") +
      "</span></div>" +
      '<div class="blsm-stat"><span class="k">Version</span><span class="v mono">' +
      (data.version || "—") +
      "</span></div>" +
      '<button class="blsm-pbtn ' +
      (running ? "danger" : "primary") +
      '" data-act="toggle-macro">' +
      (running ? "Stop macro" : "Start macro") +
      "</button>"
    );
  }

  function refreshStats() {
    call("get_session_stats")
      .then(function (data) {
        if (current !== "stats") return;
        panelBody.innerHTML = renderStats(data);
      })
      .catch(function () {});
  }

  function renderSettings(aot) {
    return (
      '<div class="blsm-toggle"><span class="k">Always on top</span>' +
      '<button class="blsm-switch ' +
      (aot ? "on" : "") +
      '" data-act="aot"></button></div>' +
      '<button class="blsm-pbtn" data-act="minimize">Minimize window</button>' +
      '<button class="blsm-pbtn" data-act="goto-settings">Open Settings tab</button>'
    );
  }

  function loadSettings() {
    call("get_window_always_on_top")
      .then(function (r) {
        if (current !== "settings") return;
        panelBody.innerHTML = renderSettings(r && r.enabled);
      })
      .catch(function () {
        if (current === "settings") panelBody.innerHTML = renderSettings(false);
      });
  }

  function alignPanel() {
    var r = dock.getBoundingClientRect();
    var top = r.top;
    var ph = panel.offsetHeight || 220;
    top = Math.max(8, Math.min(top, window.innerHeight - ph - 8));
    panel.style.top = top + "px";
  }

  function openPanel(id) {
    var pill = dock.querySelector('.blsm-pill[data-pill="' + id + '"]');
    Array.prototype.forEach.call(dock.querySelectorAll(".blsm-pill"), function (p) {
      p.classList.toggle("is-active", p === pill);
    });
    var titles = { stats: "Live Stats", settings: "Quick Settings" };
    panelTitle.textContent = titles[id] || id;
    current = id;

    panelBody.classList.remove("swap");
    void panelBody.offsetWidth;
    panelBody.classList.add("swap");

    if (id === "stats") {
      panelBody.innerHTML = renderStats({});
      refreshStats();
    } else if (id === "settings") {
      panelBody.innerHTML = "";
      loadSettings();
    }

    panel.classList.add("is-open");
    requestAnimationFrame(alignPanel);

    if (pollTimer) clearInterval(pollTimer);
    if (id === "stats") pollTimer = setInterval(refreshStats, 1000);
  }

  function closePanel() {
    panel.classList.remove("is-open");
    current = null;
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
    Array.prototype.forEach.call(dock.querySelectorAll(".blsm-pill"), function (p) {
      p.classList.remove("is-active");
    });
  }

  function togglePill(id) {
    if (current === id) closePanel();
    else openPanel(id);
  }

  function onPanelClick(e) {
    var el = e.target.closest("[data-act]");
    if (!el) return;
    var act = el.getAttribute("data-act");
    if (act === "toggle-macro") {
      call("get_session_stats")
        .then(function (d) {
          return call("set_biome_detection", [!(d && d.running)]);
        })
        .then(function () {
          setTimeout(refreshStats, 200);
        })
        .catch(function () {});
    } else if (act === "aot") {
      var on = !el.classList.contains("on");
      el.classList.toggle("on", on);
      call("set_window_always_on_top", [on]).catch(function () {
        el.classList.toggle("on", !on);
      });
    } else if (act === "minimize") {
      call("minimize").catch(function () {
        call("minimize_window").catch(function () {});
      });
    } else if (act === "goto-settings") {
      gotoTab(["customization", "settings", "Settings & extras"]);
      closePanel();
    }
  }

  function gotoTab(keys) {
    var items = document.querySelectorAll(
      ".sidebar-item, .nav-item, [class*='sidebar'] button, nav button"
    );
    for (var i = 0; i < items.length; i++) {
      var t = (items[i].textContent || "").trim().toLowerCase();
      for (var k = 0; k < keys.length; k++) {
        if (t.indexOf(String(keys[k]).toLowerCase()) !== -1) {
          items[i].click();
          return;
        }
      }
    }
  }

  function applyTop(top) {
    var h = dock.offsetHeight;
    top = Math.max(8, Math.min(top, window.innerHeight - h - 8));
    dock.style.top = top + "px";
    dock.style.transform = "none";
    if (current) requestAnimationFrame(alignPanel);
  }

  function initDrag(grip) {
    var dragging = false,
      startY = 0,
      startTop = 0;
    var down = function (e) {
      dragging = true;
      dock.classList.add("is-dragging");
      var r = dock.getBoundingClientRect();
      startTop = r.top;
      startY = e.clientY;
      e.preventDefault();
      window.addEventListener("pointermove", move);
      window.addEventListener("pointerup", up);
    };
    var move = function (e) {
      if (!dragging) return;
      applyTop(startTop + (e.clientY - startY));
    };
    var up = function () {
      dragging = false;
      dock.classList.remove("is-dragging");
      try {
        localStorage.setItem(POS_KEY, String(parseInt(dock.style.top, 10) || 0));
      } catch (e) {}
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
    grip.addEventListener("pointerdown", down);
  }

  function build() {
    if (document.getElementById("blsm-dock")) return;

    dock = document.createElement("div");
    dock.id = "blsm-dock";
    dock.classList.add("blsm-dock-mount");

    var grip = document.createElement("div");
    grip.className = "blsm-grip";
    grip.innerHTML = ICONS.grip;
    grip.title = "Drag to move";
    dock.appendChild(grip);

    PILLS.forEach(function (p) {
      var btn = document.createElement("button");
      btn.className = "blsm-pill";
      btn.type = "button";
      btn.setAttribute("data-pill", p.id);
      btn.innerHTML =
        '<span class="ic">' +
        p.icon +
        (p.dot ? '<span class="dot"></span>' : "") +
        "</span>" +
        '<span class="lbl">' +
        p.label +
        "</span>";
      btn.addEventListener("click", function () {
        togglePill(p.id);
      });
      dock.appendChild(btn);
    });

    panel = document.createElement("div");
    panel.id = "blsm-panel";
    panel.innerHTML =
      '<div class="blsm-p-head"><span class="blsm-p-title">Stats</span>' +
      '<button type="button" class="blsm-p-close" title="Close">' +
      ICONS.close +
      "</button></div>" +
      '<div class="blsm-p-body"></div>';

    document.body.appendChild(dock);
    document.body.appendChild(panel);

    panelTitle = panel.querySelector(".blsm-p-title");
    panelBody = panel.querySelector(".blsm-p-body");
    panel.querySelector(".blsm-p-close").addEventListener("click", closePanel);
    panelBody.addEventListener("click", onPanelClick);

    try {
      var saved = parseInt(localStorage.getItem(POS_KEY) || "", 10);
      if (!isNaN(saved)) applyTop(saved);
    } catch (e) {}

    initDrag(grip);
    window.addEventListener("resize", function () {
      if (current) alignPanel();
    });

    setInterval(function () {
      if (current === "stats") return;
      call("get_session_stats")
        .then(function (d) {
          setDot(d && d.running);
        })
        .catch(function () {});
    }, 4000);
  }

  function boot() {
    if (!document.body) return;
    build();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot, { once: true });
  } else {
    boot();
  }
})();
