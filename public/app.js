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

// ── Quiz Page (v2) ─────────────────────────────────────────────────────────
window.quizPage = function() {
  const BATCH_SIZES = [
    { value: 25,        label: "25"  },
    { value: 50,        label: "50"  },
    { value: 75,        label: "75"  },
    { value: 100,       label: "100" },
    { value: "ENDLESS", label: "∞"   },
  ];

  return {
    BATCH_SIZES,
    view: "loading",          // "loading" | "landing" | "practice" | "summary"
    dashboard: null,
    sessionId: null,
    pickedN: null,
    currentQ: null,
    selection: [],
    feedback: null,
    submitting: false,
    finalSummary: null,
    startedAt: 0,             // ms — session timer
    elapsed: 0,               // ms — re-rendered every second
    elapsedFormatted: "00:00",
    _timerId: null,
    _qStartedAt: 0,
    lastQSec: 0,

    async init() {
      await this.loadDashboard();
    },

    async loadDashboard() {
      this.view = "loading";
      try {
        const json = await api("/api/quiz/dashboard");
        if (json.success) {
          this.dashboard = json.data;
        } else {
          window.showToast("× " + (json.error || "Failed to load"), "error");
          this.dashboard = null;
        }
      } catch (e) {
        window.showToast("× Network error", "error");
        this.dashboard = null;
      } finally {
        this.view = "landing";
      }
    },

    masteryPct() {
      const d = this.dashboard;
      if (!d || !d.quizable_total) return 0;
      return Math.round((d.mastered_count / d.quizable_total) * 100);
    },
    candidateCount() {
      const d = this.dashboard;
      if (!d) return 0;
      return d.quizable_total - d.mastered_count;
    },
    canStart(value) {
      if (value === "ENDLESS") return this.candidateCount() > 0;
      return value <= this.candidateCount();
    },
    latestAccuracy() {
      const s = this.dashboard?.latest_session;
      return s ? `${s.accuracy}%` : "—";
    },
    latestBestStreak() {
      const s = this.dashboard?.latest_session;
      return s ? String(s.best_streak) : "—";
    },
    latestDuration() {
      const s = this.dashboard?.latest_session;
      return s ? this.formatDur(s.duration_sec) : "—";
    },
    positionText() {
      if (!this.currentQ) return "";
      const p = this.currentQ.position;
      const total = p.total !== null ? p.total : "∞";
      return `Question ${p.seen + 1} / ${total}`;
    },
    progressPct() {
      if (!this.currentQ) return 0;
      const p = this.currentQ.position;
      if (p.total === null) return 0; // ∞ — no progress bar fill
      return Math.round(((p.seen + 1) / p.total) * 100);
    },
    formatDur(sec) {
      if (sec == null) return "—";
      const m = Math.floor(sec / 60);
      const s = sec % 60;
      return `${String(m).padStart(2,"0")}:${String(s).padStart(2,"0")}`;
    },
    ago(iso) {
      if (!iso) return "—";
      const diff = (Date.now() - Date.parse(iso)) / 1000;
      if (diff < 60)   return `${Math.floor(diff)}s ago`;
      if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
      if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
      return `${Math.floor(diff/86400)}d ago`;
    },

    async startSession(batchSize) {
      this.view = "loading";
      this.feedback = null;
      this.selection = [];
      try {
        const json = await api("/api/quiz/sessions",
          { method: "POST", body: { batch_size: batchSize } });
        if (!json.success) {
          window.showToast("× " + json.error, "error");
          this.view = "landing";
          return;
        }
        this.sessionId = json.data.session_id;
        this.pickedN   = json.data.picked_n;
        this.startedAt = Date.now();
        this._startTimer();
        await this.fetchNext();
      } catch (e) {
        window.showToast("× Network error", "error");
        this.view = "landing";
      }
    },

    _startTimer() {
      this._stopTimer();
      this._tick();
      this._timerId = setInterval(() => this._tick(), 1000);
    },
    _stopTimer() {
      if (this._timerId) {
        clearInterval(this._timerId);
        this._timerId = null;
      }
    },
    _tick() {
      this.elapsed = Date.now() - this.startedAt;
      const sec = Math.floor(this.elapsed / 1000);
      this.elapsedFormatted = this.formatDur(sec);
    },

    async fetchNext() {
      this.view = "loading";
      this.selection = [];
      this.feedback = null;
      try {
        const json = await api(`/api/quiz/sessions/${this.sessionId}/next`);
        if (!json.success) {
          window.showToast("× " + json.error, "error");
          this._stopTimer();
          this.view = "landing";
          return;
        }
        if (json.data && json.data.exhausted) {
          await this.finishSession();
          return;
        }
        this.currentQ = json.data;
        this._qStartedAt = Date.now();
        this.view = "practice";
      } catch (e) {
        // Network drop with the timer still ticking would burn battery and
        // run a phantom session clock until the next nav — stop it here.
        window.showToast("× Network error", "error");
        this._stopTimer();
        this.view = "landing";
      }
    },

    toggleChoice(label) {
      if (this.feedback) return;
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
      if (!this.selection.length || this.feedback || this.submitting) return;
      this.submitting = true;
      this.lastQSec = Math.round((Date.now() - this._qStartedAt) / 1000);
      try {
        const json = await api(`/api/quiz/sessions/${this.sessionId}/answers`, {
          method: "POST",
          body: { question_id: this.currentQ.question_id,
                  selected_labels: this.selection },
        });
        if (!json.success) {
          // ALREADY_ANSWERED means a previous click already landed; advance
          // instead of trapping the user on a dead question.
          if (json.code === "ALREADY_ANSWERED") {
            await this.fetchNext();
            return;
          }
          window.showToast("× " + json.error, "error");
          return;
        }
        this.feedback = json.data;
      } catch (e) {
        window.showToast("× Network error", "error");
      } finally {
        this.submitting = false;
      }
    },

    async iDontKnow() {
      if (this.feedback || this.submitting) return;
      this.submitting = true;
      this.lastQSec = Math.round((Date.now() - this._qStartedAt) / 1000);
      try {
        const json = await api(`/api/quiz/sessions/${this.sessionId}/dont-know`,
          { method: "POST", body: { question_id: this.currentQ.question_id } });
        if (!json.success) {
          if (json.code === "ALREADY_ANSWERED") {
            await this.fetchNext();
            return;
          }
          window.showToast("× " + json.error, "error");
          return;
        }
        this.feedback = json.data;
      } catch (e) {
        window.showToast("× Network error", "error");
      } finally {
        this.submitting = false;
      }
    },

    async finishSession() {
      if (!this.sessionId) {
        this.view = "landing";
        return;
      }
      this._stopTimer();
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

    async practiceAgain() {
      // Prefer the finished session we just summarized, then fall back to
      // the dashboard's latest. batch_size IS NULL in the DB means the
      // session was ENDLESS — preserve that intent instead of silently
      // shrinking the user down to a 25-card batch.
      const prior = this.finalSummary ?? this.dashboard?.latest_session;
      const lastBatch = prior?.batch_size;
      const replay = lastBatch == null ? "ENDLESS" : lastBatch;
      this.sessionId    = null;
      this.finalSummary = null;
      await this.loadDashboard();   // refresh counts before relaunching
      await this.startSession(replay);
    },

    async backToLanding() {
      this.sessionId    = null;
      this.currentQ     = null;
      this.finalSummary = null;
      this.selection    = [];
      this.feedback     = null;
      await this.loadDashboard();
    },

    async resetProgress() {
      const ok = await Alpine.store("modal").show(
        "This will reset ALL quiz progress, sessions, and answer history. Question content is preserved.",
        "Reset all quiz data", true,
      );
      if (!ok) return;
      try {
        const json = await api("/api/quiz/reset", { method: "POST" });
        if (json.success) {
          window.showToast(
            `+ Cleared ${json.data.cleared_progress} progress, ${json.data.cleared_sessions} sessions, ${json.data.cleared_answers} answers`,
            "success",
          );
          await this.loadDashboard();
        } else {
          window.showToast("× " + json.error, "error");
        }
      } catch (e) {
        window.showToast("× Network error", "error");
      }
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

// ── Cisco-text detector ───────────────────────────────────────────────
// Heuristic: text is Cisco CLI / config if it matches any common prompt or
// configuration directive. Used by the practice view to render config-style
// choices in monospace so the columns and punctuation actually read.
const CISCO_RE = /Switch\(config|Router\(config|R\d+\(config|\binterface\s+\w|\bswitchport\s|\bspanning-tree\s|\bip\s+route\s|\bip\s+address\s|^\s*conf\s+t\b|^\s*en\b/im;
function isCiscoText(text) {
  return typeof text === "string" && CISCO_RE.test(text);
}
window.isCiscoText = isCiscoText;

