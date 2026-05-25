// window.statsPage + chart theme sync. UI: Analytics (internal: page==='stats').
// Depends on core/main.js (api()); Chart.js from CDN.

// ── Stats Page ─────────────────────────────────────────────────────────────
window.statsPage = function() {
  return {
    loading: true,
    byCategory: [],
    quizSummary: {},
    chart: null,
    accuracyChart: null,

    get summary() { return this.$store.app.summary; },

    async load() {
      this.loading = true;
      try {
        const [, cat, slow, quiz, accuracyTrend] = await Promise.all([
          this.$store.app.refreshSummary(),
          api("/api/stats/by-category"),
          api("/api/stats/slowest"),
          api("/api/stats/quiz-summary"),
          api("/api/stats/quiz-accuracy-trend"),
        ]);
        this.byCategory = cat.data;
        const slowest   = slow.data;
        this._slowest   = slowest;
        this.quizSummary = quiz.data;
        this._accuracyTrend = accuracyTrend.data;
        this.loading    = false;
        await this.$nextTick();  // x-if unmounts canvas while loading=true
        this.renderChart(slowest);
        this.renderAccuracyChart(accuracyTrend.data);
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

    renderAccuracyChart(data) {
      const el = document.getElementById("accuracyChart");
      if (!el) return;
      if (this.accuracyChart) this.accuracyChart.destroy();
      const css = getComputedStyle(document.documentElement);
      const accent = css.getPropertyValue("--accent").trim() || "#1d8fc7";
      const accentRgb = css.getPropertyValue("--accent-rgb").trim() || "29, 143, 199";
      const border = css.getPropertyValue("--border").trim() || "#e8eaf2";
      const text3  = css.getPropertyValue("--text-3").trim() || "#7c8294";
      this.accuracyChart = new Chart(el.getContext("2d"), {
        type: "line",
        data: {
          labels: data.map((_, i) => `Session ${i + 1}`),
          datasets: [{
            label: "accuracy",
            data: data.map(d => d.accuracy),
            borderColor: accent,
            backgroundColor: `rgba(${accentRgb}, 0.10)`,
            fill: true,
            tension: 0.3,
            pointRadius: 3,
            pointBackgroundColor: accent
          }]
        },
        options: {
          responsive: true,
          plugins: { legend: { display: false } },
          scales: {
            x: {
              grid:   { display: false, drawBorder: false },
              border: { color: border },
              ticks:  { color: text3, font: { family: "Outfit", size: 10 } }
            },
            y: {
              beginAtZero: false,
              min: 0,
              max: 100,
              grid:   { color: border, drawBorder: false, lineWidth: 1 },
              border: { display: false },
              ticks:  { stepSize: 20, color: text3, font: { family: "Outfit", size: 10 } }
            }
          }
        }
      });
    },

    formatTime(s = 0)     { return formatTime(s, 'compact'); },
    formatTimeRich(s = 0) { return formatTime(s, 'rich');    }
  }
}

// ── Stats theme-listener (one-time bind) ─────────────────────────────
// Hoisted to avoid leaking listeners on repeated navigation.
let _statsRef = null;
let _accuracyChartRef = null;
let _statsThemeBound = false;
function bindStatsThemeListener(getCurrent) {
  _statsRef = getCurrent;
  _accuracyChartRef = getCurrent().accuracyChart;
  if (_statsThemeBound) return;
  _statsThemeBound = true;
  window.addEventListener('theme-changed', () => {
    const cur = _statsRef && _statsRef();
    if (cur && cur._slowest) cur.renderChart(cur._slowest);
    if (cur && cur._accuracyTrend) cur.renderAccuracyChart(cur._accuracyTrend);
  });
}
