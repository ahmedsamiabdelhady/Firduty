/**
 * dashboard.js — Admin Dashboard for Firduty
 *
 * UX improvements (v2.4):
 *  • Shows skeleton stat cards instantly — no blank wait
 *  • Numbers animate with a count-up on first render
 *  • Warnings render as soon as data arrives (no all-or-nothing)
 *  • Auto-refresh every 60 s (silent background refresh)
 *  • Pull-to-refresh button in header
 */

const lang = () => I18N.getLang();
let _dashRefreshTimer = null;

// ─── Entry point ──────────────────────────────────────────────────────────────

async function loadDashboard(silent = false) {
  if (!silent) _showSkeleton();

  try {
    const res = await apiFetch('/admin/dashboard');
    if (!res || !res.ok) {
      if (!silent) _showError(res?.status);
      return;
    }
    const data = await res.json();
    renderDashboard(data);
    _scheduleRefresh();
  } catch (err) {
    if (!silent) _showError();
    console.error('[dashboard] load failed:', err);
  }
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function _showSkeleton() {
  document.getElementById('dashContent').innerHTML = `
    <div class="dash-grid" style="margin-bottom:20px">
      ${[0,1,2,3].map(() => `
        <div class="stat-card">
          <div class="skel skel-val"></div>
          <div class="skel skel-lbl"></div>
        </div>`).join('')}
    </div>
    <div class="dash-grid" style="margin-bottom:20px">
      ${[0,1].map(() => `
        <div class="section-card">
          <div class="skel skel-title"></div>
          ${[0,1,2,3].map(() => `<div class="skel skel-row"></div>`).join('')}
        </div>`).join('')}
    </div>
  `;
}

function _showError(status) {
  document.getElementById('dashContent').innerHTML = `
    <div style="text-align:center;padding:60px 0">
      <div style="font-size:2.5rem;margin-bottom:12px">⚠️</div>
      <p style="color:var(--danger);margin-bottom:16px">
        Error loading dashboard${status ? ` (${status})` : ''}.
      </p>
      <button class="btn btn-primary btn-sm" onclick="loadDashboard()">Retry</button>
    </div>`;
}

// ─── Auto-refresh ─────────────────────────────────────────────────────────────

function _scheduleRefresh() {
  clearTimeout(_dashRefreshTimer);
  _dashRefreshTimer = setTimeout(() => loadDashboard(true), 60_000);
}

// ─── Count-up animation ───────────────────────────────────────────────────────

function _countUp(el, target, duration = 600) {
  if (!el || isNaN(target)) return;
  const start = performance.now();
  const from  = 0;
  function step(now) {
    const t = Math.min((now - start) / duration, 1);
    const ease = 1 - Math.pow(1 - t, 3); // cubic ease-out
    el.textContent = Math.round(from + (target - from) * ease);
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

function _animateAllCounters(root = document) {
  root.querySelectorAll('[data-count]').forEach(el => {
    const target = parseInt(el.dataset.count, 10);
    _countUp(el, target);
  });
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

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
      <div class="bar-track">
        <div class="bar-fill ${cssClass}" style="width:0%" data-target-width="${pct}%"></div>
      </div>
      <span class="bar-count">${count}</span>
    </div>`;
}

function _animateBars(root = document) {
  // Small delay so CSS transitions play after paint
  requestAnimationFrame(() => {
    root.querySelectorAll('[data-target-width]').forEach(el => {
      el.style.width = el.dataset.targetWidth;
    });
  });
}

// ─── Week section ─────────────────────────────────────────────────────────────

function renderWeekSection(stats, label) {
  if (!stats) {
    return `
      <div class="section-card">
        <h3 class="section-title">${label}</h3>
        <p style="color:var(--text-muted);margin-top:8px">${I18N.t('no_week_plan')}</p>
      </div>`;
  }

  const maxTeacher = stats.teacher_counts.length > 0 ? stats.teacher_counts[0].count : 1;
  const maxDay     = Math.max(...Object.values(stats.duties_per_day), 1);

  const teacherBars = stats.teacher_counts.slice(0, 8).map(t =>
    barRow(t.teacher_name, t.count, maxTeacher)
  ).join('');

  const dayBars = Object.entries(stats.duties_per_day).map(([d, c]) => {
    const label = _dayLabel(d);
    return barRow(label, c, maxDay);
  }).join('');

  const morningCount = stats.duties_per_type.morning_endofday || 0;
  const breakCount   = stats.duties_per_type.break || 0;
  const maxType      = Math.max(morningCount, breakCount, 1);

  const fillPct = stats.total_slots > 0
    ? Math.round((stats.assigned_slots / stats.total_slots) * 100) : 0;
  const fillColour = fillPct === 100 ? 'var(--primary)' : fillPct > 60 ? 'var(--warning)' : 'var(--danger)';

  return `
    <div class="section-card">
      <div style="display:flex;align-items:center;justify-content:space-between;gap:10px;flex-wrap:wrap;margin-bottom:14px">
        <h3 class="section-title" style="margin:0">${label} ${statusPill(stats.status)} <small style="color:var(--text-muted);font-weight:400">v${stats.version}</small></h3>
        <div style="font-size:0.8rem;color:var(--text-muted)">
          <span style="font-weight:700;color:${fillColour}">${fillPct}%</span> filled
        </div>
      </div>

      <!-- Mini progress bar -->
      <div style="height:5px;background:var(--border);border-radius:999px;margin-bottom:16px;overflow:hidden">
        <div style="height:100%;border-radius:999px;background:${fillColour};width:0%;transition:width 0.6s ease" data-target-width="${fillPct}%"></div>
      </div>

      <div class="dash-grid dash-grid-4" style="margin-bottom:16px">
        <div class="stat-card stat-card-sm">
          <div class="stat-value" data-count="${stats.total_slots}">${stats.total_slots}</div>
          <div class="stat-label">${I18N.t('total_slots')}</div>
        </div>
        <div class="stat-card stat-card-sm green">
          <div class="stat-value" data-count="${stats.assigned_slots}">${stats.assigned_slots}</div>
          <div class="stat-label">${I18N.t('assigned_slots')}</div>
        </div>
        <div class="stat-card stat-card-sm ${stats.unassigned_slots > 0 ? 'orange' : 'green'}">
          <div class="stat-value" data-count="${stats.unassigned_slots}">${stats.unassigned_slots}</div>
          <div class="stat-label">${I18N.t('unassigned_slots')}</div>
        </div>
        <div class="stat-card stat-card-sm">
          <div class="stat-value" data-count="${stats.teachers_assigned_count}">${stats.teachers_assigned_count}</div>
          <div class="stat-label">${I18N.t('teachers_on_duty')}</div>
        </div>
      </div>

      <div class="two-col">
        <div>
          <h4 class="chart-label">${I18N.t('duties_per_day')}</h4>
          ${dayBars || '<p style="color:var(--text-muted);font-size:0.85rem">—</p>'}
        </div>
        <div>
          <h4 class="chart-label">${I18N.t('duties_by_type')}</h4>
          ${barRow(I18N.t('morning_endofday'), morningCount, maxType)}
          ${barRow(I18N.t('break_duty'), breakCount, maxType, 'break-type')}
        </div>
      </div>

      ${stats.teacher_counts.length > 0 ? `
        <h4 class="chart-label" style="margin-top:14px">${I18N.t('duties_per_teacher')}</h4>
        ${teacherBars}
        ${stats.teacher_counts.length > 8
          ? `<p style="font-size:0.8rem;color:var(--text-muted);margin-top:4px">+${stats.teacher_counts.length - 8} ${I18N.t('more')}</p>`
          : ''}
      ` : ''}
    </div>`;
}

// Convert YYYY-MM-DD date string to short day name
function _dayLabel(dateStr) {
  try {
    const d = new Date(dateStr + 'T12:00:00');
    const keys = ['day_sun','day_mon','day_tue','day_wed','day_thu','day_fri','day_sat'];
    return I18N.t(keys[d.getDay()]) || dateStr;
  } catch { return dateStr; }
}

// ─── Main render ──────────────────────────────────────────────────────────────

function renderDashboard(data) {
  const curLabel = I18N.t('current_week');
  const nxtLabel = I18N.t('next_week');

  // ── Top stat cards ─────────────────────────────────────────────────────────
  const noPending = (data.pending_teachers_count || 0) === 0;
  const topCards = `
    <div class="dash-grid">
      <div class="stat-card">
        <div class="stat-value" data-count="${data.total_active_teachers}">0</div>
        <div class="stat-label">${I18N.t('active_teachers')}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" data-count="${data.total_locations}">0</div>
        <div class="stat-label">${I18N.t('total_locations')}</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" data-count="${data.total_shifts}">0</div>
        <div class="stat-label">${I18N.t('total_shifts')}</div>
      </div>
      <div class="stat-card ${data.teachers_without_duties_this_week.length > 0 ? 'orange' : 'green'}">
        <div class="stat-value" data-count="${data.teachers_without_duties_this_week.length}">0</div>
        <div class="stat-label">${I18N.t('teachers_no_duties')}</div>
      </div>
      ${data.pending_teachers_count > 0 ? `
      <div class="stat-card orange" style="cursor:pointer" onclick="window.location.href='teachers.html'">
        <div class="stat-value" data-count="${data.pending_teachers_count}">0</div>
        <div class="stat-label">⏳ ${I18N.t('tab_pending') || 'Pending Approval'}</div>
      </div>` : ''}
    </div>`;

  // ── Warnings ───────────────────────────────────────────────────────────────
  let warningsHtml = '';
  if (data.warnings.length > 0) {
    const items = data.warnings.map(w => `<li>${w}</li>`).join('');
    warningsHtml = `
      <div class="section-card warn-card">
        <h3>⚠️ ${I18N.t('warnings')}</h3>
        <ul class="warn-list">${items}</ul>
      </div>`;
  }

  // ── Top teachers ───────────────────────────────────────────────────────────
  let topTeachersHtml = '';
  if (data.top_teachers_this_week.length > 0) {
    const rows = data.top_teachers_this_week.map((t, i) => `
      <tr>
        <td>${rankBadge(i)}</td>
        <td>${t.teacher_name}</td>
        <td><strong data-count="${t.count}">${t.count}</strong></td>
      </tr>`).join('');
    topTeachersHtml = `
      <div class="section-card">
        <h3 class="section-title">🏆 ${I18N.t('top_teachers_this_week')}</h3>
        <table class="teacher-table" style="margin-top:10px">
          <thead><tr>
            <th>#</th>
            <th>${I18N.t('teacher')}</th>
            <th>${I18N.t('duties')}</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  }

  // ── No-duty teachers ───────────────────────────────────────────────────────
  let noDutyHtml = '';
  if (data.teachers_without_duties_this_week.length > 0) {
    const chips = data.teachers_without_duties_this_week
      .map(t => `<span class="no-duty-chip">${t.teacher_name}</span>`).join('');
    noDutyHtml = `
      <div class="section-card">
        <h3 class="section-title">📋 ${I18N.t('teachers_no_duties_list')}</h3>
        <p style="font-size:0.85rem;color:var(--text-muted);margin-bottom:10px">${I18N.t('teachers_no_duties_hint')}</p>
        <div>${chips}</div>
      </div>`;
  }

  // ── Compose ────────────────────────────────────────────────────────────────
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

  // Animate after DOM is in place
  const root = document.getElementById('dashContent');
  _animateAllCounters(root);
  _animateBars(root);
}