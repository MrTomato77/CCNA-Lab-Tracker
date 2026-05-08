// ── Shared constants ──────────────────────────────────────────────────────
// Mirror of core/constants.py — sync manually when adding values backend-side.
const STATUS = Object.freeze({
  NOT_STARTED: 'not_started',
  IN_PROGRESS: 'in_progress',
  DONE:        'done',
});
const STATUS_LABELS = Object.freeze({
  not_started: 'Not Started',
  in_progress: 'In Progress',
  done:        'Done',
});
const CATEGORIES = Object.freeze([
  'CLI & Basic',     'Switching & VLAN', 'Wireless',
  'Inter-VLAN & Routing', 'HSRP & ACL',  'NAT & DHCP',
  'Management',      'Security & Advanced',
]);

// 8h cap on resumed timers — see labCard.init() for rationale.
const TIMER_RESUME_CAP_SEC = 8 * 3600;

// ── Fetch wrapper ─────────────────────────────────────────────────────────
// All POST sites used to repeat the same `headers` + `JSON.stringify` body
// shape. Wrap once. GET keeps working — pass no body, returns parsed JSON.
async function api(path, { method = 'GET', body = null } = {}) {
  const opts = { method };
  if (body !== null) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body    = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  return res.json();
}

// ── Time formatting ───────────────────────────────────────────────────────
// One helper, three render modes — replaces the three near-duplicates that
// used to live on appShell, labCard, and statsPage.
//   'clock'   → "HH:MM:SS"   (timer display)
//   'compact' → "4h 32m"     (totals)
//   'rich'    → "4ʰ 32ᵐ"     (stats blocks, with <sup> markup)
function formatTime(s = 0, mode = 'clock') {
  s = Math.max(0, s | 0);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (mode === 'compact') return h > 0 ? `${h}h ${m}m` : `${m}m`;
  if (mode === 'rich')    return h > 0 ? `${h}<sup>h</sup> ${m}<sup>m</sup>` : `${m}<sup>m</sup>`;
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
}

// Alpine store — single source of truth for summary so any component can
// trigger a refresh after a mutation (status change, timer stop) and the
// dashboard progress bar / analytics page pick it up immediately.
document.addEventListener("alpine:init", () => {
  Alpine.store("app", {
    summary: { done:0, in_progress:0, not_started:0, total:51,
               completion_percent:0, total_time_spent:0 },
    async refreshSummary() {
      try {
        const json = await api("/api/stats/summary");
        if (json.success) this.summary = json.data;
      } catch (e) { console.error("Summary refresh failed:", e); }
    }
  });

  Alpine.store("modal", {
    open: false, title: "", message: "", danger: false, resolve: null,
    show(message, title = "", danger = false) {
      return new Promise(resolve => {
        this.title = title; this.message = message;
        this.danger = danger; this.resolve = resolve;
        this.open = true;
      });
    },
    ok()     { if (this.resolve) this.resolve(true);  this.open = false; },
    cancel() { if (this.resolve) this.resolve(false); this.open = false; }
  });
});

