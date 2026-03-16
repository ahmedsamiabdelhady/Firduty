/**
 * dashboard.js — Admin Dashboard for Firduty v2.5
 *
 * UX improvements:
 *  - Skeleton cards shown instantly (no blank wait)
 *  - Count-up animation on all numbers
 *  - Animated bar fills
 *  - Page header with greeting + last-updated timestamp
 *  - Stat cards have icons and colour-coded left borders
 *  - Week sections: compact fill ring + day/type charts only (no redundant sub-cards)
 *  - Warnings shown prominently with action link
 *  - Top teachers as a clean leaderboard
 *  - Unassigned teachers shown as chips
 *  - Auto-refresh every 60 s silently
 */

const lang = () => I18N.getLang();
const isAr = () => lang() === 'ar';
let _dashRefreshTimer = null;
let _lastUpdated = null;

// ─── Entry point ──────────────────────────────────────────────────────────────

async function loadDashboard(silent = false) {
  if (!silent) _showSkeleton();
  try {
    const res = await apiFetch('/admin/dashboard');
    if (!res || !res.ok) { if (!silent) _showError(res?.status); return; }
    const data = await res.json();
    _lastUpdated = new Date();
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
    <div class="db-header skel-header">
      <div class="skel" style="height:22px;width:200px;margin-bottom:8px"></div>
      <div class="skel" style="height:14px;width:120px"></div>
    </div>
    <div class="dash-grid" style="margin-bottom:20px">
      ${[0,1,2,3].map(() => `
        <div class="stat-card">
          <div class="skel" style="height:14px;width:40px;margin-bottom:14px"></div>
          <div class="skel skel-val"></div>
          <div class="skel skel-lbl"></div>
        </div>`).join('')}
    </div>
    <div class="two-col">
      ${[0,1].map(() => `
        <div class="section-card">
          <div class="skel skel-title"></div>
          <div class="skel" style="height:8px;border-radius:999px;margin-bottom:18px"></div>
          ${[0,1,2,3,4].map(() => `
            <div class="bar-row">
              <div class="skel" style="height:12px;width:100px;flex-shrink:0"></div>
              <div class="skel" style="height:10px;flex:1;border-radius:999px"></div>
              <div class="skel" style="height:12px;width:20px;flex-shrink:0"></div>
            </div>`).join('')}
        </div>`).join('')}
    </div>
  `;
}

function _showError(status) {
  document.getElementById('dashContent').innerHTML = `
    <div style="text-align:center;padding:80px 0">
      <div style="font-size:3rem;margin-bottom:16px;opacity:0.4">⚠</div>
      <p style="color:var(--danger);font-weight:600;margin-bottom:8px">
        Failed to load dashboard${status ? ` (${status})` : ''}
      </p>
      <p style="color:var(--text-muted);font-size:0.88rem;margin-bottom:20px">Check your connection and try again.</p>
      <button class="btn btn-primary btn-sm" onclick="loadDashboard()">Retry</button>
    </div>`;
}

// ─── Auto-refresh ─────────────────────────────────────────────────────────────

function _scheduleRefresh() {
  clearTimeout(_dashRefreshTimer);
  _dashRefreshTimer = setTimeout(() => loadDashboard(true), 60_000);
}

// ─── Animations ───────────────────────────────────────────────────────────────

function _countUp(el, target, duration = 700) {
  if (!el || isNaN(target)) return;
  const start = performance.now();
  (function step(now) {
    const t    = Math.min((now - start) / duration, 1);
    const ease = 1 - Math.pow(1 - t, 3);
    el.textContent = Math.round(target * ease);
    if (t < 1) requestAnimationFrame(step);
  })(performance.now());
}

function _animateAll(root) {
  root.querySelectorAll('[data-count]').forEach(el =>
    _countUp(el, parseInt(el.dataset.count, 10))
  );
  requestAnimationFrame(() => {
    root.querySelectorAll('[data-target-width]').forEach(el => {
      el.style.width = el.dataset.targetWidth;
    });
  });
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function _t(key, fallback = '') {
  return (typeof I18N !== 'undefined' ? I18N.t(key) : '') || fallback;
}

function statusPill(status) {
  if (!status) return `<span class="status-pill none">${_t('no_week_plan','No plan')}</span>`;
  return `<span class="status-pill ${status}">${_t(status, status)}</span>`;
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

function _dayLabel(dateStr) {
  try {
    const d = new Date(dateStr + 'T12:00:00');
    const keys = ['day_sun','day_mon','day_tue','day_wed','day_thu','day_fri','day_sat'];
    return _t(keys[d.getDay()], dateStr);
  } catch { return dateStr; }
}

function _fillColour(pct) {
  return pct === 100 ? 'var(--primary)' : pct >= 60 ? 'var(--warning)' : 'var(--danger)';
}

function _timeAgo(date) {
  if (!date) return '';
  const s = Math.round((Date.now() - date) / 1000);
  if (s < 10)  return isAr() ? 'الآن'           : 'just now';
  if (s < 60)  return isAr() ? `منذ ${s} ث`     : `${s}s ago`;
  const m = Math.round(s / 60);
  return isAr() ? `منذ ${m} د` : `${m}m ago`;
}

// ─── Page header ──────────────────────────────────────────────────────────────

function _renderHeader() {
  const hour = new Date().getHours();
  const greeting = isAr()
    ? (hour < 12 ? 'صباح الخير' : hour < 17 ? 'مساء الخير' : 'مساء الخير')
    : (hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening');

  const updatedStr = _lastUpdated ? _timeAgo(_lastUpdated) : '';

  return `
    <div class="db-header">
      <div>
        <h2 class="db-greeting">${greeting}</h2>
        <p class="db-subtitle">${isAr() ? 'لوحة التحكم — نظام المناوبات' : 'Duty Roster — Admin Dashboard'}</p>
      </div>
      ${updatedStr ? `<span class="db-updated">${isAr() ? 'تحديث ' : 'Updated '}${updatedStr}</span>` : ''}
    </div>`;
}

// ─── Week section ─────────────────────────────────────────────────────────────

function renderWeekSection(stats, label) {
  if (!stats) {
    return `
      <div class="section-card db-week-empty">
        <span class="db-week-empty-icon">📭</span>
        <p class="db-week-empty-label">${label}</p>
        <p class="db-week-empty-hint">${_t('no_week_plan','No plan for this week')}</p>
        <a href="planner.html" class="btn btn-primary btn-sm" style="margin-top:12px">
          ${_t('create_week','Create Week')}
        </a>
      </div>`;
  }

  const maxTeacher = stats.teacher_counts.length > 0 ? stats.teacher_counts[0].count : 1;
  const maxDay     = Math.max(...Object.values(stats.duties_per_day), 1);
  const morningCount = stats.duties_per_type?.morning_endofday || 0;
  const breakCount   = stats.duties_per_type?.break || 0;
  const maxType      = Math.max(morningCount, breakCount, 1);

  const teacherBars = stats.teacher_counts.slice(0, 6).map(t =>
    barRow(t.teacher_name, t.count, maxTeacher)
  ).join('');

  const dayBars = Object.entries(stats.duties_per_day).map(([d, c]) =>
    barRow(_dayLabel(d), c, maxDay)
  ).join('');

  const fillPct = stats.total_slots > 0
    ? Math.round((stats.assigned_slots / stats.total_slots) * 100) : 0;
  const colour = _fillColour(fillPct);

  return `
    <div class="section-card">
      <div class="db-week-head">
        <div class="db-week-title">
          ${label}
          ${statusPill(stats.status)}
        </div>
        <span class="week-fill-pct" style="color:${colour}" data-count="${fillPct}">0</span>%
      </div>

      <div class="week-fill-ring" style="margin-bottom:18px">
        <div class="week-fill-ring-bar">
          <div class="week-fill-ring-fill" style="background:${colour}" data-target-width="${fillPct}%"></div>
        </div>
        <span style="font-size:0.75rem;color:var(--text-muted);white-space:nowrap">
          ${stats.assigned_slots}/${stats.total_slots} ${_t('assigned_slots','assigned')}
        </span>
      </div>

      <div class="two-col" style="margin-bottom:0">
        <div>
          <p class="chart-label">${_t('duties_per_day','By Day')}</p>
          ${dayBars || `<p style="color:var(--text-muted);font-size:0.85rem">—</p>`}
        </div>
        <div>
          <p class="chart-label">${_t('duties_by_type','By Type')}</p>
          ${barRow(_t('morning_endofday','Morning/End'), morningCount, maxType)}
          ${barRow(_t('break_duty','Break'), breakCount, maxType, 'break-type')}

          ${stats.teacher_counts.length > 0 ? `
            <p class="chart-label" style="margin-top:16px">${_t('duties_per_teacher','By Teacher')}</p>
            ${teacherBars}
            ${stats.teacher_counts.length > 6
              ? `<p style="font-size:0.78rem;color:var(--text-muted);margin-top:4px">+${stats.teacher_counts.length - 6} ${_t('more','more')}</p>`
              : ''}
          ` : ''}
        </div>
      </div>
    </div>`;
}

// ─── Main render ──────────────────────────────────────────────────────────────

function renderDashboard(data) {
  const cur = data.current_week;
  const nxt = data.next_week;

  // ── Stat cards ─────────────────────────────────────────────────────────────
  const curFill = cur && cur.total_slots > 0
    ? Math.round((cur.assigned_slots / cur.total_slots) * 100) : null;

  const statCards = [
    { icon:'👩‍🏫', value: data.total_active_teachers, label: _t('active_teachers','Active Teachers'), cls: '' },
    { icon:'📍', value: data.total_locations,       label: _t('total_locations','Locations'),       cls: '' },
    { icon:'⏰', value: data.total_shifts,           label: _t('total_shifts','Shift Types'),        cls: '' },
    curFill !== null
      ? { icon:'📋', value: curFill, label: _t('assigned_slots','Fill Rate') + ' %',
          cls: curFill === 100 ? 'green' : curFill >= 60 ? 'orange' : 'red' }
      : null,
    data.teachers_without_duties_this_week.length > 0
      ? { icon:'⚠', value: data.teachers_without_duties_this_week.length,
          label: _t('teachers_no_duties','No Duties'), cls: 'orange' }
      : null,
    data.pending_teachers_count > 0
      ? { icon:'⏳', value: data.pending_teachers_count,
          label: _t('tab_pending','Pending Approval'), cls: 'orange',
          link: 'teachers.html' }
      : null,
  ].filter(Boolean);

  const topCardsHtml = `
    <div class="dash-grid" style="margin-bottom:20px">
      ${statCards.map(c => `
        <div class="stat-card ${c.cls}"${c.link ? ` style="cursor:pointer" onclick="location.href='${c.link}'"` : ''}>
          <span class="stat-icon">${c.icon}</span>
          <div class="stat-value" data-count="${c.value}">0</div>
          <div class="stat-label">${c.label}</div>
        </div>`).join('')}
    </div>`;

  // ── Warnings ───────────────────────────────────────────────────────────────
  const warningsHtml = data.warnings.length > 0 ? `
    <div class="section-card warn-card" style="margin-bottom:20px">
      <h3 class="section-title" style="margin-bottom:12px">⚠ ${_t('warnings','Warnings')}</h3>
      <ul class="warn-list">${data.warnings.map(w => `<li>${w}</li>`).join('')}</ul>
    </div>` : '';

  // ── Week sections ──────────────────────────────────────────────────────────
  const weekHtml = `
    <div class="two-col" style="margin-bottom:20px">
      ${renderWeekSection(cur, _t('current_week','Current Week'))}
      ${renderWeekSection(nxt, _t('next_week','Next Week (Draft)'))}
    </div>`;

  // ── Bottom row: leaderboard + no-duty chips ────────────────────────────────
  const topTeachersHtml = data.top_teachers_this_week.length > 0 ? `
    <div class="section-card">
      <h3 class="section-title">🏆 ${_t('top_teachers_this_week','Most Active This Week')}</h3>
      <table class="teacher-table">
        <thead><tr>
          <th>#</th>
          <th>${_t('teacher','Teacher')}</th>
          <th>${_t('duties','Duties')}</th>
        </tr></thead>
        <tbody>
          ${data.top_teachers_this_week.map((t, i) => `
            <tr>
              <td>${rankBadge(i)}</td>
              <td><strong>${t.teacher_name}</strong></td>
              <td><span style="font-weight:700;color:var(--nav)" data-count="${t.count}">${t.count}</span></td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>` : '';

  const noDutyHtml = data.teachers_without_duties_this_week.length > 0 ? `
    <div class="section-card">
      <h3 class="section-title">📋 ${_t('teachers_no_duties_list','No Duties This Week')}</h3>
      <p style="font-size:0.84rem;color:var(--text-muted);margin-bottom:12px">
        ${_t('teachers_no_duties_hint','Consider assigning these teachers.')}
      </p>
      <div>
        ${data.teachers_without_duties_this_week
          .map(t => `<span class="no-duty-chip">${t.teacher_name}</span>`).join('')}
      </div>
    </div>` : '';

  const bottomHtml = (topTeachersHtml || noDutyHtml) ? `
    <div class="two-col">
      ${topTeachersHtml || '<div></div>'}
      ${noDutyHtml || '<div></div>'}
    </div>` : '';

  // ── Compose ────────────────────────────────────────────────────────────────
  document.getElementById('dashContent').innerHTML =
    _renderHeader() + topCardsHtml + warningsHtml + weekHtml + bottomHtml;

  const root = document.getElementById('dashContent');
  _animateAll(root);
}