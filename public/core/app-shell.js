// window.appShell — root SPA component (nav routing, page state, lab management).
// Depends on core/main.js for Alpine stores + api() + showToast.

// Internal page state <-> URL hash. Keeps the hash human-readable
// (#practical) while the Alpine state keeps its historical names (dashboard).
const PAGE_TO_HASH = Object.freeze({
  dashboard: "practical", quiz: "quiz", stats: "analytics",
  settings: "settings", import: "import",
});
const HASH_TO_PAGE = Object.freeze(
  Object.fromEntries(Object.entries(PAGE_TO_HASH).map(([p, h]) => [h, p]))
);

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
    _navPrefix: false,        // true briefly after pressing "g" (vim/gmail-style)
    _navTimer: null,

    // Stacked card-grid panels for the filter swap transition. The most
    // recently pushed panel is the visible one; previous panels are kept
    // briefly so their leave transition can run, then garbage-collected.
    panels: [{ id: 0, fc: "", hs: "", visible: true }],
    _panelCounter: 0,

    get summary() { return this.$store.app.summary; },

    setFilter(updater) {
      updater();
      try {
        localStorage.setItem("filterCat", this.filterCat);
        localStorage.setItem("hideStatus", this.hideStatus);
      } catch (e) { /* localStorage may be blocked */ }
      this.panels.forEach(p => p.visible = false);
      const next = {
        id: ++this._panelCounter,
        fc: this.filterCat,
        hs: this.hideStatus,
        visible: false,
      };
      this.panels.push(next);
      const nextIdx = this.panels.length - 1;
      // Two rAFs: first lets Alpine mount the new panel in `view-hidden`;
      // second lets the browser paint that initial state. Without the gap
      // the class flips in one frame and CSS sees no transition.
      // Mutate via the array index — the local `next` ref is the raw object,
      // while the array proxy holds the reactive copy.
      requestAnimationFrame(() => requestAnimationFrame(() => {
        if (this.panels[nextIdx]) this.panels[nextIdx].visible = true;
        setTimeout(() => {
          this.panels = this.panels.filter(p => p.visible);
        }, 300);
      }));
    },

    async init() {
      // Restore persisted filters before the first render.
      try {
        const savedCat = localStorage.getItem("filterCat");
        const savedStatus = localStorage.getItem("hideStatus");
        if (savedCat !== null) this.filterCat = savedCat;
        if (savedStatus !== null) this.hideStatus = savedStatus;
        this.panels = [{ id: 0, fc: this.filterCat, hs: this.hideStatus, visible: true }];
      } catch (e) { /* localStorage may be blocked */ }

      // Hash routing: hydrate from the URL, then keep the two in sync.
      this.applyHash();
      window.addEventListener("hashchange", () => this.applyHash());
      this.$watch("page", (p) => {
        const hash = "#" + (PAGE_TO_HASH[p] || p);
        if (location.hash !== hash) location.hash = hash;
      });

      await this.fetchLabs();
      window.addEventListener("refresh-labs", () => this.fetchLabs());
      // Sync appShell.labs[] status without a full refetch — labCard owns
      // a spread copy, so the shell would lag behind until next page load.
      window.addEventListener("lab-status-changed", (e) => {
        const row = this.labs.find(l => l.id === e.detail.id);
        if (row) row.status = e.detail.status;
      });
    },

    // Global page navigation: press "g" then p/q/a/s. A prefix keeps it from
    // colliding with the quiz's number/Enter accelerators and from firing on a
    // stray keystroke. Ignored while typing in a field or with a modal open.
    onGlobalKey(e) {
      if (e.target.matches("input, textarea, select")) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (this.$store.modal.open || this.$store.summaryModal.open || this.$store.imageModal.open) return;

      if (this._navPrefix) {
        this._navPrefix = false;
        clearTimeout(this._navTimer);
        const dest = { p: "dashboard", q: "quiz", a: "stats", s: "settings" }[e.key.toLowerCase()];
        if (dest) { this.page = dest; e.preventDefault(); }
        return;
      }
      if (e.key === "g") {
        this._navPrefix = true;
        clearTimeout(this._navTimer);
        this._navTimer = setTimeout(() => { this._navPrefix = false; }, 1500);
        e.preventDefault();
      }
    },

    // Map the current URL hash onto page state (no-op for unknown hashes).
    applyHash() {
      const key = location.hash.replace(/^#/, "");
      const target = HASH_TO_PAGE[key];
      if (target && target !== this.page) {
        this.page = target;
      } else if (!location.hash) {
        // Seed the hash on first load so back/forward has an entry to return to.
        location.replace("#" + (PAGE_TO_HASH[this.page] || this.page));
      }
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

    matchesFilter(lab) {
      if (this.filterCat && lab.category !== this.filterCat) return false;
      if (this.hideStatus === 'done'   && lab.status === STATUS.DONE) return false;
      if (this.hideStatus === 'undone' && lab.status !== STATUS.DONE) return false;
      return true;
    },

    formatTotalTime(s = 0) { return formatTime(s, 'compact'); }
  }
}
