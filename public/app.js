// Alpine store — single source of truth for summary so any component can
// trigger a refresh after a mutation (status change, timer stop) and the
// dashboard progress bar / analytics page pick it up immediately.
document.addEventListener("alpine:init", () => {
  Alpine.store("app", {
    summary: { done:0, in_progress:0, not_started:0, total:51,
               completion_percent:0, total_time_spent:0 },
    async refreshSummary() {
      try {
        const res  = await fetch("/api/stats/summary");
        const json = await res.json();
        if (json.success) this.summary = json.data;
      } catch (e) { console.error("Summary refresh failed:", e); }
    }
  });
});

// ── App Shell ─────────────────────────────────────────────────────────────
function appShell() {
  return {
    page: "dashboard",
    loading: true,
    labs: [],
    filterCat: "",
    search: "",
    categories: [
      "CLI & Basic", "Switching & VLAN", "Wireless",
      "Inter-VLAN & Routing", "HSRP & ACL", "NAT & DHCP",
      "Management", "Security & Advanced"
    ],

    // Convenience getter so existing `x-text="summary.done"` bindings still work
    get summary() { return this.$store.app.summary; },

    async init() {
      await this.fetchLabs();
      window.addEventListener("refresh-labs", () => this.fetchLabs());
    },

    async fetchLabs() {
      this.loading = true;
      try {
        const labsRes = await fetch("/api/labs");
        this.labs = (await labsRes.json()).data;
        await this.$store.app.refreshSummary();
      } catch (e) {
        console.error("Failed to load labs:", e);
      } finally {
        this.loading = false;
      }
    },

    get filteredLabs() {
      const cat = this.filterCat;
      const q   = this.search.toLowerCase();
      return this.labs.filter(lab =>
        (!cat || lab.category === cat) &&
        (!q   || lab.name.toLowerCase().includes(q) || lab.id.toLowerCase().includes(q))
      );
    },

    formatTotalTime(s = 0) {
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      return h > 0 ? `${h}h ${m}m` : `${m}m`;
    }
  }
}

