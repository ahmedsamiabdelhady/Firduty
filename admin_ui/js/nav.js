/**
 * nav.js — Shared navigation bar for all Firduty admin pages.
 *
 * Injects a unified <nav class="main-nav"> into #mainNav on every page.
 * Call initNav() after I18N has loaded so labels are translated.
 *
 * Also applies RTL direction from stored language preference immediately,
 * before I18N loads, to prevent layout flash.
 */

const NAV_PAGES = [
  { href: 'dashboard.html', icon: '📊', key: 'dashboard',        fallback: 'Dashboard'     },
  { href: 'planner.html',   icon: '📅', key: 'week_planner',     fallback: 'Week Planner'  },
  { href: 'reports.html',   icon: '🏆', key: 'monthly_report',   fallback: 'Report'        },
  { href: 'teachers.html',  icon: '👥', key: 'teacher_approval', fallback: 'Teachers', badge: true },
];

// Apply RTL immediately from stored preference (before I18N loads)
(function applyDirEarly() {
  const lang = localStorage.getItem('firduty_lang') || 'ar';
  document.documentElement.lang = lang;
  document.documentElement.dir  = lang === 'ar' ? 'rtl' : 'ltr';
})();

function initNav() {
  _renderNav();
  _loadPendingBadge();
}

function _renderNav() {
  const bar = document.getElementById('mainNav');
  if (!bar) return;

  // Detect active page by filename
  const current = window.location.pathname.split('/').pop() || 'dashboard.html';

  bar.innerHTML = NAV_PAGES.map(p => {
    const active = current === p.href;
    const label  = (typeof I18N !== 'undefined' ? I18N.t(p.key) : '') || p.fallback;

    return `
      <a href="${p.href}"
         class="nav-tab${active ? ' nav-tab-active' : ''}"
         aria-current="${active ? 'page' : ''}">
        <span class="nav-tab-icon" aria-hidden="true">${p.icon}</span>
        <span class="nav-tab-label">${label}</span>
        ${p.badge ? `<span class="nav-badge" id="navBadgePending" style="display:none">0</span>` : ''}
      </a>`;
  }).join('');
}

async function _loadPendingBadge() {
  // Only show badge on Teachers page or fetch count on all pages
  try {
    if (typeof apiFetch !== 'function') return;
    const res = await apiFetch('/teachers/pending');
    if (!res || !res.ok) return;
    const data = await res.json();
    const count = Array.isArray(data) ? data.length : 0;
    const badge = document.getElementById('navBadgePending');
    if (badge && count > 0) {
      badge.textContent = count > 99 ? '99+' : count;
      badge.style.display = 'inline-flex';
    }
  } catch (_) { /* non-critical */ }
}