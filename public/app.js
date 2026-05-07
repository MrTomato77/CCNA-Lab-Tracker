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
window.appShell = function() {
  return {
    page: "dashboard",
    loading: true,
    labs: [],
    filterCat: "",
    hideStatus: "",
    categories: [
      "CLI & Basic", "Switching & VLAN", "Wireless",
      "Inter-VLAN & Routing", "HSRP & ACL", "NAT & DHCP",
      "Management", "Security & Advanced"
    ],

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

    async resetAllLabs() {
      if (!confirm("! This will reset ALL labs to Not Started and clear all timer data. Are you sure?")) {
        return;
      }
      try {
        const res = await fetch("/api/labs/reset", { method: "POST" });
        const json = await res.json();
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

    get filteredLabs() {
      const cat = this.filterCat;
      const hide = this.hideStatus;
      return this.labs.filter(lab => {
        const matchCat = !cat || lab.category === cat;
        let matchStatus = true;
        if (hide === 'done') matchStatus = lab.status !== 'done';
        if (hide === 'undone') matchStatus = lab.status === 'done';
        return matchCat && matchStatus;
      });
    },

    formatTotalTime(s = 0) {
      const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
      return h > 0 ? `${h}h ${m}m` : `${m}m`;
    }
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
      // 8-hour cap: if resumed elapsed is implausibly large (laptop sleep,
      // clock drift, zombie row that slipped past startup cleanup), treat
      // the session as abandoned rather than crediting bogus time.
      if (!this.lab.open_session_started_at) return;
      const started = new Date(this.lab.open_session_started_at);
      const elapsed = Math.floor((Date.now() - started.getTime()) / 1000);
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
          // Auto-mark done after stop (per user-confirmed launch flow)
          this.lab.status = 'done';
          await this.updateStatus('done');
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
      if (!confirm(`Reset progress and time for ${this.lab.id}?`)) return;
      try {
        const res = await fetch(`/api/labs/reset-single/${this.lab.id}`, { method: "POST" });
        const json = await res.json();
        if (json.success) {
          this.lab.status = 'not_started';
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
        await fetch(`/api/labs/${this.lab.id}/status`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: status })
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
        const res  = await fetch(`/api/labs/${this.lab.id}/open`, { method: "POST" });
        const json = await res.json();
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
window.statsPage = function() {
  return {
    loading: true,
    byCategory: [],
    chart: null,

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

// ── Toast Service ─────────────────────────────────────────────────────
window.showToast = function(message, type = 'info', duration = 1000) {
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  toast.style.cssText = `
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    padding: 12px 20px;
    background: ${type === 'error' ? '#dc2626' : type === 'success' ? '#059669' : '#0891b2'};
    color: white;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 500;
    z-index: 1000;
    box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    transition: all 0.3s ease;
    max-width: 400px;
    text-align: center;
  `;

  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(-50%) translateY(-20px)';
    setTimeout(() => document.body.removeChild(toast), 300);
  }, duration);
};

// Disable Alpine auto-start and start it manually (deferLoadingAlpine helper)
window.deferLoadingAlpine = function (callback) {
  window.addEventListener('DOMContentLoaded', () => {
    callback();
  });
};