// ── Lab Card ──────────────────────────────────────────────────────────────
function labCard(initialLab) {
  return {
    lab: { ...initialLab },
    running: false,
    elapsed: 0,
    sessionStart: null,
    interval: null,
    toast: false,
    toastMsg: "",

    init() {
      // Resume an open timer session if one exists. The open session's
      // started_at is delivered inline with GET /api/labs (no per-card
      // fetch) via the open_session_started_at column.
      if (!this.lab.open_session_started_at) return;
      const started = new Date(this.lab.open_session_started_at);
      const elapsed = Math.floor((Date.now() - started.getTime()) / 1000);
      // 8-hour cap: if resumed elapsed is implausibly large (laptop sleep,
      // clock drift, zombie row that slipped past startup cleanup), treat
      // the session as abandoned rather than crediting bogus time.
      const EIGHT_HOURS = 8 * 3600;
      if (elapsed < 0 || elapsed > EIGHT_HOURS) return;
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
      await fetch(`/api/labs/${this.lab.id}/timer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ started_at: this.sessionStart.toISOString(), duration: 0 })
      });
      // Mirror the server state locally so a page refresh right now resumes
      // via the 8-hour-capped logic in init(), not a stale list payload.
      this.lab.open_session_started_at = this.sessionStart.toISOString();
      this.interval = setInterval(() => this.elapsed++, 1000);
    },

    async stopTimer() {
      if (!this.running) return;
      clearInterval(this.interval);
      this.running = false;
      const duration = this.elapsed;
      try {
        const res  = await fetch(`/api/labs/${this.lab.id}/timer`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ started_at: this.sessionStart.toISOString(), duration })
        });
        const json = await res.json();
        if (json.success) {
          this.lab.time_spent = json.data.time_spent;
          // Keep the dashboard progress bar / total-time counter live
          await Alpine.store("app").refreshSummary();
        }
      } catch (e) { console.error("Timer save failed:", e); }
      this.elapsed = 0;
      this.sessionStart = null;
      this.lab.open_session_started_at = null;
    },

    resetTimer() {
      clearInterval(this.interval);
      this.running = false;
      this.elapsed = 0;
      this.sessionStart = null;
    },

    async updateStatus() {
      try {
        await fetch(`/api/labs/${this.lab.id}/status`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: this.lab.status })
        });
        // Summary reflects done/in_progress/not_started counts — refresh
        // so the progress bar updates the moment the user picks a status.
        await Alpine.store("app").refreshSummary();
      } catch (e) { console.error("Status update failed:", e); }
    },

    async launch() {
      if (!this.lab.file_path) {
        this.showToast("⚠ Import this lab first. Go to Import page.");
        return;
      }
      try {
        const res  = await fetch(`/api/labs/${this.lab.id}/open`, { method: "POST" });
        const json = await res.json();
        this.showToast(json.success ? "✓ Opening in Packet Tracer..." : `✗ ${json.error}`);
      } catch (e) { this.showToast("✗ Network error"); }
    },

    showToast(msg) {
      this.toastMsg = msg;
      this.toast = true;
      clearTimeout(this._toastTimer);
      this._toastTimer = setTimeout(() => this.toast = false, 3500);
    },

    formatTime(s = 0) {
      const h   = Math.floor(s / 3600);
      const m   = Math.floor((s % 3600) / 60);
      const sec = s % 60;
      return `${String(h).padStart(2,"0")}:${String(m).padStart(2,"0")}:${String(sec).padStart(2,"0")}`;
    },

    statusLabel() {
      return { not_started:"Not Started", in_progress:"In Progress", done:"Done" }[this.lab.status] ?? "";
    },
    badgeClass() { return `badge badge--${this.lab.status}`; },
    cardClass()  {
      const base = `lab-card lab-card--${this.lab.status}`;
      return this.lab.file_path ? base : base + " lab-card--no-file";
    }
  }
}

// ── Import Page ────────────────────────────────────────────────────────────
function importPage() {
  return {
    dragging: false,
    folderPath: "",
    scanning: false,
    results: [],
    importedCount: 0,
    status: { imported_count: 0, total: 51, missing: [], imported: [] },

    async loadStatus() {
      try {
        const res  = await fetch("/api/import/status");
        const json = await res.json();
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
        const res  = await fetch("/api/import/scan", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ folder_path: this.folderPath.trim() })
        });
        const json = await res.json();
        if (json.success) {
          this.results       = json.data.results;
          this.importedCount = json.data.imported_count;
          await this.loadStatus();
        } else {
          alert(`Error: ${json.error}`);
        }
      } catch (e) { alert("Network error during scan."); }
      finally     { this.scanning = false; }
    }
  }
}

// ── Stats Page ─────────────────────────────────────────────────────────────
function statsPage() {
  return {
    loading: true,
    byCategory: [],
    chart: null,

    // Read summary from the shared store — gets live updates when the user
    // changes status or stops a timer on the dashboard without leaving the page.
    get summary() { return this.$store.app.summary; },

    async load() {
      this.loading = true;
      try {
        const [, catRes, slowRes] = await Promise.all([
          this.$store.app.refreshSummary(),
          fetch("/api/stats/by-category"),
          fetch("/api/stats/slowest")
        ]);
        this.byCategory = (await catRes.json()).data;
        const slowest   = (await slowRes.json()).data;
        this.loading    = false;
        // x-if unmounts the chart container while loading=true, so we must
        // wait for the next DOM tick before grabbing the canvas element.
        // $nextTick is the correct tool; the setTimeout(50) hack in v4.1
        // was a race disguised as a fix.
        await this.$nextTick();
        this.renderChart(slowest);
      } catch (e) {
        console.error("Stats load failed:", e);
        this.loading = false;
      }
    },

    renderChart(data) {
      const el = document.getElementById("timeChart");
      if (!el) return;
      if (this.chart) this.chart.destroy();
      this.chart = new Chart(el.getContext("2d"), {
        type: "bar",
        data: {
          labels: data.map(d => d.id),
          datasets: [{
            label: "Time Spent (minutes)",
            data: data.map(d => Math.round(d.time_spent / 60)),
            backgroundColor: "#049fd4",
            borderRadius: 4
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { stepSize: 10 } } }
        }
      });
    },

    formatTime(s = 0) {
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      return h > 0 ? `${h}h ${m}m` : `${m}m`;
    }
  }
}
