/**
 * nav.js — Shared navigation bar for all Firduty admin pages.
 *
 * Injects a unified tab bar with icons, active state, and a live
 * pending-teachers badge. Call initNav() once on each page.
 *
 * Determines the active tab from window.location.pathname.
 */

const NAV_PAGES = [
  { href: 'dashboard.html', icon: '📊', key: 'dashboard',       label: 'Dashboard' },
  { href: 'planner.html',   icon: '📅', key: 'week_planner',    label: 'Week Planner' },
  { href: 'reports.html',   icon: '🏆', key: 'monthly_report',  label: 'Report' },
  { href: 'teachers.html',  icon: '👥', key: 'teacher_approval', label: 'Teachers', badge: 'pendingTeachers' },
];

// Cached pending count — refreshed once per page load
let _pendingCount = 0;

async function initNav() {
  _renderNav();
  // Load pending count in background — non-blocking
  _loadPendingCount();
}

function _renderNav() {
  const current = window.location.pathname.split('/').pop() || 'dashboard.html';

  const html = NAV_PAGES.map(p => {
    const active = current === p.href || (current === '' && p.href === 'dashboard.html');
    const badgeHtml = p.badge === 'pendingTeachers' && _pendingCount > 0
      ? `<span class="nav-badge" id="navBadgePending">${_pendingCount}</span>`
      : `<span class="nav-badge" id="navBadgePending" style="display:none">0</span>`;

    return `
      <a href="${p.href}"
         class="nav-tab${active ? ' nav-tab-active' : ''}"
         data-i18n="${p.key}"
         aria-current="${active ? 'page' : ''}">
        <span class="nav-tab-icon">${p.icon}</span>
        <span class="nav-tab-label">${I18N.t(p.key) || p.label}</span>
        ${p.badge ? badgeHtml : ''}
      </a>
    `;
  }).join('');

  const bar = document.getElementById('mainNav');
  if (bar) bar.innerHTML = html;
}

async function _loadPendingCount() {
  try {
    const res = await apiFetch('/teachers/pending');
    if (!res || !res.ok) return;
    const data = await res.json();
    _pendingCount = Array.isArray(data) ? data.length : 0;

    // Update badge in-place without re-rendering the whole nav
    const badge = document.getElementById('navBadgePending');
    if (badge) {
      badge.textContent = _pendingCount;
      badge.style.display = _pendingCount > 0 ? 'inline-flex' : 'none';
    }
  } catch (_) {
    // Non-critical — badge simply stays hidden
  }
}