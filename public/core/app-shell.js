// window.appShell — root SPA component (nav routing, page state, lab management).
// Depends on core/main.js for Alpine stores + api() + showToast.

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

    // Composite key — changes whenever any filter input changes, which
    // remounts the keyed .cards-grid wrapper and triggers the panel fade.
    get filterKey() { return `${this.filterCat}|${this.hideStatus}`; },

    setFilter(updater) { updater(); },

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

    matchesFilter(lab) {
      if (this.filterCat && lab.category !== this.filterCat) return false;
      if (this.hideStatus === 'done'   && lab.status === STATUS.DONE) return false;
      if (this.hideStatus === 'undone' && lab.status !== STATUS.DONE) return false;
      return true;
    },

    formatTotalTime(s = 0) { return formatTime(s, 'compact'); }
  }
}
