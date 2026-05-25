// practical/lab-card.js — window.labCard Alpine component.
// Single lab-row state: timer ticking, launch/stop/done actions,
// status pill, per-card reset, brief modal dispatch.
// Depends on core/main.js for STATUS, TIMER_RESUME_CAP_SEC, formatTime(),
// api(), Alpine stores (modal/summaryModal/app), showToast.

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

    cardClass()  {
      const base = `lab-card lab-card--${this.lab.status}`;
      return this.lab.file_path ? base : base + " lab-card--no-file";
    }
  }
}
