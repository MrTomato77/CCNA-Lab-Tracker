// Shared infrastructure: constants, Transitions FLIP orchestrator, api() fetch
// wrapper, time formatter, Alpine stores (app/modal/summaryModal/imageModal),
// toast service. Loads BEFORE every page component.

// ── Shared constants ──────────────────────────────────────────────────────
// Mirror of core/constants.py — sync manually when adding values backend-side.
const STATUS = Object.freeze({
  NOT_STARTED: 'not_started',
  IN_PROGRESS: 'in_progress',
  DONE:        'done',
});
const STATUS_LABELS = Object.freeze({
  not_started: 'Not Started',
  in_progress: 'In Progress',
  done:        'Done',
});
const CATEGORIES = Object.freeze([
  'CLI & Basic',     'Switching & VLAN', 'Wireless',
  'Inter-VLAN & Routing', 'HSRP & ACL',  'NAT & DHCP',
  'Management',      'Security & Advanced',
]);

// 8h cap on resumed timers — see labCard.init() for rationale.
const TIMER_RESUME_CAP_SEC = 8 * 3600;

// ── Transitions service ───────────────────────────────────────────────────
// Single source of truth for animation timing and easings, mirrored in
// CSS custom properties (:root in style.css). JS-driven follow-ups
// (toasts, chart re-renders) should read from here so they can't drift
// from the stylesheet.
//
// filterList() smooths list-filter transitions by combining two
// techniques into one orchestrator:
//
//   • LEAVING cards (visible → hidden) are pinned to position:absolute
//     at their old rect, dropping out of flow immediately so siblings
//     don't reserve their slots during the fade-out.
//   • REMAINING cards (visible → visible) get a FLIP animation: snapshot
//     before, measure after, jump back to the old position via
//     transform, then animate the transform to zero. The user sees a
//     smooth slide from old slot to new slot rather than an instant
//     "snap up" when the layout collapses.
//   • ENTERING cards (hidden → visible) are left alone — Alpine's enter
//     transition fades them in at their final slot, which is correct
//     because leaving cards are already out of flow by then.
//
// Usage:
//   const flip = Transitions.filterList('.cards-grid');
//   // Inside a filter handler:
//   flip.snapshot();         // capture positions before mutation
//   this.filterCat = cat;    // trigger Alpine reactivity
//   this.$nextTick(() => flip.play());
//
// Reusable for any flex/grid list with x-show + fade transitions — pass
// the container selector, optionally override duration/easing/leaveClass.
const Transitions = Object.freeze({
  DURATION: Object.freeze({ fast: 120, normal: 200, slow: 320 }),  // ms
  EASING: Object.freeze({
    default: 'cubic-bezier(.2, .8, .2, 1)',
    sharp:   'cubic-bezier(.4, 0, .6, 1)',
  }),

  filterList(containerSelector, opts = {}) {
    const duration   = opts.duration   ?? this.DURATION.normal;
    const easing     = opts.easing     ?? this.EASING.default;
    const leaveClass = opts.leaveClass ?? 'card-fade-leave';

    let oldPositions = new Map();

    const realChildren = (container) =>
      [...container.children].filter((el) => el.tagName !== 'TEMPLATE');

    return {
      snapshot() {
        oldPositions = new Map();
        for (const container of document.querySelectorAll(containerSelector)) {
          if (getComputedStyle(container).position === 'static') {
            container.style.position = 'relative';
          }
          for (const el of realChildren(container)) {
            if (getComputedStyle(el).display === 'none') continue;
            oldPositions.set(el, {
              rect: el.getBoundingClientRect(),
              container,
            });
          }
        }
      },

      play() {
        // Pass 1 — pin leaving cards to absolute at their snapshotted
        // position, taking them out of flow so layout settles to its
        // final form before we measure remaining cards.
        for (const [el, { rect: oldRect, container }] of oldPositions) {
          if (!el.classList.contains(leaveClass)) continue;
          const cRect = container.getBoundingClientRect();
          el.style.position = 'absolute';
          el.style.top    = `${oldRect.top  - cRect.top }px`;
          el.style.left   = `${oldRect.left - cRect.left}px`;
          el.style.width  = `${oldRect.width}px`;
          const onLeaveEnd = (e) => {
            if (e.propertyName !== 'opacity') return;
            el.style.position = '';
            el.style.top      = '';
            el.style.left     = '';
            el.style.width    = '';
            el.removeEventListener('transitionend', onLeaveEnd);
          };
          el.addEventListener('transitionend', onLeaveEnd);
        }

        // Pass 2 — FLIP remaining cards. Layout is now collapsed (leaving
        // cards are absolute), so getBoundingClientRect returns the FINAL
        // positions. We jump back to old positions via transform, then
        // animate the transform to zero on the next frame.
        for (const [el, { rect: oldRect }] of oldPositions) {
          if (el.classList.contains(leaveClass)) continue;
          if (getComputedStyle(el).display === 'none') continue;
          const newRect = el.getBoundingClientRect();
          const dx = oldRect.left - newRect.left;
          const dy = oldRect.top  - newRect.top;
          if (Math.abs(dx) < 0.5 && Math.abs(dy) < 0.5) continue;

          el.style.transition = 'none';
          el.style.transform  = `translate(${dx}px, ${dy}px)`;
          // Force the inverted state to apply before unwinding it.
          void el.offsetWidth;
          requestAnimationFrame(() => {
            el.style.transition = `transform ${duration}ms ${easing}`;
            el.style.transform  = '';
            const onFlipEnd = (e) => {
              if (e.propertyName !== 'transform') return;
              el.style.transition = '';
              el.style.transform  = '';
              el.removeEventListener('transitionend', onFlipEnd);
            };
            el.addEventListener('transitionend', onFlipEnd);
          });
        }
      },
    };
  },
});
window.Transitions = Transitions;

