/**
 * dashboard.js — Admin Dashboard for Firduty  v2.5
 *
 * Uses apiFetch() from auth.js for all API calls (handles JWT + 401 redirect).
 * i18n via I18N.t() from i18n.js.
 *
 * Key improvements vs v2.4:
 *  - Auto-init via DOMContentLoaded (no manual I18N.load call in HTML)
 *  - Proper loading / error states
 *  - refreshDashboard() for the header ↺ button
 *  - Day-by-day fill bars inside each week section
 *  - Teacher reliability section
 */

/* ─── Helpers ─────────────────────────────────────────────────────────────── */

function escHtml(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function lang() { return I18N.getLang(); }

function showToast(msg, type = 'success') {
  const c = document.getElementById('toastContainer');
  if (!c) return;
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

function statusPill(status) {
  if (!status) return `<span class="status-pill none">${I18N.t('no_week_plan')}</span>`;
  return `<span class="status-pill ${status}">${I18N.t(status)}</span>`;
}

function rankBadge(i) {
  const cls = ['gold','silver','bronze'][i] ?? '';
  return `<span class="rank-badge ${cls}">${i + 1}</span>`;
}

function barRow(label, count, maxCount, cssClass = '') {
  const pct = maxCount > 0 ? Math.round((count / maxCount) * 100) : 0;
  return `
    <div class="bar-row">
      <span class="bar-label" title="${escHtml(label)}">${escHtml(label)}</span>
      <div class="bar-track"><div class="bar-fill ${cssClass}" style="width:${pct}%"></div></div>
      <span class="bar-count">${count}</span>
    </div>`;
}

function greetingText() {
  const h = new Date().getHours();
  if (h < 12) return '🌅 ' + (I18N.t('good_morning')  || 'Good morning');
  if (h < 18) return '☀️ ' + (I18N.t('good_afternoon') || 'Good afternoon');
  return '🌙 ' + (I18N.t('good_evening') || 'Good evening');
}

/* ─── Week section renderer ───────────────────────────────────────────────── */

function renderWeekSection(stats, label) {
  if (!stats) {
    return `
      <div class="section-card">
        <h3>${escHtml(label)}</h3>
        <p style="color:var(--text-muted);font-size:0.88rem">${I18N.t('no_week_plan')}</p>
      </div>`;
  }

  // Mini stat cards
  const assignedPct = stats.total_slots > 0
    ? Math.round((stats.assigned_slots / stats.total_slots) * 100) : 0;

  const miniStats = `
    <div class="mini-stat-grid">
      <div class="mini-stat">
        <div class="mini-stat-value">${stats.total_slots}</div>
        <div class="mini-stat-label">${I18N.t('total_slots')}</div>
      </div>
      <div class="mini-stat">
        <div class="mini-stat-value green">${stats.assigned_slots}</div>
        <div class="mini-stat-label">${I18N.t('assigned_slots')}</div>
      </div>
      <div class="mini-stat">
        <div class="mini-stat-value ${stats.unassigned_slots > 0 ? 'red' : 'green'}">${stats.unassigned_slots}</div>
        <div class="mini-stat-label">${I18N.t('unassigned_slots')}</div>
      </div>
      <div class="mini-stat">
        <div class="mini-stat-value">${assignedPct}%</div>
        <div class="mini-stat-label">${I18N.t('assigned_slots')}</div>
      </div>
    </div>`;

  // Day-by-day fill bars
  let dayBarsHtml = '';
  if (stats.duties_per_day && Object.keys(stats.duties_per_day).length > 0) {
    const maxDay = Math.max(...Object.values(stats.duties_per_day), 1);
    dayBarsHtml = `
      <h4 style="font-size:0.82rem;font-weight:600;color:var(--text-muted);margin:0 0 8px">${I18N.t('duties_per_day')}</h4>
      ${Object.entries(stats.duties_per_day).map(([d, c]) => {
        const pct = Math.round((c / maxDay) * 100);
        return `
          <div class="day-fill-bar">
            <span class="day-fill-bar-name">${escHtml(d)}</span>
            <div class="day-fill-bar-track">
              <div class="day-fill-bar-fill" style="width:${pct}%"></div>
            </div>
            <span class="day-fill-bar-pct">${c}</span>
          </div>`;
      }).join('')}`;
  }

  // Duty type breakdown
  const morningCount = stats.duties_per_type?.morning_endofday ?? 0;
  const breakCount   = stats.duties_per_type?.break ?? 0;
  const maxType      = Math.max(morningCount, breakCount, 1);
  const typeHtml = `
    <h4 style="font-size:0.82rem;font-weight:600;color:var(--text-muted);margin:14px 0 8px">${I18N.t('duties_by_type')}</h4>
    ${barRow(I18N.t('morning_endofday'), morningCount, maxType, '')}
    ${barRow(I18N.t('break_duty'),       breakCount,   maxType, 'break-type')}`;

  // Top teachers bar
  let topHtml = '';
  if (stats.teacher_counts?.length > 0) {
    const maxT = stats.teacher_counts[0].count || 1;
    topHtml = `
      <h4 style="font-size:0.82rem;font-weight:600;color:var(--text-muted);margin:14px 0 8px">${I18N.t('duties_per_teacher')}</h4>
      ${stats.teacher_counts.slice(0, 8).map(t => barRow(t.teacher_name, t.count, maxT)).join('')}
      ${stats.teacher_counts.length > 8
        ? `<p style="font-size:0.75rem;color:var(--text-muted);margin-top:4px">+${stats.teacher_counts.length - 8} ${I18N.t('more')}</p>`
        : ''}`;
  }

  return `
    <div class="section-card">
      <h3>
        📅 ${escHtml(label)} — ${statusPill(stats.status)}
        <small style="font-weight:400;color:var(--text-muted);font-size:0.78rem"> v${stats.version ?? 1}</small>
      </h3>
      ${miniStats}
      ${dayBarsHtml}
      ${typeHtml}
      ${topHtml}
    </div>`;
}

/* ─── Main render ─────────────────────────────────────────────────────────── */

function renderDashboard(data) {
  const updatedAt = new Date().toLocaleTimeString(lang() === 'ar' ? 'ar-OM' : 'en-GB',
    { hour: '2-digit', minute: '2-digit' });

  // Top stat cards
  const noPending = data.teachers_without_duties_this_week?.length ?? 0;
  const topCards = `
    <div class="dash-greet">
      <div class="dash-greet-text">
        <h2>${greetingText()}</h2>
        <p>${I18N.t('week_planner') || 'Duty Roster'} — ${I18N.t('dashboard') || 'Admin Dashboard'}</p>
      </div>
      <span class="dash-updated">↺ ${I18N.t('loading') ? '' : 'Updated'} ${updatedAt}</span>
    </div>

    <div class="dash-stat-grid">
      <div class="dash-stat-card">
        <div class="dash-stat-icon">👩‍🏫</div>
        <div class="dash-stat-value">${data.total_active_teachers}</div>
        <div class="dash-stat-label">${I18N.t('active_teachers')}</div>
      </div>
      <div class="dash-stat-card">
        <div class="dash-stat-icon">📍</div>
        <div class="dash-stat-value">${data.total_locations}</div>
        <div class="dash-stat-label">${I18N.t('total_locations')}</div>
      </div>
      <div class="dash-stat-card">
        <div class="dash-stat-icon">⏰</div>
        <div class="dash-stat-value">${data.total_shifts}</div>
        <div class="dash-stat-label">${I18N.t('total_shifts')}</div>
      </div>
      <div class="dash-stat-card ${noPending > 0 ? 'orange' : 'green'}">
        <div class="dash-stat-icon">${noPending > 0 ? '⚠️' : '✅'}</div>
        <div class="dash-stat-value ${noPending > 0 ? 'orange' : 'green'}">${noPending}</div>
        <div class="dash-stat-label">${I18N.t('teachers_no_duties')}</div>
      </div>
    </div>`;

  // Warnings
  let warningsHtml = '';
  if (data.warnings?.length > 0) {
    const items = data.warnings.map(w => `<li>${escHtml(w)}</li>`).join('');
    warningsHtml = `
      <div class="section-card">
        <h3>⚠️ ${I18N.t('warnings')}</h3>
        <ul class="warn-list">${items}</ul>
      </div>`;
  }

  // Top teachers leaderboard
  let topTeachersHtml = '';
  if (data.top_teachers_this_week?.length > 0) {
    const rows = data.top_teachers_this_week.map((t, i) => `
      <tr>
        <td>${rankBadge(i)}</td>
        <td>${escHtml(t.teacher_name)}</td>
        <td><strong>${t.count}</strong></td>
      </tr>`).join('');
    topTeachersHtml = `
      <div class="section-card">
        <h3>🏆 ${I18N.t('top_teachers_this_week')}</h3>
        <table class="teacher-mini-table">
          <thead><tr>
            <th>#</th>
            <th>${I18N.t('teacher')}</th>
            <th>${I18N.t('duties')}</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  // Teachers without duties
  let noDutyHtml = '';
  if (data.teachers_without_duties_this_week?.length > 0) {
    const chips = data.teachers_without_duties_this_week
      .map(t => `<span class="no-duty-chip">${escHtml(t.teacher_name)}</span>`)
      .join('');
    noDutyHtml = `
      <div class="section-card">
        <h3>📋 ${I18N.t('teachers_no_duties_list')}</h3>
        <p style="font-size:0.82rem;color:var(--text-muted);margin-bottom:10px">${I18N.t('teachers_no_duties_hint')}</p>
        <div>${chips}</div>
      </div>`;
  }

  // Week sections side-by-side
  const weekSections = `
    <div class="two-col">
      ${renderWeekSection(data.current_week, I18N.t('current_week'))}
      ${renderWeekSection(data.next_week,    I18N.t('next_week'))}
    </div>`;

  // Bottom two cols
  const bottomSection = (topTeachersHtml || noDutyHtml) ? `
    <div class="two-col">
      ${topTeachersHtml || '<div></div>'}
      ${noDutyHtml      || '<div></div>'}
    </div>` : '';

  document.getElementById('dashContent').innerHTML =
    topCards + warningsHtml + weekSections + bottomSection;
}

/* ─── Load / Refresh ──────────────────────────────────────────────────────── */

async function loadDashboard() {
  const content = document.getElementById('dashContent');
  if (!content) return;

  try {
    const res = await apiFetch('/admin/dashboard');

    if (!res || !res.ok) {
      content.innerHTML = `
        <div class="dash-error">
          <div class="error-icon">⚠️</div>
          <p>${I18N.t('error_generic')}</p>
          <button class="btn btn-primary btn-sm" onclick="loadDashboard()">${I18N.t('refresh') || 'Retry'}</button>
        </div>`;
      return;
    }

    const data = await res.json();
    renderDashboard(data);
  } catch (err) {
    console.error('loadDashboard failed:', err);
    content.innerHTML = `
      <div class="dash-error">
        <div class="error-icon">⚠️</div>
        <p>${I18N.t('error_generic')}</p>
        <button class="btn btn-primary btn-sm" onclick="loadDashboard()">${I18N.t('refresh') || 'Retry'}</button>
      </div>`;
  }
}

async function refreshDashboard() {
  const btn = document.getElementById('refreshBtn');
  if (btn) btn.classList.add('spinning');

  // Show spinner in content area without wiping it entirely
  const content = document.getElementById('dashContent');
  if (content) {
    content.style.opacity = '0.5';
    content.style.pointerEvents = 'none';
  }

  await loadDashboard();

  if (content) {
    content.style.opacity = '';
    content.style.pointerEvents = '';
  }
  if (btn) btn.classList.remove('spinning');
  showToast(I18N.t('success_saved') || 'Refreshed', 'info');
}

/* ─── Auto-init ───────────────────────────────────────────────────────────── */

async function initDashboard() {
  // Ensure i18n is loaded for the right language before rendering
  await I18N.load(localStorage.getItem('firduty_lang') || 'en');
  await loadDashboard();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initDashboard);
} else {
  initDashboard();
}
