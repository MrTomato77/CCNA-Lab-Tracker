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

// ── Transitions service ───────────────────────────────────────────────────
// Single source of truth for animation timing and easings, mirrored in
// CSS custom properties (:root in style.css). JS-driven follow-ups
// (toasts, chart re-renders) should read from here so they can't drift
// from the stylesheet.
//
// filterList() smooths list-filter transitions by combining two
// techniques into one orchestrator:
//
//   • LEAVING cards (visible → hidden) are pinned to position:absolute
//     at their old rect, dropping out of flow immediately so siblings
//     don't reserve their slots during the fade-out.
//   • REMAINING cards (visible → visible) get a FLIP animation: snapshot
//     before, measure after, jump back to the old position via
//     transform, then animate the transform to zero. The user sees a
//     smooth slide from old slot to new slot rather than an instant
//     "snap up" when the layout collapses.
//   • ENTERING cards (hidden → visible) are left alone — Alpine's enter
//     transition fades them in at their final slot, which is correct
//     because leaving cards are already out of flow by then.
//
// Usage:
//   const flip = Transitions.filterList('.cards-grid');
//   // Inside a filter handler:
//   flip.snapshot();         // capture positions before mutation
//   this.filterCat = cat;    // trigger Alpine reactivity
//   this.$nextTick(() => flip.play());
//
// Reusable for any flex/grid list with x-show + fade transitions — pass
// the container selector, optionally override duration/easing/leaveClass.
const Transitions = Object.freeze({
  DURATION: Object.freeze({ fast: 120, normal: 200, slow: 320 }),  // ms
  EASING: Object.freeze({
    default: 'cubic-bezier(.2, .8, .2, 1)',
    sharp:   'cubic-bezier(.4, 0, .6, 1)',
  }),

  filterList(containerSelector, opts = {}) {
    const duration   = opts.duration   ?? this.DURATION.normal;
    const easing     = opts.easing     ?? this.EASING.default;
    const leaveClass = opts.leaveClass ?? 'card-fade-leave';

    let oldPositions = new Map();

    const realChildren = (container) =>
      [...container.children].filter((el) => el.tagName !== 'TEMPLATE');

    return {
      snapshot() {
        oldPositions = new Map();
        for (const container of document.querySelectorAll(containerSelector)) {
          if (getComputedStyle(container).position === 'static') {
            container.style.position = 'relative';
          }
          for (const el of realChildren(container)) {
            if (getComputedStyle(el).display === 'none') continue;
            oldPositions.set(el, {
              rect: el.getBoundingClientRect(),
              container,
            });
          }
        }
      },

      play() {
        // Pass 1 — pin leaving cards to absolute at their snapshotted
        // position, taking them out of flow so layout settles to its
        // final form before we measure remaining cards.
        for (const [el, { rect: oldRect, container }] of oldPositions) {
          if (!el.classList.contains(leaveClass)) continue;
          const cRect = container.getBoundingClientRect();
          el.style.position = 'absolute';
          el.style.top    = `${oldRect.top  - cRect.top }px`;
          el.style.left   = `${oldRect.left - cRect.left}px`;
          el.style.width  = `${oldRect.width}px`;
          const onLeaveEnd = (e) => {
            if (e.propertyName !== 'opacity') return;
            el.style.position = '';
            el.style.top      = '';
            el.style.left     = '';
            el.style.width    = '';
            el.removeEventListener('transitionend', onLeaveEnd);
          };
          el.addEventListener('transitionend', onLeaveEnd);
        }

        // Pass 2 — FLIP remaining cards. Layout is now collapsed (leaving
        // cards are absolute), so getBoundingClientRect returns the FINAL
        // positions. We jump back to old positions via transform, then
        // animate the transform to zero on the next frame.
        for (const [el, { rect: oldRect }] of oldPositions) {
          if (el.classList.contains(leaveClass)) continue;
          if (getComputedStyle(el).display === 'none') continue;
          const newRect = el.getBoundingClientRect();
          const dx = oldRect.left - newRect.left;
          const dy = oldRect.top  - newRect.top;
          if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) continue;

          el.style.transition = 'none';
          el.style.transform  = `translate(${dx}px, ${dy}px)`;
          // Force the inverted state to apply before unwinding it.
          void el.offsetWidth;
          requestAnimationFrame(() => {
            el.style.transition = `transform ${duration}ms ${easing}`;
            el.style.transform  = '';
            const onFlipEnd = (e) => {
              if (e.propertyName !== 'transform') return;
              el.style.transition = '';
              el.style.transform  = '';
              el.removeEventListener('transitionend', onFlipEnd);
            };
            el.addEventListener('transitionend', onFlipEnd);
          });
        }
      },
    };
  },
});
window.Transitions = Transitions;

