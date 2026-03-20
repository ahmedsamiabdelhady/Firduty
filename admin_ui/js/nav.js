/**
 * nav.js — Shared navigation bar for all Firduty admin pages.
 *
 * Renders floating pill-style buttons on the blue nav bar.
 * Active page button is filled white; others are transparent with hover effect.
 * No emojis — text labels only.
 *
 * Call initNav() after I18N has loaded so labels are translated.
 * RTL direction is applied early from stored preference before I18N loads.
 */

const NAV_PAGES = [
  { href: 'dashboard.html', key: 'dashboard',        fallback: 'Dashboard'          },
  { href: 'planner.html',   key: 'week_planner',     fallback: 'Week Planner'       },
  { href: 'reports.html',   key: 'monthly_report',   fallback: 'Monthly Report'     },
  { href: 'teachers.html',  key: 'teacher_approval', fallback: 'Teachers', badge: true },
];

// Apply RTL immediately from stored preference — prevents layout flash
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

  // Detect active page — handles both "/dashboard.html" and "/dashboard" style URLs
  const raw     = window.location.pathname.split('/').pop() || '';
  const current = raw.replace(/\.html$/, '') || 'dashboard';

  bar.innerHTML = NAV_PAGES.map(p => {
    const pageKey = p.href.replace(/\.html$/, '');
    const active  = current === pageKey;
    const label   = (typeof I18N !== 'undefined' ? I18N.t(p.key) : '') || p.fallback;

    return `
      <a href="${p.href}"
         class="nav-tab${active ? ' nav-tab-active' : ''}"
         aria-current="${active ? 'page' : ''}">
        ${label}
        ${p.badge ? `<span class="nav-badge" id="navBadgePending" style="display:none">0</span>` : ''}
      </a>`;
  }).join('');
}

async function _loadPendingBadge() {
  try {
    if (typeof apiFetch !== 'function') return;
    const res = await apiFetch('/teachers/pending');
    if (!res || !res.ok) return;
    const data  = await res.json();
    const count = Array.isArray(data) ? data.length : 0;
    const badge = document.getElementById('navBadgePending');
    if (badge && count > 0) {
      badge.textContent    = count > 99 ? '99+' : count;
      badge.style.display  = 'inline-flex';
    }
  } catch (_) { /* non-critical */ }
}

