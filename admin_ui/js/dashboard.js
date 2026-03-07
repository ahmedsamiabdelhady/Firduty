/**
 * dashboard.js — Admin Dashboard for Firduty
 * Loads /admin/dashboard and renders stats, charts, and warnings.
 */

const API_BASE = localStorage.getItem('firduty_api') || 'https://naval-donnamarie-firduty-6e288803.koyeb.app/';
const TOKEN = () => localStorage.getItem('firduty_token');
const lang = () => I18N.getLang();

function authHeaders() {
  return { 'Content-Type': 'application/json', 'Authorization': `Bearer ${TOKEN()}` };
}
function logout() {
  localStorage.removeItem('firduty_token');
  window.location.href = 'login.html';
}

async function loadDashboard() {
  const res = await fetch(`${API_BASE}admin/dashboard`, { headers: authHeaders() });
  if (res.status === 401) { logout(); return; }
  if (!res.ok) {
    document.getElementById('dashContent').innerHTML =
      `<p style="color:red;text-align:center">Error loading dashboard (${res.status})</p>`;
    return;
  }
  const data = await res.json();
  renderDashboard(data);
}

function statusPill(status) {
  if (!status) return `<span class="status-pill none">${I18N.t('no_week_plan')}</span>`;
  return `<span class="status-pill ${status}">${I18N.t(status)}</span>`;
}

function rankBadge(i) {
  const cls = i === 0 ? 'gold' : i === 1 ? 'silver' : i === 2 ? 'bronze' : '';
  return `<span class="rank-badge ${cls}">${i + 1}</span>`;
}

function barRow(label, count, maxCount, cssClass = '') {
  const pct = maxCount > 0 ? Math.round((count / maxCount) * 100) : 0;
  return `
    <div class="bar-row">
      <span class="bar-label" title="${label}">${label}</span>
      <div class="bar-track"><div class="bar-fill ${cssClass}" style="width:${pct}%"></div></div>
      <span class="bar-count">${count}</span>
    </div>`;
}

function renderWeekSection(stats, label) {
  if (!stats) {
    return `<div class="section-card"><h3>${label}</h3>
      <p style="color:var(--text-muted)">${I18N.t('no_week_plan')}</p></div>`;
  }

  const maxTeacher = stats.teacher_counts.length > 0
    ? stats.teacher_counts[0].count : 1;
  const maxDay = Math.max(...Object.values(stats.duties_per_day), 1);

  const teacherBars = stats.teacher_counts.slice(0, 8).map(t =>
    barRow(t.teacher_name, t.count, maxTeacher)
  ).join('');

  const dayBars = Object.entries(stats.duties_per_day).map(([d, c]) =>
    barRow(d, c, maxDay)
  ).join('');

  const morningCount = stats.duties_per_type.morning_endofday || 0;
  const breakCount   = stats.duties_per_type.break || 0;
  const maxType      = Math.max(morningCount, breakCount, 1);

  return `
    <div class="section-card">
      <h3>${label} — ${statusPill(stats.status)} <small style="color:var(--text-muted);font-weight:400"> v${stats.version}</small></h3>

      <div class="dash-grid" style="margin-bottom:16px">
        <div class="stat-card">
          <div class="stat-value">${stats.total_slots}</div>
          <div class="stat-label">${I18N.t('total_slots')}</div>
        </div>
        <div class="stat-card green">
          <div class="stat-value">${stats.assigned_slots}</div>
          <div class="stat-label">${I18N.t('assigned_slots')}</div>
        </div>
        <div class="stat-card ${stats.unassigned_slots > 0 ? 'orange' : 'green'}">
          <div class="stat-value">${stats.unassigned_slots}</div>
          <div class="stat-label">${I18N.t('unassigned_slots')}</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${stats.teachers_assigned_count}</div>
          <div class="stat-label">${I18N.t('teachers_on_duty')}</div>
        </div>
      </div>

      <div class="two-col">
        <div>
          <h4 style="font-size:0.88rem;color:var(--text-muted);margin-bottom:10px">${I18N.t('duties_per_day')}</h4>
          ${dayBars || '<p style="color:var(--text-muted);font-size:0.85rem">—</p>'}
        </div>
        <div>
          <h4 style="font-size:0.88rem;color:var(--text-muted);margin-bottom:10px">${I18N.t('duties_by_type')}</h4>
          ${barRow(I18N.t('morning_endofday'), morningCount, maxType, '')}
          ${barRow(I18N.t('break_duty'), breakCount, maxType, 'break-type')}
        </div>
      </div>

      ${stats.teacher_counts.length > 0 ? `
      <h4 style="font-size:0.88rem;color:var(--text-muted);margin:14px 0 10px">${I18N.t('duties_per_teacher')}</h4>
      ${teacherBars}
      ${stats.teacher_counts.length > 8 ? `<p style="font-size:0.8rem;color:var(--text-muted)">+${stats.teacher_counts.length - 8} ${I18N.t('more')}</p>` : ''}
      ` : ''}
    </div>`;
}

function renderDashboard(data) {
  const isAr = lang() === 'ar';
  const curLabel = I18N.t('current_week');
  const nxtLabel = I18N.t('next_week');

  // Top stat cards
  const topCards = `
    <div class="dash-grid">
      <div class="stat-card">
        <div class="stat-value">${data.total_active_teachers}</div>
        <div class="stat-label">${I18N.t('active_teachers')}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${data.total_locations}</div>
        <div class="stat-label">${I18N.t('total_locations')}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value">${data.total_shifts}</div>
        <div class="stat-label">${I18N.t('total_shifts')}</div>
      </div>
      <div class="stat-card ${data.teachers_without_duties_this_week.length > 0 ? 'orange' : 'green'}">
        <div class="stat-value">${data.teachers_without_duties_this_week.length}</div>
        <div class="stat-label">${I18N.t('teachers_no_duties')}</div>
      </div>
    </div>`;

  // Warnings
  let warningsHtml = '';
  if (data.warnings.length > 0) {
    const items = data.warnings.map(w => `<li>${w}</li>`).join('');
    warningsHtml = `<div class="section-card">
      <h3>⚠️ ${I18N.t('warnings')}</h3>
      <ul class="warn-list">${items}</ul>
    </div>`;
  }

  // Top teachers
  let topTeachersHtml = '';
  if (data.top_teachers_this_week.length > 0) {
    const rows = data.top_teachers_this_week.map((t, i) => `
      <tr>
        <td>${rankBadge(i)}</td>
        <td>${t.teacher_name}</td>
        <td><strong>${t.count}</strong></td>
      </tr>`).join('');
    topTeachersHtml = `<div class="section-card">
      <h3>🏆 ${I18N.t('top_teachers_this_week')}</h3>
      <table class="teacher-table">
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
  if (data.teachers_without_duties_this_week.length > 0) {
    const chips = data.teachers_without_duties_this_week
      .map(t => `<span class="no-duty-chip">${t.teacher_name}</span>`).join('');
    noDutyHtml = `<div class="section-card">
      <h3>📋 ${I18N.t('teachers_no_duties_list')}</h3>
      <p style="font-size:0.85rem;color:var(--text-muted);margin-bottom:10px">${I18N.t('teachers_no_duties_hint')}</p>
      <div>${chips}</div>
    </div>`;
  }

  document.getElementById('dashContent').innerHTML = `
    ${topCards}
    ${warningsHtml}
    <div class="two-col">
      ${renderWeekSection(data.current_week, curLabel)}
      ${renderWeekSection(data.next_week, nxtLabel)}
    </div>
    <div class="two-col">
      ${topTeachersHtml}
      ${noDutyHtml}
    </div>
  `;
}