// ── Fetch wrapper ─────────────────────────────────────────────────────────
// Returns the parsed JSON envelope when the server speaks JSON, regardless
// of HTTP status — the backend always wraps errors as {success:false,...}.
// If the response isn't JSON (e.g. a router crash returning HTML 500) the
// wrapper synthesizes a {success:false} envelope so callers don't blow up
// on res.json() and can fall through to a generic error toast. The HTTP
// status is bubbled up via .status so callers that care (e.g. quiz's 409
// ALREADY_ANSWERED auto-advance) can branch on it.
async function api(path, { method = 'GET', body = null } = {}) {
  const opts = { method };
  if (body !== null) {
    opts.headers = { 'Content-Type': 'application/json' };
    opts.body    = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  const ctype = res.headers.get('content-type') || '';
  if (!ctype.includes('application/json')) {
    return { success: false, error: `HTTP ${res.status}`,
             code: 'NON_JSON_RESPONSE', status: res.status };
  }
  try {
    const json = await res.json();
    if (typeof json === 'object' && json !== null && !('status' in json)) {
      json.status = res.status;
    }
    return json;
  } catch (e) {
    return { success: false, error: 'Malformed JSON response',
             code: 'BAD_JSON', status: res.status };
  }
}

// ── Time formatting ───────────────────────────────────────────────────────
// mode: 'clock' → "HH:MM:SS" | 'compact' → "4h 32m" | 'rich' → "4<sup>h</sup> 32<sup>m</sup>"
function formatTime(s = 0, mode = 'clock') {
  s = Math.max(0, s | 0);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  if (mode === 'compact') return h > 0 ? `${h}h ${m}m` : `${m}m`;
  if (mode === 'rich')    return h > 0 ? `${h}<sup>h</sup> ${m}<sup>m</sup>` : `${m}<sup>m</sup>`;
  return `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`;
}

document.addEventListener("alpine:init", () => {
  Alpine.store("app", {
    summary: { done:0, in_progress:0, not_started:0, total:51,
               completion_percent:0, total_time_spent:0 },
    async refreshSummary() {
      try {
        const json = await api("/api/stats/summary");
        if (json.success) this.summary = json.data;
      } catch (e) { console.error("Summary refresh failed:", e); }
    }
  });

  Alpine.store("modal", {
    open: false, title: "", message: "", danger: false, resolve: null,
    show(message, title = "", danger = false) {
      return new Promise(resolve => {
        this.title = title; this.message = message;
        this.danger = danger; this.resolve = resolve;
        this.open = true;
      });
    },
    ok()     { if (this.resolve) this.resolve(true);  this.open = false; },
    cancel() { if (this.resolve) this.resolve(false); this.open = false; }
  });

  Alpine.store("summaryModal", {
    open: false,
    lab: null,
    data: null,
    loading: false,
    error: null,
    async show(lab) {
      this.lab = { id: lab.id, name: lab.name };
      this.data = null;
      this.error = null;
      this.loading = true;
      this.open = true;
      try {
        const res = await api(`/api/labs/${lab.id}/summary`);
        if (res.success) {
          this.data = res.data;
        } else {
          this.error = res.code === "SUMMARY_MISSING"
            ? "No cheat-sheet for this lab yet."
            : (res.error || "Failed to load");
        }
      } catch (e) {
        this.error = "Network error";
      } finally {
        this.loading = false;
      }
    },
    close() { this.open = false; this.data = null; this.error = null; }
  });

  Alpine.store("imageModal", {
    open: false,
    url: null,
    show(url) { this.url = url; this.open = true; },
    close()   { this.open = false; this.url = null; },
  });
});

// ── Toast Service ─────────────────────────────────────────────────────
window.showToast = function(message, type = 'info', duration = 1800) {
  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('toast--leaving');
    setTimeout(() => toast.remove(), 220);
  }, duration);
};
