/**
 * dashboard.js — Admin Dashboard for Firduty v2.5
 * Renders all 8 insight groups returned by GET /admin/dashboard
 */

const lang = () => I18N.getLang();
const isAr = () => lang() === 'ar';
let _dashRefreshTimer = null;
let _lastUpdated = null;

// ─── Entry ────────────────────────────────────────────────────────────────────

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
    console.error('[dashboard]', err);
  }
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function _showSkeleton() {
  document.getElementById('dashContent').innerHTML = `
    <div class="db-header skel-header">
      <div><div class="skel" style="height:22px;width:220px;margin-bottom:8px"></div>
      <div class="skel" style="height:14px;width:140px"></div></div>
    </div>
    <div class="dash-grid" style="margin-bottom:20px">
      ${[0,1,2,3].map(() => `<div class="stat-card">
        <div class="skel" style="height:14px;width:36px;margin-bottom:12px"></div>
        <div class="skel skel-val"></div><div class="skel skel-lbl"></div>
      </div>`).join('')}
    </div>
    <div class="two-col">
      ${[0,1].map(() => `<div class="section-card">
        <div class="skel skel-title"></div>
        ${[0,1,2,3,4].map(() => `<div class="skel" style="height:10px;border-radius:999px;margin-bottom:10px"></div>`).join('')}
      </div>`).join('')}
    </div>`;
}

function _showError(status) {
  document.getElementById('dashContent').innerHTML = `
    <div style="text-align:center;padding:80px 0">
      <div style="font-size:3rem;margin-bottom:16px;opacity:0.35">⚠</div>
      <p style="color:var(--danger);font-weight:600;margin-bottom:8px">
        Failed to load dashboard${status ? ` (${status})` : ''}</p>
      <p style="color:var(--text-muted);font-size:0.88rem;margin-bottom:20px">
        Check your connection and try again.</p>
      <button class="btn btn-primary btn-sm" onclick="loadDashboard()">Retry</button>
    </div>`;
}

function _scheduleRefresh() {
  clearTimeout(_dashRefreshTimer);
  _dashRefreshTimer = setTimeout(() => loadDashboard(true), 60_000);
}

// ─── Animations ───────────────────────────────────────────────────────────────

function _countUp(el, target, duration = 700) {
  if (!el || isNaN(target)) return;
  const start = performance.now();
  (function step(now) {
    const t = Math.min((now - start) / duration, 1);
    el.textContent = Math.round(target * (1 - Math.pow(1 - t, 3)));
    if (t < 1) requestAnimationFrame(step);
  })(performance.now());
}

function _animateAll(root) {
  root.querySelectorAll('[data-count]').forEach(el =>
    _countUp(el, parseInt(el.dataset.count, 10)));
  requestAnimationFrame(() =>
    root.querySelectorAll('[data-tw]').forEach(el => { el.style.width = el.dataset.tw; }));
}

// ─── Tiny helpers ─────────────────────────────────────────────────────────────

function _t(k, fb = '') { return (typeof I18N !== 'undefined' ? I18N.t(k) : '') || fb; }

function statusPill(s) {
  if (!s) return `<span class="status-pill none">${_t('no_week_plan','No plan')}</span>`;
  return `<span class="status-pill ${s}">${_t(s, s)}</span>`;
}

function _fill(pct) {
  return pct >= 100 ? 'var(--primary)' : pct >= 60 ? 'var(--warning)' : 'var(--danger)';
}

function barRow(label, count, max, cls = '') {
  const pct = max > 0 ? Math.round(count / max * 100) : 0;
  return `<div class="bar-row">
    <span class="bar-label" title="${label}">${label}</span>
    <div class="bar-track"><div class="bar-fill ${cls}" style="width:0%" data-tw="${pct}%"></div></div>
    <span class="bar-count">${count}</span>
  </div>`;
}

function rankBadge(i) {
  const cls = ['gold','silver','bronze'][i] || '';
  return `<span class="rank-badge ${cls}">${i + 1}</span>`;
}

function _dayName(d) { return _t(d.day_key, d.day_name); }

