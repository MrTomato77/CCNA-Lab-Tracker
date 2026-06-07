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
    view: "loading",          // loading | landing | practice | summary | review
    dashboard: null,
    sessionId: null,
    pickedN: null,
    currentQ: null,
    selection: [],
    feedback: null,
    submitting: false,
    loadingNext: false,      // in-session fetch; keeps the question on screen
    ddPicked: null,          // drag-drop: item selected for click-to-assign
    ddRemaining: 0,          // drag-drop: items still in the bank (gates submit)
    _ddSortables: [],
    finalSummary: null,
    reviewSummary: null,
    reviewSessionId: null,   // id currently shown in review (for URL sync)
    summaryView: 'wrong',
    startedAt: 0,             // ms
    elapsed: 0,               // ms
    elapsedFormatted: "00:00",
    _timerId: null,
    _qStartedAt: 0,
    lastQSec: 0,

    async init() {
      await this.loadDashboard();
      // Deep-link sync: open a session if the URL is /quiz/<id>; keep view and
      // URL in step on back/forward and when the Quiz tab is (re)entered.
      this.syncRoute();
      window.addEventListener("popstate", () => this.syncRoute());
      window.addEventListener("section-entered", (e) => {
        if (e.detail && e.detail.page === "quiz") this.syncRoute();
      });
    },

    // Match the URL's quiz sub-segment to the view (no push; URL is the source).
    syncRoute() {
      const m = location.pathname.match(/^\/quiz\/session\/([^/]+)$/);
      if (m) {
        if (this.reviewSessionId !== m[1]) this.viewSession(m[1], true);
      } else {
        // Bare /quiz: drop back to landing from a review/summary, but never
        // interrupt an active practice run.
        this.reviewSessionId = null;
        if (this.view !== "landing" && this.view !== "practice") this._goLanding();
      }
    },

    _setQuizPath(sub) {
      const path = sub ? `/quiz/session/${sub}` : "/quiz";
      if (location.pathname !== path) history.pushState({}, "", path);
    },

    // Keyboard accelerators. Bound via @keydown.window on the quiz root; we
    // bail unless the quiz page is actually on screen so shortcuts don't fire
    // from other tabs. Ignores keystrokes aimed at inputs and open modals.
    onKey(e) {
      if (this.$el.offsetParent === null) return;              // quiz page hidden
      if (e.target.matches("input, textarea, select")) return;
      if (this.$store.modal.open || this.$store.imageModal.open) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (this.view === "practice" && this.currentQ) {
        const isDrag = this.currentQ.question_type === "drag_drop";
        // Number-key choice picking is mcq-only (drag-drop has no labels).
        if (!isDrag && /^[1-9]$/.test(e.key)) {
          const choices = this.currentQ.choices || [];
          const idx = parseInt(e.key, 10) - 1;
          if (idx < choices.length && !this.feedback) {
            this.toggleChoice(choices[idx].label);
            e.preventDefault();
          }
          return;
        }
        if (e.key === "Enter") {
          if (this.feedback) {
            if (!this.loadingNext) this.fetchNext();
          } else if (this.submitting) {
            /* in flight */
          } else if (isDrag) {
            if (this.ddRemaining === 0) this.submit();
          } else if (this.selection.length) {
            this.submit();
          }
          e.preventDefault();
        }
      } else if (this.view === "landing") {
        const idx = { "1": 0, "2": 1, "3": 2, "4": 3, "5": 4 }[e.key];
        if (idx === undefined) return;
        const size = this.BATCH_SIZES[idx];
        if (size && this.canStart(size.value)) {
          this.startSession(size.value);
          e.preventDefault();
        }
      }
    },

    async loadDashboard() {
      this.view = "loading";
      try {
        const json = await api("/api/quiz/dashboard");
        if (json.success) {
          this.dashboard = json.data;
        } else {
          window.showToast(window.friendlyError(json, "Failed to load quiz dashboard."), "error");
          this.dashboard = null;
        }
      } catch (e) {
        window.showToast(window.netErrMsg, "error");
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
    // Absolute timestamp for the session log: "07/06/2026 16:42"
    // (dd/mm/yyyy HH:MM). Relative time goes in the row's tooltip via ago().
    when(iso) {
      if (!iso) return "—";
      const d = new Date(iso);
      const p = (n) => String(n).padStart(2, "0");
      return `${p(d.getDate())}/${p(d.getMonth() + 1)}/${d.getFullYear()} ${p(d.getHours())}:${p(d.getMinutes())}`;
    },

    async startSession(batchSize) {
      this.view = "loading";
      this.feedback = null;
      this.selection = [];
      try {
        const json = await api("/api/quiz/sessions",
          { method: "POST", body: { batch_size: batchSize } });
        if (!json.success) {
          window.showToast(window.friendlyError(json), "error");
          this.view = "landing";
          return;
        }
        this.sessionId = json.data.session_id;
        this.pickedN   = json.data.picked_n;
        this.startedAt = Date.now();
        this._startTimer();
        await this.fetchNext();
      } catch (e) {
        window.showToast(window.netErrMsg, "error");
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
      // First question of a session shows the full loading view; subsequent
      // fetches keep the current question on screen and flag loadingNext so
      // the Next button shows progress instead of the whole view flashing.
      const inSession = this.view === "practice";
      if (inSession) this.loadingNext = true;
      else this.view = "loading";
      this.selection = [];
      this.feedback = null;
      this.ddPicked = null;
      this.ddRemaining = 0;
      try {
        const json = await api(`/api/quiz/sessions/${this.sessionId}/next`);
        if (!json.success) {
          window.showToast(window.friendlyError(json), "error");
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
        window.showToast(window.netErrMsg, "error");
        this._stopTimer();
        this.view = "landing";
      } finally {
        this.loadingNext = false;
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
      return !!this.feedback && (this.feedback.correct_labels || []).includes(label);
    },

    // ── Drag-and-drop ────────────────────────────────────────────────────
    // SortableJS owns the item DOM (items are built here, not via Alpine x-for,
    // which would churn against Sortable's moves). Handlers use the stored root
    // element — never Alpine magics — so they also work from native listeners.
    // A tap-to-assign fallback covers keyboard/touch.
    initDragDrop(root) {
      root = root || this._ddRoot;
      if (!root || typeof Sortable === "undefined") return;
      this._ddRoot = root;
      this._ddPickedEl = null;
      (this._ddSortables || []).forEach((s) => { try { s.destroy(); } catch (e) {} });
      this._ddSortables = [];

      const bank = root.querySelector(".dd-bank");
      if (!bank) return;
      bank.innerHTML = "";
      for (const item of this.currentQ.items || []) {
        const el = document.createElement("div");
        el.className = "dd-item";
        el.dataset.item = item;
        el.textContent = item;
        el.addEventListener("click", (ev) => { ev.stopPropagation(); this._ddPickEl(el); });
        bank.appendChild(el);
      }

      const opts = { group: "dd", animation: 150, onSort: () => this.ddRecount() };
      this._ddSortables.push(Sortable.create(bank, opts));
      root.querySelectorAll(".dd-bucket").forEach((bk) => {
        const zone = bk.querySelector(".dd-zone");
        this._ddSortables.push(Sortable.create(zone, opts));
        bk.onclick = () => this._ddDropPickedEl(zone);   // onclick = no listener stacking
      });
      this.ddRecount();
    },
    _ddPickEl(el) {
      if (this.feedback) return;
      if (this._ddPickedEl === el) {
        el.classList.remove("dd-item--picked");
        this._ddPickedEl = null;
        return;
      }
      if (this._ddPickedEl) this._ddPickedEl.classList.remove("dd-item--picked");
      this._ddPickedEl = el;
      el.classList.add("dd-item--picked");
    },
    _ddDropPickedEl(zone) {
      if (this.feedback || !this._ddPickedEl) return;
      zone.appendChild(this._ddPickedEl);
      this._ddPickedEl.classList.remove("dd-item--picked");
      this._ddPickedEl = null;
      this.ddRecount();
    },
    ddRecount() {
      const bank = this._ddRoot && this._ddRoot.querySelector(".dd-bank");
      this.ddRemaining = bank ? bank.querySelectorAll(".dd-item").length : 0;
    },
    ddCollectMatches() {
      const matches = {};
      if (!this._ddRoot) return matches;
      this._ddRoot.querySelectorAll(".dd-zone").forEach((zone) => {
        const bucket = zone.dataset.bucket;
        zone.querySelectorAll(".dd-item").forEach((el) => {
          matches[el.dataset.item] = bucket;
        });
      });
      return matches;
    },
    ddShowFeedback() {
      if (!this._ddRoot) return;
      (this._ddSortables || []).forEach((s) => { try { s.destroy(); } catch (e) {} });
      this._ddSortables = [];
      const authored = {};
      (this.feedback.pairs || []).forEach((p) => { authored[p.left] = p.right; });
      this._ddRoot.querySelectorAll(".dd-zone .dd-item").forEach((el) => {
        const inBucket = el.closest(".dd-zone").dataset.bucket;
        const ok = authored[el.dataset.item] === inBucket;
        el.classList.add(ok ? "dd-item--correct" : "dd-item--wrong");
      });
    },

    async submit() {
      if (this.feedback || this.submitting) return;
      const isDrag = this.currentQ?.question_type === "drag_drop";
      let body;
      if (isDrag) {
        const matches = this.ddCollectMatches();
        if (Object.keys(matches).length < (this.currentQ.items || []).length) return;
        body = { question_id: this.currentQ.question_id, matches };
      } else {
        if (!this.selection.length) return;
        body = { question_id: this.currentQ.question_id, selected_labels: this.selection };
      }
      this.submitting = true;
      this.lastQSec = Math.round((Date.now() - this._qStartedAt) / 1000);
      try {
        const json = await api(`/api/quiz/sessions/${this.sessionId}/answers`, {
          method: "POST",
          body,
        });
        if (!json.success) {
          // ALREADY_ANSWERED: advance instead of trapping user
          if (json.code === "ALREADY_ANSWERED") {
            await this.fetchNext();
            return;
          }
          window.showToast(window.friendlyError(json), "error");
          return;
        }
        this.feedback = json.data;
        if (isDrag) this.$nextTick(() => this.ddShowFeedback());
      } catch (e) {
        window.showToast(window.netErrMsg, "error");
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
          window.showToast(window.friendlyError(json), "error");
          return;
        }
        this.feedback = json.data;
      } catch (e) {
        window.showToast(window.netErrMsg, "error");
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
      try {
        const json = await api(
          `/api/quiz/sessions/${this.sessionId}/finish`, { method: "POST" });
        if (!json.success) {
          window.showToast(window.friendlyError(json), "error");
          this.view = "practice";
          return;
        }
        this.finalSummary = json.data;
        this.summaryView = 'wrong';
        this.view = "summary";
        // A finished session is reviewable: deep-link it so refresh reopens it.
        this.reviewSessionId = String(this.sessionId);
        this._setQuizPath(this.sessionId);
      } catch (e) {
        window.showToast(window.netErrMsg, "error");
        this.view = "practice";
      }
    },

    // hydrate=true when called from URL sync (back/forward, direct load): skip
    // pushing a new history entry, since the URL already points here.
    async viewSession(sessionId, hydrate = false) {
      try {
        const json = await api(`/api/quiz/sessions/${sessionId}/summary`);
        if (!json.success) {
          window.showToast(window.friendlyError(json), "error");
          this._goLanding();
          return;
        }
        this.reviewSummary = json.data;
        this.reviewSessionId = String(sessionId);
        this.summaryView = 'wrong';
        this.view = "review";
        if (!hydrate) this._setQuizPath(sessionId);
      } catch (e) {
        window.showToast(window.netErrMsg, "error");
        this._goLanding();
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

    // User-initiated return to landing: record a history entry, then reset.
    async backToLanding() {
      this._setQuizPath(null);
      await this._goLanding();
    },

    // Reset to landing without touching history (used by backToLanding and by
    // URL sync on back/forward). Always reloads so a just-finished session shows
    // in the recent list and mastery counts reflect the run.
    async _goLanding() {
      this.sessionId       = null;
      this.currentQ        = null;
      this.finalSummary    = null;
      this.reviewSummary   = null;
      this.reviewSessionId = null;
      this.summaryView     = 'wrong';
      this.selection       = [];
      this.feedback        = null;
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
