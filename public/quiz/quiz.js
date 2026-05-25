// Quiz page (internal state: page==='quiz'). Quiz v2 component + isCiscoText helper.

// ── Quiz Page ─────────────────────────────────────────────────────────
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
    view: "loading",          // loading | landing | practice | summary
    dashboard: null,
    sessionId: null,
    pickedN: null,
    currentQ: null,
    selection: [],
    feedback: null,
    submitting: false,
    finalSummary: null,
    startedAt: 0,             // ms
    elapsed: 0,               // ms
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
      if (p.total === null) return 0; // ∞ mode
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
        // Stop timer on network error to avoid phantom clock
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
          // ALREADY_ANSWERED: advance instead of trapping user
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
      // Preserve ENDLESS intent (batch_size IS NULL in DB)
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
  };
};

// ── Cisco-text detector ───────────────────────────────────────────────
// Heuristic: matches common Cisco CLI/config patterns for monospace rendering.
const CISCO_RE = /Switch\(config|Router\(config|R\d+\(config|\binterface\s+\w|\bswitchport\s|\bspanning-tree\s|\bip\s+route\s|\bip\s+address\s|^\s*conf\s+t\b|^\s*en\b/im;
function isCiscoText(text) {
  return typeof text === "string" && CISCO_RE.test(text);
}
window.isCiscoText = isCiscoText;