function _greeting() {
  const h = new Date().getHours();
  if (isAr()) return h < 12 ? 'صباح الخير' : 'مساء الخير';
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

function _timeAgo(d) {
  const s = Math.round((Date.now() - d) / 1000);
  if (s < 10) return isAr() ? 'الآن' : 'just now';
  if (s < 60) return isAr() ? `منذ ${s}ث` : `${s}s ago`;
  return isAr() ? `منذ ${Math.round(s/60)}د` : `${Math.round(s/60)}m ago`;
}

// ─── Section builders ────────────────────────────────────────────────────────

function _header() {
  const updated = _lastUpdated ? `<span class="db-updated">${isAr()?'تحديث ':'Updated '}${_timeAgo(_lastUpdated)}</span>` : '';
  return `<div class="db-header">
    <div>
      <h2 class="db-greeting">${_greeting()}</h2>
      <p class="db-subtitle">${isAr() ? 'لوحة التحكم — نظام المناوبات' : 'Duty Roster — Admin Dashboard'}</p>
    </div>
    ${updated}
  </div>`;
}

// 1 — Top stat cards
function _statCards(data) {
  const cards = [
    { v: data.total_active_teachers, label: _t('active_teachers','Active Teachers'), icon: '👩‍🏫', cls: '' },
    { v: data.total_locations,       label: _t('total_locations','Locations'),       icon: '📍', cls: '' },
    { v: data.total_shifts,          label: _t('total_shifts','Shift Types'),        icon: '⏰', cls: '' },
    data.pending_teachers_count > 0
      ? { v: data.pending_teachers_count, label: _t('tab_pending','Pending Approval'), icon: '⏳', cls: 'orange', link: 'teachers.html' }
      : null,
  ].filter(Boolean);

  return `<div class="dash-grid" style="margin-bottom:20px">
    ${cards.map(c => `
      <div class="stat-card ${c.cls}"${c.link ? ` style="cursor:pointer" onclick="location.href='${c.link}'"` : ''}>
        <span class="stat-icon">${c.icon}</span>
        <div class="stat-value" data-count="${c.v}">0</div>
        <div class="stat-label">${c.label}</div>
      </div>`).join('')}
  </div>`;
}

// 2 — Today's live status
function _todayCard(today) {
  if (!today) return `<div class="section-card db-today-empty">
    <p style="color:var(--text-muted);font-size:0.88rem">${isAr() ? 'لا توجد مناوبات اليوم' : 'No duties scheduled for today'}</p>
  </div>`;

  const colour = _fill(today.confirm_rate);
  const pubBadge = today.published
    ? `<span class="status-pill published">${_t('published','Published')}</span>`
    : `<span class="status-pill draft">${_t('draft','Unpublished')}</span>`;

  return `<div class="section-card db-today-card">
    <div class="db-today-head">
      <div>
        <span class="db-today-label">${isAr() ? 'اليوم' : 'Today'}</span>
        <span class="db-today-date">${today.date}</span>
      </div>
      ${pubBadge}
    </div>
    <div class="db-today-stats">
      <div class="db-today-stat">
        <span class="db-today-num" data-count="${today.assigned}">${today.assigned}</span>
        <span class="db-today-lbl">${isAr() ? 'مُعيَّن' : 'Assigned'}</span>
      </div>
      <div class="db-today-stat">
        <span class="db-today-num" data-count="${today.empty}" style="color:${today.empty > 0 ? 'var(--danger)' : 'var(--primary)'}">${today.empty}</span>
        <span class="db-today-lbl">${isAr() ? 'فارغ' : 'Empty'}</span>
      </div>
      <div class="db-today-stat">
        <span class="db-today-num" style="color:${colour}" data-count="${today.confirmed}">${today.confirmed}</span>
        <span class="db-today-lbl">${isAr() ? 'أكَّد' : 'Confirmed'}</span>
      </div>
      <div class="db-today-stat">
        <span class="db-today-num" style="color:${colour}" data-count="${today.confirm_rate}">${today.confirm_rate}</span>
        <span class="db-today-lbl">${isAr() ? 'نسبة التأكيد %' : 'Confirm Rate %'}</span>
      </div>
    </div>
    <div class="week-fill-ring" style="margin-top:12px;margin-bottom:0">
      <div class="week-fill-ring-bar">
        <div class="week-fill-ring-fill" style="background:${colour};width:0%" data-tw="${today.confirm_rate}%"></div>
      </div>
    </div>
  </div>`;
}

// 3 — Per-day slot grid (THIS WEEK)
function _weekDaysGrid(days, title, weekStatus, weekVersion) {
  if (!days || !days.length) return `<div class="section-card">
    <h3 class="section-title">${title}</h3>
    <p style="color:var(--text-muted);margin-top:8px">${_t('no_week_plan','No plan')}</p>
    <a href="planner.html" class="btn btn-primary btn-sm" style="margin-top:12px">${_t('create_week','Create Week')}</a>
  </div>`;

  const totalAssigned = days.reduce((s, d) => s + d.assigned, 0);
  const totalSlots    = days.reduce((s, d) => s + d.total, 0);
  const overallPct    = totalSlots > 0 ? Math.round(totalAssigned / totalSlots * 100) : 0;
  const colour        = _fill(overallPct);

  const dayCells = days.map(d => {
    const pct    = d.total > 0 ? Math.round(d.assigned / d.total * 100) : 0;
    const col    = _fill(pct);
    const isToday = d.date === new Date().toISOString().split('T')[0];
    const todayMark = isToday ? ' db-day-today' : '';

    return `<div class="db-day-cell${todayMark}">
      <div class="db-day-name">${_dayName(d)}</div>
      <div class="db-day-pub">${d.published
        ? `<span class="db-pub-dot db-pub-yes" title="${_t('published','Published')}"></span>`
        : `<span class="db-pub-dot db-pub-no" title="${_t('draft','Unpublished')}"></span>`}</div>
      <div class="db-day-ring-wrap">
        <svg viewBox="0 0 36 36" class="db-day-ring">
          <path class="db-day-ring-bg" d="M18 2.0845a15.9155 15.9155 0 0 1 0 31.831 15.9155 15.9155 0 0 1 0-31.831"/>
          <path class="db-day-ring-fill" stroke="${col}" stroke-dasharray="${pct}, 100"
            d="M18 2.0845a15.9155 15.9155 0 0 1 0 31.831 15.9155 15.9155 0 0 1 0-31.831"/>
        </svg>
        <span class="db-day-ring-pct" style="color:${col}">${pct}%</span>
      </div>
      <div class="db-day-counts">
        <span class="db-day-assigned">${d.assigned}</span>
        <span class="db-day-sep">/</span>
        <span class="db-day-total">${d.total}</span>
      </div>
      ${d.empty > 0 ? `<span class="db-day-empty-chip">${d.empty} ${isAr()?'فارغ':'empty'}</span>` : ''}
    </div>`;
  }).join('');

  return `<div class="section-card">
    <div class="db-week-head">
      <div class="db-week-title">
        ${title} ${statusPill(weekStatus)}
        ${weekVersion ? `<small style="color:var(--text-muted);font-weight:400">v${weekVersion}</small>` : ''}
      </div>
      <span class="week-fill-pct" style="color:${colour}" data-count="${overallPct}">0</span>%
    </div>
    <div class="week-fill-ring" style="margin-bottom:16px">
      <div class="week-fill-ring-bar">
        <div class="week-fill-ring-fill" style="background:${colour};width:0%" data-tw="${overallPct}%"></div>
      </div>
      <span style="font-size:0.75rem;color:var(--text-muted);white-space:nowrap">
        ${totalAssigned}/${totalSlots} ${isAr()?'مُعيَّن':'assigned'}
      </span>
    </div>
    <div class="db-days-grid">${dayCells}</div>
  </div>`;
}

// 4 — Monthly engagement
function _monthlyCard(stats, month, year) {
  if (!stats) return '';
  const col    = _fill(stats.confirmation_rate);
  const months = isAr()
    ? ['يناير','فبراير','مارس','أبريل','مايو','يونيو','يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر']
    : ['January','February','March','April','May','June','July','August','September','October','November','December'];

  const maxBreak = Math.max(stats.on_time, stats.late, stats.missed, 1);

  return `<div class="section-card">
    <h3 class="section-title">${isAr() ? 'الالتزام الشهري' : 'Monthly Engagement'} — ${months[month-1]} ${year}</h3>

    <div class="db-monthly-ring-row">
      <div class="db-rate-circle" style="--rate:${stats.confirmation_rate};--col:${col}">
        <svg viewBox="0 0 36 36">
          <path class="db-day-ring-bg" d="M18 2.0845a15.9155 15.9155 0 0 1 0 31.831 15.9155 15.9155 0 0 1 0-31.831"/>
          <path class="db-day-ring-fill" stroke="${col}" stroke-dasharray="${stats.confirmation_rate}, 100"
            d="M18 2.0845a15.9155 15.9155 0 0 1 0 31.831 15.9155 15.9155 0 0 1 0-31.831"/>
        </svg>
        <span class="db-rate-num" style="color:${col}" data-count="${stats.confirmation_rate}">0</span>%
        <span class="db-rate-lbl">${isAr()?'نسبة التأكيد':'Confirm Rate'}</span>
      </div>
      <div class="db-monthly-breakdown">
        ${barRow(isAr()?'في الوقت':'On Time',   stats.on_time,  maxBreak, '')}
        ${barRow(isAr()?'متأخر قليلاً':'Late',  stats.late,    maxBreak, 'bar-fill-warn')}
        ${barRow(isAr()?'فاتته':'Missed',        stats.missed,  maxBreak, 'bar-fill-danger')}
      </div>
    </div>

    <div class="db-monthly-counts">
      <div class="db-mc">
        <span class="db-mc-v" data-count="${stats.total_assigned}">${stats.total_assigned}</span>
        <span class="db-mc-l">${isAr()?'إجمالي المهام':'Total Duties'}</span>
      </div>
      <div class="db-mc">
        <span class="db-mc-v" data-count="${stats.confirmed}">${stats.confirmed}</span>
        <span class="db-mc-l">${isAr()?'مؤكَّدة':'Confirmed'}</span>
      </div>
      <div class="db-mc" style="${stats.missed > 0 ? 'color:var(--danger)' : ''}">
        <span class="db-mc-v" data-count="${stats.missed}">${stats.missed}</span>
        <span class="db-mc-l">${isAr()?'فائتة':'Missed'}</span>
      </div>
    </div>
  </div>`;
}

// 5 — Teacher reliability
function _reliabilityCard(list) {
  if (!list || !list.length) return '';
  const rows = list.map(t => {
    const col = t.confirm_rate >= 80 ? 'var(--primary)' : t.confirm_rate >= 50 ? 'var(--warning)' : 'var(--danger)';
    return `<tr>
      <td><strong>${t.teacher_name}</strong></td>
      <td><span style="color:${col};font-weight:700" data-count="${t.confirm_rate}">${t.confirm_rate}</span>%</td>
      <td>${t.confirmed}/${t.assigned}</td>
      ${t.unconfirmed > 0
        ? `<td><span class="db-unconf-chip">${t.unconfirmed} ${isAr()?'لم يؤكد':'unconfirmed'}</span></td>`
        : `<td><span style="color:var(--primary);font-size:0.8rem">✓ ${isAr()?'ممتاز':'Great'}</span></td>`}
    </tr>`;
  }).join('');

  return `<div class="section-card">
    <h3 class="section-title">${isAr()?'مستوى الالتزام هذا الأسبوع':'Teacher Reliability This Week'}</h3>
    <p style="font-size:0.82rem;color:var(--text-muted);margin-bottom:12px">
      ${isAr()?'من الأيام المنشورة فقط':'From published days only'}
    </p>
    <table class="teacher-table">
      <thead><tr>
        <th>${isAr()?'المعلم':'Teacher'}</th>
        <th>${isAr()?'نسبة التأكيد':'Rate'}</th>
        <th>${isAr()?'مؤكَّد/معيَّن':'Confirmed'}</th>
        <th>${isAr()?'الحالة':'Status'}</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
  </div>`;
}

// 6 — Workload balance
function _balanceCard(balance, topTeachers) {
  const teacherRows = topTeachers.map((t, i) => `
    <tr>
      <td>${rankBadge(i)}</td>
      <td><strong>${t.teacher_name}</strong></td>
      <td><span style="font-weight:700;color:var(--nav)" data-count="${t.count}">${t.count}</span></td>
    </tr>`).join('');

  const balanceHtml = balance ? `
    <div class="db-balance ${balance.fair ? 'db-balance-ok' : 'db-balance-warn'}">
      <span class="db-balance-icon">${balance.fair ? '✓' : '⚠'}</span>
      <span>${balance.fair
        ? (isAr() ? 'توزيع عادل' : 'Fair distribution')
        : (isAr()
            ? `فجوة ${balance.gap} مناوبة — ${balance.max_teacher} (${balance.max_count}) مقابل ${balance.min_teacher} (${balance.min_count})`
            : `Gap of ${balance.gap} — ${balance.max_teacher} (${balance.max_count}) vs ${balance.min_teacher} (${balance.min_count})`)
      }</span>
    </div>` : '';

  return `<div class="section-card">
    <h3 class="section-title">🏆 ${isAr()?'أكثر المعلمين نشاطاً':'Most Active This Week'}</h3>
    ${balanceHtml}
    <table class="teacher-table" style="margin-top:10px">
      <thead><tr>
        <th>#</th>
        <th>${isAr()?'المعلم':'Teacher'}</th>
        <th>${isAr()?'المناوبات':'Duties'}</th>
      </tr></thead>
      <tbody>${teacherRows}</tbody>
    </table>
  </div>`;
}

// 7 — No-duty chips (week + month)
function _noDutyCard(weekList, monthList) {
  const weekChips = weekList.map(t => `<span class="no-duty-chip">${t.teacher_name}</span>`).join('');
  const monthChips = monthList
    .filter(t => !weekList.find(w => w.teacher_id === t.teacher_id))
    .map(t => `<span class="no-duty-chip no-duty-chip-month">${t.teacher_name}</span>`).join('');

  if (!weekChips && !monthChips) return '';

  return `<div class="section-card">
    <h3 class="section-title">📋 ${isAr()?'المعلمون بدون مناوبات':'Teachers Without Duties'}</h3>
    ${weekChips ? `
      <p class="chart-label" style="margin-bottom:8px">${isAr()?'هذا الأسبوع':'This Week'}</p>
      <div style="margin-bottom:14px">${weekChips}</div>` : ''}
    ${monthChips ? `
      <p class="chart-label" style="margin-bottom:8px">${isAr()?'هذا الشهر فقط':'This Month Only'}</p>
      <div>${monthChips}</div>` : ''}
  </div>`;
}

// 8 — Warnings
function _warningsCard(warnings) {
  if (!warnings.length) return '';
  return `<div class="section-card warn-card" style="margin-bottom:20px">
    <h3 class="section-title" style="margin-bottom:10px">⚠ ${_t('warnings','Warnings')}</h3>
    <ul class="warn-list">${warnings.map(w => `<li>${w}</li>`).join('')}</ul>
  </div>`;
}

// ─── Main render ──────────────────────────────────────────────────────────────

function renderDashboard(data) {
  const root = document.getElementById('dashContent');

  root.innerHTML =
    _header() +
    _statCards(data) +
    _warningsCard(data.warnings) +

    // Row 1: Today + monthly engagement
    `<div class="two-col" style="margin-bottom:16px">
      ${_todayCard(data.today)}
      ${_monthlyCard(data.monthly_stats, data.month, data.year)}
    </div>` +

    // Row 2: Current week days + next week days
    `<div class="two-col" style="margin-bottom:16px">
      ${_weekDaysGrid(data.current_week_days, _t('current_week','Current Week'),
                      data.current_week_status, data.current_week_version)}
      ${_weekDaysGrid(data.next_week_days, _t('next_week','Next Week (Draft)'),
                      data.next_week_status, null)}
    </div>` +

    // Row 3: Leaderboard/balance + reliability
    `<div class="two-col" style="margin-bottom:16px">
      ${_balanceCard(data.workload_balance, data.top_teachers)}
      ${_reliabilityCard(data.teacher_reliability)}
    </div>` +

    // Row 4: No-duty teachers
    _noDutyCard(data.teachers_without_duties_week, data.zero_duty_teachers_month);

  _animateAll(root);
}