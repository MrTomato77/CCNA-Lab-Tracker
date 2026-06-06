// window.settingsPage. Theme toggle, reset labs, reset quiz data.
// Depends on core/main.js (api, Alpine stores, toast).

// ── Settings Page ─────────────────────────────────────────────────────────────
window.settingsPage = function() {
  return {
    theme: document.documentElement.getAttribute("data-theme") || "light",

    toggleTheme() {
      this.theme = this.theme === "light" ? "dark" : "light";
      document.documentElement.setAttribute("data-theme", this.theme);
      try { localStorage.setItem("theme", this.theme); } catch (e) { /* ignore */ }
      // Trigger theme-changed event for analytics chart redraw
      if (window.appShell) {
        window.appShell.theme = this.theme;
      }
    },

    async resetAllLabs() {
      const ok = await Alpine.store("modal").show(
        "This will reset ALL labs to Not Started and clear all timer data. This cannot be undone.",
        "Reset All Labs", true, "RESET"
      );
      if (!ok) return;
      try {
        const json = await api("/api/labs/reset", { method: "POST" });
        if (json.success) {
          window.showToast("+ All labs have been reset successfully!", 'success');
          // Refresh labs if on dashboard
          if (window.appShell) {
            await window.appShell.fetchLabs();
          }
        } else {
          window.showToast(`× Error: ${json.error}`, 'error');
        }
      } catch (e) {
        window.showToast("× Network error while resetting labs", 'error');
        console.error("Reset failed:", e);
      }
    },

    async resetQuizData() {
      const ok = await Alpine.store("modal").show(
        "This will reset ALL quiz progress, sessions, and answer history. Question content is preserved. This cannot be undone.",
        "Reset all quiz data", true, "RESET",
      );
      if (!ok) return;
      try {
        const json = await api("/api/quiz/reset", { method: "POST" });
        if (json.success) {
          window.showToast(
            `+ Cleared ${json.data.cleared_progress} progress, ${json.data.cleared_sessions} sessions, ${json.data.cleared_answers} answers`,
            "success",
          );
          // Refresh quiz dashboard if on quiz page
          if (window.quizPage) {
            const quizInstance = Alpine.$data(document.querySelector('[x-data="quizPage()"]'));
            if (quizInstance) {
              await quizInstance.loadDashboard();
            }
          }
        } else {
          window.showToast("× " + json.error, "error");
        }
      } catch (e) {
        window.showToast("× Network error", "error");
      }
    }
  };
};