// ── App Shell ─────────────────────────────────────────────────────────────
window.appShell = function() {
  return {
    page: "dashboard",
    loading: true,
    labs: [],
    filterCat: "",
    hideStatus: "",
    statusOpen: false,
    theme: document.documentElement.getAttribute("data-theme") || "light",
    categories: CATEGORIES,

    get summary() { return this.$store.app.summary; },

    async init() {
      await this.fetchLabs();
      window.addEventListener("refresh-labs", () => this.fetchLabs());
    },

    toggleTheme() {
      this.theme = this.theme === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", this.theme);
      try { localStorage.setItem("theme", this.theme); } catch (e) { /* ignore */ }
      // Re-render chart with new theme colors if present
      if (this.page === "stats") {
        window.dispatchEvent(new CustomEvent("theme-changed"));
      }
    },

    async fetchLabs() {
      this.loading = true;
      try {
        this.labs = (await api("/api/labs")).data;
        await this.$store.app.refreshSummary();
      } catch (e) {
        console.error("Failed to load labs:", e);
      } finally {
        this.loading = false;
      }
    },

    async resetAllLabs() {
      const ok = await Alpine.store("modal").show(
        "This will reset ALL labs to Not Started and clear all timer data.",
        "Reset All Labs", true
      );
      if (!ok) return;
      try {
        const json = await api("/api/labs/reset", { method: "POST" });
        if (json.success) {
          await this.fetchLabs();
          window.showToast("+ All labs have been reset successfully!", 'success');
        } else {
          window.showToast(`× Error: ${json.error}`, 'error');
        }
      } catch (e) {
        window.showToast("× Network error while resetting labs", 'error');
        console.error("Reset failed:", e);
      }
    },

    // Predicate form (used by x-show on each card so Alpine can transition
    // entering/leaving cards). The old filteredLabs getter is gone — cards
    // stay in DOM and are toggled via x-show/x-transition for fade in/out.
    matchesFilter(lab) {
      if (this.filterCat && lab.category !== this.filterCat) return false;
      if (this.hideStatus === 'done'   && lab.status === STATUS.DONE) return false;
      if (this.hideStatus === 'undone' && lab.status !== STATUS.DONE) return false;
      return true;
    },

    formatTotalTime(s = 0) { return formatTime(s, 'compact'); }
  }
}

// ── Lab Card ──────────────────────────────────────────────────────────────
window.labCard = function(initialLab) {
  return {
    lab: { ...initialLab },
    running: false,
    elapsed: 0,
    sessionStart: null,
    interval: null,

    init() {
      // Resume an open timer session if one exists. open_session_started_at is
      // delivered inline with GET /api/labs via correlated subquery.
      // The cap guards against laptop-sleep / clock-drift / zombie sessions
      // that slipped past startup cleanup — better to drop those than to
      // credit bogus hours.
      if (!this.lab.open_session_started_at) return;
      const started = new Date(this.lab.open_session_started_at);
      const elapsed = Math.floor((Date.now() - started.getTime()) / 1000);
      if (elapsed < 0 || elapsed > TIMER_RESUME_CAP_SEC) return;
      this.sessionStart = started;
      this.elapsed = elapsed;
      this.running = true;
      this.interval = setInterval(() => this.elapsed++, 1000);
    },

    async startTimer() {
      if (this.running) return;
      this.sessionStart = new Date();
      this.elapsed = 0;
      this.running = true;
      // Persist open session immediately (duration=0 = signal for open)
      await api(`/api/labs/${this.lab.id}/timer`, {
        method: "POST",
        body: { started_at: this.sessionStart.toISOString(), duration: 0 },
      });
      this.lab.open_session_started_at = this.sessionStart.toISOString();
      this.interval = setInterval(() => this.elapsed++, 1000);
    },

    async stopTimer() {
      if (!this.running) return;
      clearInterval(this.interval);
      this.running = false;
      const duration = this.elapsed;
      try {
        const json = await api(`/api/labs/${this.lab.id}/timer`, {
          method: "POST",
          body: { started_at: this.sessionStart.toISOString(), duration },
        });
        if (json.success) {
          this.lab.time_spent = json.data.time_spent;
          // Auto-mark done after stop (per user-confirmed launch flow)
          this.lab.status = STATUS.DONE;
          await this.updateStatus(STATUS.DONE);
          window.showToast("+ Time saved & marked done", 'success');
        }
      } catch (e) {
        console.error("Timer save failed:", e);
        window.showToast("× Failed to save time", 'error');
      }
      this.elapsed = 0;
      this.sessionStart = null;
      this.lab.open_session_started_at = null;
    },

    resetTimer() {
      if (this.interval) clearInterval(this.interval);
      this.running = false;
      this.elapsed = 0;
      this.sessionStart = null;
    },

    async resetLab() {
      const ok = await Alpine.store("modal").show(
        `Reset progress and time for ${this.lab.id}?`, "Reset Lab"
      );
      if (!ok) return;
      try {
        const json = await api(`/api/labs/reset-single/${this.lab.id}`, { method: "POST" });
        if (json.success) {
          this.lab.status = STATUS.NOT_STARTED;
          this.lab.time_spent = 0;
          this.resetTimer();
          await Alpine.store("app").refreshSummary();
          window.showToast("+ Lab reset successful", 'success');
        }
      } catch (e) {
        window.showToast("× Failed to reset lab", 'error');
      }
    },

    async updateStatus(newStatus = null) {
      try {
        const status = newStatus || this.lab.status;
        await api(`/api/labs/${this.lab.id}/status`, {
          method: "POST",
          body: { status },
        });
        if (newStatus) {
          this.lab.status = newStatus;
        }
        await Alpine.store("app").refreshSummary();
      } catch (e) {
        console.error("Status update failed:", e);
        window.showToast("× Failed to update status", 'error');
      }
    },

    openDocs() {
      if (!this.lab.docs_path) {
        window.showToast("! No docs for this lab. Run scripts/split_pdf.py first.", 'error');
        return;
      }
      window.open(`/docs/${this.lab.id}.pdf`, '_blank');
    },

    async launch() {
      if (this.running) {
        await this.stopTimer();
        return;
      }
      if (!this.lab.file_path) {
        window.showToast("! Import this lab first. Go to Import page.", 'error');
        return;
      }
      try {
        const json = await api(`/api/labs/${this.lab.id}/open`, { method: "POST" });
        if (json.success) {
          window.showToast("+ Opening in Packet Tracer...", 'success');
          if (!this.running) {
            this.startTimer();
          }
        } else {
          window.showToast(`× ${json.error}`, 'error');
        }
      } catch (e) {
        window.showToast("× Network error", 'error');
      }
    },

    formatTime(s = 0) { return formatTime(s, 'clock'); },

    statusLabel() {
      return STATUS_LABELS[this.lab.status] ?? "";
    },
    badgeClass() { return `badge badge--${this.lab.status}`; },
    cardClass()  {
      const base = `lab-card lab-card--${this.lab.status}`;
      return this.lab.file_path ? base : base + " lab-card--no-file";
    }
  }
}