// ── Fetch wrapper ─────────────────────────────────────────────────────────
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
// mode: 'clock' → "HH:MM:SS" | 'compact' → "4h 32m" | 'rich' → "4<sup>h</sup> 32<sup>m</sup>"
function formatTime(s = 0, mode = 'clock') {
  s = Math.max(0, s | 0);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (mode === 'compact') return h > 0 ? `${h}h ${m}m` : `${m}m`;
  if (mode === 'rich')    return h > 0 ? `${h}<sup>h</sup> ${m}<sup>m</sup>` : `${m}<sup>m</sup>`;
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
}

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

  Alpine.store("summaryModal", {
    open: false,
    lab: null,
    data: null,
    loading: false,
    error: null,
    async show(lab) {
      this.lab = { id: lab.id, name: lab.name };
      this.data = null;
      this.error = null;
      this.loading = true;
      this.open = true;
      try {
        const res = await api(`/api/labs/${lab.id}/summary`);
        if (res.success) {
          this.data = res.data;
        } else {
          this.error = res.code === "SUMMARY_MISSING"
            ? "No cheat-sheet for this lab yet."
            : (res.error || "Failed to load");
        }
      } catch (e) {
        this.error = "Network error";
      } finally {
        this.loading = false;
      }
    },
    close() { this.open = false; this.data = null; this.error = null; }
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
    _flip: null,  // created lazily in init() after .cards-grid exists

    get summary() { return this.$store.app.summary; },

    setFilter(updater) {
      if (!this._flip) this._flip = Transitions.filterList('.cards-grid');
      this._flip.snapshot();
      updater();
      this.$nextTick(() => this._flip.play());
    },

    async init() {
      await this.fetchLabs();
      window.addEventListener("refresh-labs", () => this.fetchLabs());
      // Sync appShell.labs[] status without a full refetch — labCard owns
      // a spread copy, so the shell would lag behind until next page load.
      window.addEventListener("lab-status-changed", (e) => {
        const row = this.labs.find(l => l.id === e.detail.id);
        if (row) row.status = e.detail.status;
      });
    },

    // True when every lab in the category is done — turns the chip green.
    // Empty string ("All") always returns false; the All chip checks inline.
    categoryDone(cat) {
      if (!cat) return false;
      const rows = this.labs.filter(l => l.category === cat);
      return rows.length > 0 && rows.every(l => l.status === STATUS.DONE);
    },

    toggleTheme() {
      this.theme = this.theme === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", this.theme);
      try { localStorage.setItem("theme", this.theme); } catch (e) { /* ignore */ }
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
      // Resume open timer if present. Cap guards against laptop-sleep / clock-drift
      // / zombie sessions that slipped past startup cleanup.
      if (!this.lab.open_session_started_at) return;
      const started = new Date(this.lab.open_session_started_at);
      const elapsed = Math.floor((Date.now() - started.getTime()) / 1000);
      if (elapsed < 0 || elapsed > TIMER_RESUME_CAP_SEC) return;
      this.sessionStart = started;
      this.elapsed = elapsed;
      this.running = true;
      this.interval = setInterval(() => this.tickElapsed(), 1000);
    },

    // Skipped while the card is hidden (offsetParent null) — avoids DOM
    // updates for invisible timers; snaps to wall clock on next visible tick.
    tickElapsed() {
      if (this.$el && this.$el.offsetParent === null) return;
      this.elapsed = Math.floor((Date.now() - this.sessionStart.getTime()) / 1000);
    },

    async startTimer() {
      if (this.running) return;
      this.sessionStart = new Date();
      this.elapsed = 0;
      this.running = true;
      await api(`/api/labs/${this.lab.id}/timer`, {
        method: "POST",
        body: { started_at: this.sessionStart.toISOString(), duration: 0 },
      });
      this.lab.open_session_started_at = this.sessionStart.toISOString();
      this.interval = setInterval(() => this.tickElapsed(), 1000);
    },

    async stopTimer() {
      if (!this.running) return;
      clearInterval(this.interval);
      this.running = false;
      // Wall clock (not tick counter) capped at 8h — matches init()'s zombie
      // guard. Math.max guards against NTP corrections running backward.
      const wall = Math.floor((Date.now() - this.sessionStart.getTime()) / 1000);
      const duration = Math.max(0, Math.min(wall, TIMER_RESUME_CAP_SEC));
      try {
        const json = await api(`/api/labs/${this.lab.id}/timer`, {
          method: "POST",
          body: { started_at: this.sessionStart.toISOString(), duration },
        });
        if (json.success) {
          this.lab.time_spent = json.data.time_spent;
          this.lab.status = STATUS.DONE;
          await this.updateStatus(STATUS.DONE);
          // Close PT — non-fatal if it fails; timer is already saved.
          try {
            const closeRes = await api(`/api/labs/${this.lab.id}/close`, { method: "POST" });
            if (!closeRes.success) {
              window.showToast("! Time saved, but couldn't close Packet Tracer", 'info');
            }
          } catch (_) {
            window.showToast("! Time saved, but couldn't reach close endpoint", 'info');
          }
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
          window.dispatchEvent(new CustomEvent("lab-status-changed",
            { detail: { id: this.lab.id, status: STATUS.NOT_STARTED } }));
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
        window.dispatchEvent(new CustomEvent("lab-status-changed",
          { detail: { id: this.lab.id, status } }));
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

    openBrief() {
      Alpine.store("summaryModal").show(this.lab);
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
        await this.$nextTick();  // x-if unmounts canvas while loading=true
        this.renderChart(slowest);
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

// ── Quiz Page ──────────────────────────────────────────────────────────────
window.quizPage = function() {
  return {
    view: "pools",          // "pools" | "loading" | "practice" | "summary"
    pools: [],              // [{id, name, question_count}]
    sessionId: null,
    selectedPool: null,
    currentQ: null,         // {question_id, prompt_en, prompt_th, choices, multi, image_urls}
    selection: [],          // user's current label selection
    feedback: null,         // {is_correct, correct_labels, explanation} after submit
    finalSummary: null,

    async init() {
      await this.loadPools();
    },

    async loadPools() {
      this.view = "loading";
      try {
        const json = await api("/api/quiz/pools");
        if (json.success) this.pools = json.data;
      } finally {
        this.view = "pools";
      }
    },

    async startPool(poolId) {
      if (!poolId) return;
      this.view = "loading";
      this.selectedPool = poolId;
      this.feedback = null;
      this.selection = [];
      try {
        const json = await api("/api/quiz/sessions",
          { method: "POST", body: { pool: poolId } });
        if (!json.success) {
          window.showToast("× " + (json.error || "Failed to start"), "error");
          this.view = "pools";
          return;
        }
        this.sessionId = json.data.session_id;
        await this.fetchNext();
      } catch (e) {
        window.showToast("× Network error", "error");
        this.view = "pools";
      }
    },

    async fetchNext() {
      this.view = "loading";
      this.selection = [];
      this.feedback = null;
      try {
        const json = await api(`/api/quiz/sessions/${this.sessionId}/next`);
        if (!json.success) {
          window.showToast("× " + json.error, "error");
          return;
        }
        if (!json.data) {           // pool exhausted
          await this.finish();
          return;
        }
        this.currentQ = json.data;
        this.view = "practice";
      } catch (e) {
        window.showToast("× Network error", "error");
        this.view = "pools";
      }
    },

    toggleChoice(label) {
      if (this.feedback) return;    // freeze after submit
      if (!this.currentQ.multi) {
        this.selection = [label];
        return;
      }
      const i = this.selection.indexOf(label);
      if (i >= 0) this.selection.splice(i, 1);
      else this.selection.push(label);
    },

    isSelected(label)     { return this.selection.includes(label); },
    isCorrectLabel(label) {
      return !!this.feedback && this.feedback.correct_labels.includes(label);
    },

    async submit() {
      if (!this.selection.length || this.feedback) return;
      try {
        const json = await api(`/api/quiz/sessions/${this.sessionId}/answers`, {
          method: "POST",
          body: {
            question_id:     this.currentQ.question_id,
            selected_labels: this.selection,
          },
        });
        if (!json.success) {
          window.showToast("× " + json.error, "error");
          return;
        }
        this.feedback = json.data;
      } catch (e) {
        window.showToast("× Network error", "error");
      }
    },

    async finish() {
      if (!this.sessionId) {
        this.view = "pools";
        return;
      }
      this.view = "loading";
      try {
        const json = await api(
          `/api/quiz/sessions/${this.sessionId}/finish`, { method: "POST" });
        if (!json.success) {
          window.showToast("× " + json.error, "error");
          this.view = "practice";
          return;
        }
        this.finalSummary = json.data;
        this.view = "summary";
      } catch (e) {
        window.showToast("× Network error", "error");
        this.view = "practice";
      }
    },

    async restart() {
      const pool = this.selectedPool;
      this.sessionId = null;
      this.finalSummary = null;
      await this.startPool(pool);
    },

    backToPools() {
      this.sessionId   = null;
      this.currentQ    = null;
      this.finalSummary = null;
      this.selection   = [];
      this.feedback    = null;
      this.loadPools();
    },
  };
};

// ── Stats theme-listener (one-time bind) ─────────────────────────────
// Hoisted to module scope so repeated /stats navigation doesn't leak one
// listener per visit (five visits = five redraws per theme toggle).
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
