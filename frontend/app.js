/* ═══════════════════════════════════════════════════════════════
   HIVE OS — Shared JavaScript
   ═══════════════════════════════════════════════════════════════ */

const API_BASE = 'http://localhost:8000';
let sseConnection = null;
let refreshIntervals = [];
let toastQueue = [];

/* ─── API HELPERS ─────────────────────────────────────────────────── */
async function api(path, opts = {}) {
  try {
    const res = await fetch(`${API_BASE}${path}`, {
      headers: { 'Content-Type': 'application/json', ...opts.headers },
      ...opts,
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
    return await res.json();
  } catch (e) {
    if (e.name === 'TypeError' && e.message.includes('fetch')) {
      showToast('Backend offline — start with: python main.py', 'error');
    } else {
      showToast(`API error: ${e.message}`, 'error');
    }
    return null;
  }
}

const apiGet  = (p) => api(p);
const apiPost = (p, b) => api(p, { method: 'POST', body: JSON.stringify(b) });

/* ─── REFRESH MANAGER ─────────────────────────────────────────────── */
function startRefresh(fn, interval = 3000) {
  fn(); // immediate
  const id = setInterval(fn, interval);
  refreshIntervals.push(id);
  return id;
}

function stopAllRefresh() {
  refreshIntervals.forEach(id => clearInterval(id));
  refreshIntervals = [];
}

/* ─── SSE CONNECTION ──────────────────────────────────────────────── */
function connectSSE(onMessage) {
  disconnectSSE();
  try {
    sseConnection = new EventSource(`${API_BASE}/events`);
    sseConnection.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        onMessage(data);
      } catch {}
    };
    sseConnection.onerror = () => {
      setTimeout(() => connectSSE(onMessage), 5000);
    };
  } catch (e) {
    // SSE not available, fall back to polling
  }
}

function disconnectSSE() {
  if (sseConnection) {
    sseConnection.close();
    sseConnection = null;
  }
}

/* ─── TOAST / NOTIFICATION ────────────────────────────────────────── */
function showToast(msg, type = 'info', duration = 4000) {
  let container = document.querySelector('.toast-container');
  if (!container) {
    container = document.createElement('div');
    container.className = 'toast-container';
    document.body.appendChild(container);
  }
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const icons = { success: '✓', error: '✕', warning: '!', info: 'i' };
  toast.innerHTML = `<span style="font-weight:700">${icons[type] || 'i'}</span><span>${msg}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

/* ─── MODAL ───────────────────────────────────────────────────────── */
function showModal(title, body, footer = '') {
  const existing = document.querySelector('.modal-overlay');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay';
  overlay.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <span class="modal-title">${title}</span>
        <button class="modal-close" onclick="this.closest('.modal-overlay').remove()">✕</button>
      </div>
      <div class="modal-body">${body}</div>
      ${footer ? `<div class="modal-footer">${footer}</div>` : ''}
    </div>`;
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
  return overlay;
}

/* ─── NAV ACTIVE ──────────────────────────────────────────────────── */
function initNav() {
  const path = window.location.pathname.split('/').pop() || 'index.html';
  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.toggle('active', link.getAttribute('href') === path ||
      (path === '' && link.getAttribute('href') === 'index.html'));
  });
}

/* ─── ANIMATED COUNTER ───────────────────────────────────────────── */
function animateCounter(el, target, duration = 800) {
  if (!el) return;
  const start = parseInt(el.textContent) || 0;
  const isFloat = String(target).includes('.');
  const decimals = isFloat ? (String(target).split('.')[1] || '').length : 0;
  const startTime = performance.now();

  function update(now) {
    const elapsed = now - startTime;
    const progress = Math.min(elapsed / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = start + (target - start) * eased;
    el.textContent = isFloat ? current.toFixed(decimals) : Math.round(current);
    if (progress < 1) requestAnimationFrame(update);
  }
  requestAnimationFrame(update);
}

/* ─── UTILITY ─────────────────────────────────────────────────────── */
function timeAgo(ts) {
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return `${Math.round(diff)}s ago`;
  if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.round(diff / 3600)}h ago`;
  return `${Math.round(diff / 86400)}d ago`;
}

function formatDuration(s) {
  if (s < 1) return `${Math.round(s * 1000)}ms`;
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

function clamp(v, min, max) {
  return Math.min(Math.max(v, min), max);
}

function pulseClass(el, cls = 'animate-glow') {
  el.classList.add(cls);
  setTimeout(() => el.classList.remove(cls), 2000);
}

/* ─── SKIPLEY ─────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  initNav();

  // Auto-refresh stop on page hide
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) stopAllRefresh();
    else location.reload();
  });
});

/* ─── EXPORTED FOR PAGE SCRIPTS ───────────────────────────────────── */
window.HIVE = {
  api, apiGet, apiPost,
  startRefresh, stopAllRefresh,
  connectSSE, disconnectSSE,
  showToast, showModal,
  animateCounter,
  timeAgo, formatDuration, clamp, pulseClass,
};