// ── Import Page ────────────────────────────────────────────────────────────
window.importPage = function() {
  return {
    dragging: false,
    folderPath: "",
    scanning: false,
    results: [],
    importedCount: 0,
    status: { imported_count: 0, total: 51, missing: [], imported: [] },

    async loadStatus() {
      try {
        const json = await api("/api/import/status");
        if (json.success) this.status = json.data;
      } catch (e) { console.error("Status load failed:", e); }
    },

    async handleDrop(e) {
      this.dragging = false;
      const files = Array.from(e.dataTransfer.files).filter(f => f.name.endsWith(".pka"));
      await this.uploadFiles(files);
    },

    async handleFileInput(e) {
      await this.uploadFiles(Array.from(e.target.files));
    },

    async uploadFiles(files) {
      if (!files.length) return;
      const fd = new FormData();
      files.forEach((f, i) => fd.append(`file_${i}`, f));
      try {
        const res  = await fetch("/api/import/upload", { method: "POST", body: fd });
        const json = await res.json();
        if (json.success) {
          this.results       = json.data.results;
          this.importedCount = json.data.imported_count;
          await this.loadStatus();
        }
      } catch (e) { console.error("Upload failed:", e); }
    },

    async scanFolder() {
      if (!this.folderPath.trim()) return;
      this.scanning = true;
      try {
        const json = await api("/api/import/scan", {
          method: "POST",
          body:   { folder_path: this.folderPath.trim() },
        });
        if (json.success) {
          this.results       = json.data.results;
          this.importedCount = json.data.imported_count;
          await this.loadStatus();
        } else {
          window.showToast(`× ${json.error}`, 'error');
        }
      } catch (e) {
        window.showToast("× Network error during scan", 'error');
      } finally {
        this.scanning = false;
      }
    }
  }
}

// ── Stats Page ─────────────────────────────────────────────────────────────
window.statsPage = function() {
  return {
    loading: true,
    byCategory: [],
    chart: null,

    get summary() { return this.$store.app.summary; },

    async load() {
      this.loading = true;
      try {
        const [, cat, slow] = await Promise.all([
          this.$store.app.refreshSummary(),
          api("/api/stats/by-category"),
          api("/api/stats/slowest"),
        ]);
        this.byCategory = cat.data;
        const slowest   = slow.data;
        this._slowest   = slowest;
        this.loading    = false;
        // x-if unmounts the chart container while loading=true, so we must
        // wait for the next DOM tick before grabbing the canvas element.
        await this.$nextTick();
        this.renderChart(slowest);
        // Bind once at module scope — palette tokens come from CSS vars at
        // render time, so a destroy-and-recreate gives us fresh colours.
        bindStatsThemeListener(() => this);
      } catch (e) {
        console.error("Stats load failed:", e);
        this.loading = false;
      }
    },

    renderChart(data) {
      const el = document.getElementById("timeChart");
      if (!el) return;
      if (this.chart) this.chart.destroy();
      // Pull palette from current CSS variables so dark/light themes stay
      // consistent without hard-coding hex codes here.
      const css = getComputedStyle(document.documentElement);
      const accent = css.getPropertyValue("--accent").trim() || "#1d8fc7";
      const accentRgb = css.getPropertyValue("--accent-rgb").trim() || "29, 143, 199";
      const border = css.getPropertyValue("--border").trim() || "#e8eaf2";
      const text3  = css.getPropertyValue("--text-3").trim() || "#7c8294";
      this.chart = new Chart(el.getContext("2d"), {
        type: "bar",
        data: {
          labels: data.map(d => d.id),
          datasets: [{
            label: "minutes",
            data: data.map(d => Math.round(d.time_spent / 60)),
            backgroundColor: `rgba(${accentRgb}, 0.20)`,
            borderColor:     accent,
            borderWidth:     1,
            borderRadius:    4
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: {
              grid:   { display: false, drawBorder: false },
              border: { color: border },
              ticks:  { color: text3, font: { family: "Outfit", size: 11 } }
            },
            y: {
              beginAtZero: true,
              grid:   { color: border, drawBorder: false, lineWidth: 1 },
              border: { display: false },
              ticks:  { stepSize: 10, color: text3, font: { family: "Outfit", size: 11 } }
            }
          }
        }
      });
    },

    formatTime(s = 0)     { return formatTime(s, 'compact'); },
    formatTimeRich(s = 0) { return formatTime(s, 'rich');    }
  }
}

// ── Stats theme-listener (one-time bind) ─────────────────────────────
// statsPage.load() runs every time the user navigates to /stats. Binding
// the `theme-changed` listener inline there leaked one listener per visit
// — five visits = five chart redraws on a single theme toggle. Hoist the
// registration to module scope behind a guard so it fires exactly once,
// then poll back to whatever statsPage instance is currently mounted.
let _statsRef = null;
let _statsThemeBound = false;
function bindStatsThemeListener(getCurrent) {
  _statsRef = getCurrent;
  if (_statsThemeBound) return;
  _statsThemeBound = true;
  window.addEventListener('theme-changed', () => {
    const cur = _statsRef && _statsRef();
    if (cur && cur._slowest) cur.renderChart(cur._slowest);
  });
}

// ── Toast Service ─────────────────────────────────────────────────────
window.showToast = function(message, type = 'info', duration = 1800) {
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast--leaving');
    setTimeout(() => toast.remove(), 220);
  }, duration);
};

// Disable Alpine auto-start and start it manually (deferLoadingAlpine helper)
window.deferLoadingAlpine = function (callback) {
  window.addEventListener('DOMContentLoaded', () => {
    callback();
  });
};
