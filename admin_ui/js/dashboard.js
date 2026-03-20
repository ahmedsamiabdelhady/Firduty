/**
 * dashboard.js — Firduty Admin Dashboard  v3.0
 *
 * Three parallel API calls:
 *   1. GET /admin/dashboard         → weekly stats, teacher counts, warnings
 *   2. GET /weeks/{weekStart}       → full week data for today-specific insights
 *   3. GET /admin/reports/monthly-points → confirmation rate for current month
 *
 * All insight sections are computed client-side from these three responses.
 */

/* ─── Date helpers ────────────────────────────────────────────────────────── */

function _today() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function _weekStart() {
  const d = new Date();
  d.setDate(d.getDate() - d.getDay()); // rewind to Sunday
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}

function _dayName(dateStr) {
  const DAYS_EN = ['Sunday','Monday','Tuesday','Wednesday','Thursday','Friday','Saturday'];
  const DAYS_AR = ['الأحد','الاثنين','الثلاثاء','الأربعاء','الخميس','الجمعة','السبت'];
  const d = new Date(`${dateStr}T12:00:00`);
  return (lang() === 'ar' ? DAYS_AR : DAYS_EN)[d.getDay()];
}

function _fmtDate(dateStr) {
  const d = new Date(`${dateStr}T12:00:00`);
  return d.toLocaleDateString(lang() === 'ar' ? 'ar-OM' : 'en-GB',
    { day: 'numeric', month: 'long', year: 'numeric' });
}

/* ─── Shared helpers ──────────────────────────────────────────────────────── */

function lang() { return I18N.getLang(); }

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

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
  return `<span class="status-pill ${status}">${I18N.t(status) || status}</span>`;
}

function rankBadge(i) {
  const cls = ['gold','silver','bronze'][i] ?? '';
  return `<span class="rank-badge ${cls}">${i + 1}</span>`;
}

function barRow(label, count, maxCount, cssClass = '', title = '') {
  const pct = maxCount > 0 ? Math.round((count / maxCount) * 100) : 0;
  return `
    <div class="bar-row">
      <span class="bar-label" title="${escHtml(title || label)}">${escHtml(label)}</span>
      <div class="bar-track"><div class="bar-fill ${cssClass}" style="width:${pct}%"></div></div>
      <span class="bar-count">${count}</span>
    </div>`;
}

function greetingText() {
  const h = new Date().getHours();
  if (h < 12) return '🌅 ' + (I18N.t('good_morning')  || 'Good morning');
  if (h < 18) return '☀️ ' + (I18N.t('good_afternoon') || 'Good afternoon');
  return      '🌙 ' + (I18N.t('good_evening')   || 'Good evening');
}

/* ─── Compute helpers ─────────────────────────────────────────────────────── */

/**
 * Build a map of { teacher_id → teacher_name } for ALL active teachers
 * using both teacher_counts (have duties this week) and
 * teachers_without_duties_this_week (no duties this week).
 */
function _buildAllTeachersMap(dashData) {
  const map = new Map();
  for (const t of dashData.current_week?.teacher_counts ?? []) {
    map.set(t.teacher_id, t.teacher_name);
  }
  for (const t of dashData.teachers_without_duties_this_week ?? []) {
    map.set(t.teacher_id, t.teacher_name);
  }
  return map; // teacher_id (number) → name (string)
}

/**
 * From the full week data, extract today's assignment info.
 * Returns { total, assigned, teachersOnDuty: Map<id,name> }
 */
function _computeToday(weekData, todayStr) {
  const result = { total: 0, assigned: 0, teachersOnDuty: new Map() };
  if (!weekData?.day_plans) return result;

  const todayPlan = weekData.day_plans.find(d => String(d.date) === todayStr);
  if (!todayPlan) return result;

  for (const sl of todayPlan.shift_locations ?? []) {
    for (const a of sl.assignments ?? []) {
      result.total++;
      if (a.teacher_id) {
        result.assigned++;
        result.teachersOnDuty.set(a.teacher_id, a.teacher_name || '—');
      }
    }
  }
  return result;
}

/**
 * Compute confirmation totals from monthly report teacher array.
 * Returns { confirmed, onTime, late, noPoints }
 */
function _computeConfirmationStats(reportData) {
  const teachers = reportData?.teachers ?? [];
  const onTime   = teachers.reduce((s, t) => s + (t.on_time   ?? 0), 0);
  const late     = teachers.reduce((s, t) => s + (t.late      ?? 0), 0);
  const noPoints = teachers.reduce((s, t) => s + (t.no_points ?? 0), 0);
  const confirmed = onTime + late + noPoints;
  return { confirmed, onTime, late, noPoints };
}

/* ─── Section renderers ───────────────────────────────────────────────────── */

// ── 1. Greeting + hero stat cards ──────────────────────────────────────────

function renderHeroSection(dashData, todayStats) {
  const fillPct = dashData.current_week?.total_slots > 0
    ? Math.round((dashData.current_week.assigned_slots / dashData.current_week.total_slots) * 100)
    : 0;

  const fillColor = fillPct >= 80 ? 'green' : fillPct >= 40 ? 'orange' : 'red';

  const updatedAt = new Date().toLocaleTimeString(
    lang() === 'ar' ? 'ar-OM' : 'en-GB',
    { hour: '2-digit', minute: '2-digit' }
  );

  return `
    <div class="dash-greet">
      <div class="dash-greet-text">
        <h2>${greetingText()}</h2>
        <p style="font-size:0.82rem;color:var(--text-muted)">
          ${_dayName(_today())}, ${_fmtDate(_today())}
        </p>
      </div>
      <span class="dash-updated">Updated ${updatedAt}</span>
    </div>

    <div class="dash-stat-grid">
      <div class="dash-stat-card">
        <div class="dash-stat-icon">👩‍🏫</div>
        <div class="dash-stat-value">${dashData.total_active_teachers ?? 0}</div>
        <div class="dash-stat-label">${I18N.t('active_teachers')}</div>
      </div>
      <div class="dash-stat-card">
        <div class="dash-stat-icon">📍</div>
        <div class="dash-stat-value">${dashData.total_locations ?? 0}</div>
        <div class="dash-stat-label">${I18N.t('total_locations')}</div>
      </div>
      <div class="dash-stat-card">
        <div class="dash-stat-icon">⏰</div>
        <div class="dash-stat-value">${dashData.total_shifts ?? 0}</div>
        <div class="dash-stat-label">${I18N.t('total_shifts')}</div>
      </div>
      <div class="dash-stat-card ${fillColor}">
        <div class="dash-stat-icon">📊</div>
        <div class="dash-stat-value">${fillPct}%</div>
        <div class="dash-stat-label">Week Fill Rate</div>
      </div>
    </div>`;
}

// ── 2. TODAY at a glance ───────────────────────────────────────────────────

function renderTodaySection(dashData, todayStats, allTeachersMap, weekData) {
  const todayStr  = _today();
  const hasWeek   = !!weekData?.day_plans;
  const status    = dashData.current_week?.status ?? null;

  // Slots today
  const fillPct = todayStats.total > 0
    ? Math.round((todayStats.assigned / todayStats.total) * 100) : 0;

  const ringColor = fillPct >= 80 ? 'var(--primary)' : fillPct >= 40 ? 'var(--warning)' : 'var(--danger)';
  const circumference = 2 * Math.PI * 28; // r=28
  const dashOffset    = circumference * (1 - fillPct / 100);

  // Teachers on/off duty today
  const onDutyChips = [...todayStats.teachersOnDuty.values()]
    .map(name => `<span class="td-chip td-chip--on">${escHtml(name)}</span>`)
    .join('') || '<span style="color:var(--text-muted);font-size:0.82rem">None assigned</span>';

  const offDuty = [...allTeachersMap.entries()]
    .filter(([id]) => !todayStats.teachersOnDuty.has(id))
    .map(([, name]) => name);

  const offDutyChips = offDuty.length > 0
    ? offDuty.map(name => `<span class="td-chip td-chip--off">${escHtml(name)}</span>`).join('')
    : `<span class="td-chip td-chip--ok">All teachers have duties today ✓</span>`;

  const noDataMsg = !hasWeek
    ? `<p style="color:var(--text-muted);font-size:0.85rem;padding:12px 0">
         Week data unavailable — plan not created yet.
       </p>`
    : '';

  return `
    <div class="section-card" style="border-left:4px solid var(--nav);">
      <h3>📅 Today at a Glance
        <span style="font-weight:400;font-size:0.78rem;color:var(--text-muted);margin-inline-start:8px">
          ${_dayName(todayStr)} · ${statusPill(status)}
        </span>
      </h3>

      ${noDataMsg}

      <div class="today-grid">
        <!-- Circular progress ring -->
        <div class="today-ring-wrap">
          <svg width="80" height="80" viewBox="0 0 80 80">
            <circle cx="40" cy="40" r="28" fill="none" stroke="#e5e7eb" stroke-width="8"/>
            <circle cx="40" cy="40" r="28" fill="none"
                    stroke="${ringColor}" stroke-width="8"
                    stroke-dasharray="${circumference.toFixed(1)}"
                    stroke-dashoffset="${dashOffset.toFixed(1)}"
                    stroke-linecap="round"
                    transform="rotate(-90 40 40)"/>
            <text x="40" y="44" text-anchor="middle"
                  font-size="16" font-weight="800" fill="${ringColor}">${fillPct}%</text>
          </svg>
          <div class="today-ring-label">Today's Fill</div>
        </div>

        <!-- Slot counts -->
        <div class="today-slot-counts">
          <div class="today-slot-row">
            <span class="today-slot-num" style="color:var(--text)">${todayStats.total}</span>
            <span class="today-slot-lbl">Total slots</span>
          </div>
          <div class="today-slot-row">
            <span class="today-slot-num" style="color:var(--primary)">${todayStats.assigned}</span>
            <span class="today-slot-lbl">Assigned</span>
          </div>
          <div class="today-slot-row">
            <span class="today-slot-num" style="color:${todayStats.total - todayStats.assigned > 0 ? 'var(--danger)' : 'var(--primary)'}">
              ${todayStats.total - todayStats.assigned}
            </span>
            <span class="today-slot-lbl">Empty</span>
          </div>
        </div>

        <!-- Teachers on duty today -->
        <div class="today-teachers">
          <div class="today-teachers-label">
            ✅ On duty today (${todayStats.teachersOnDuty.size})
          </div>
          <div class="today-chips">${onDutyChips}</div>
        </div>

        <!-- Teachers NOT on duty today -->
        <div class="today-teachers">
          <div class="today-teachers-label ${offDuty.length > 0 ? 'warn' : ''}">
            ${offDuty.length > 0 ? '⚠️' : '✅'} Not on duty today (${offDuty.length})
          </div>
          <div class="today-chips">${offDutyChips}</div>
        </div>
      </div>
    </div>`;
}

// ── 3. Workload distribution (most / least / balance) ──────────────────────

function renderWorkloadSection(dashData) {
  const counts = dashData.current_week?.teacher_counts ?? [];
  if (!counts.length) {
    return `
      <div class="section-card">
        <h3>⚖️ Workload Distribution</h3>
        <p style="color:var(--text-muted);font-size:0.85rem">No assignments yet this week.</p>
      </div>`;
  }

  const maxCount = counts[0].count;
  const minCount = counts[counts.length - 1].count;
  const gap      = maxCount - minCount;
  const balanced = gap <= 2;

  const allIds  = new Set(counts.map(t => t.teacher_id));
  const noduty  = (dashData.teachers_without_duties_this_week ?? []).length;
  const total   = dashData.total_active_teachers ?? counts.length;

  // Highlight most and least
  const bars = counts.map((t, i) => {
    const pct   = maxCount > 0 ? Math.round((t.count / maxCount) * 100) : 0;
    const isTop = i === 0;
    const isBot = i === counts.length - 1 && counts.length > 1;
    const badge = isTop ? ' 🥇' : isBot ? ' 🔻' : '';
    const color = isTop ? 'var(--primary)' : isBot ? '#f87171' : 'var(--nav)';
    return `
      <div class="bar-row">
        <span class="bar-label" title="${escHtml(t.teacher_name)}">${escHtml(t.teacher_name)}${badge}</span>
        <div class="bar-track">
          <div class="bar-fill" style="width:${pct}%;background:${color};transition:width 0.5s ease"></div>
        </div>
        <span class="bar-count">${t.count}</span>
      </div>`;
  }).join('');

  const balanceColor = balanced ? 'var(--primary)' : gap <= 4 ? 'var(--warning)' : 'var(--danger)';
  const balanceLabel = balanced ? 'Well balanced ✓' : gap <= 4 ? 'Slightly uneven' : 'Uneven — review needed';

  return `
    <div class="section-card">
      <h3>⚖️ Workload Distribution
        <span class="wl-badge" style="background:${balanceColor}10;color:${balanceColor};border:1px solid ${balanceColor}30;">
          ${balanceLabel}
        </span>
      </h3>

      <!-- Summary pills -->
      <div class="wl-summary">
        <div class="wl-pill">
          <span class="wl-pill-icon">🥇</span>
          <span class="wl-pill-name">${escHtml(counts[0]?.teacher_name ?? '—')}</span>
          <span class="wl-pill-val" style="color:var(--primary)">${counts[0]?.count ?? 0} duties</span>
          <span class="wl-pill-tag">Most this week</span>
        </div>
        ${counts.length > 1 ? `
        <div class="wl-pill">
          <span class="wl-pill-icon">🔻</span>
          <span class="wl-pill-name">${escHtml(counts[counts.length-1]?.teacher_name ?? '—')}</span>
          <span class="wl-pill-val" style="color:#f87171">${counts[counts.length-1]?.count ?? 0} duties</span>
          <span class="wl-pill-tag">Fewest (with duties)</span>
        </div>` : ''}
        ${noduty > 0 ? `
        <div class="wl-pill" style="border-color:#fee2e2">
          <span class="wl-pill-icon">⚠️</span>
          <span class="wl-pill-name">${noduty} teacher${noduty > 1 ? 's' : ''}</span>
          <span class="wl-pill-val" style="color:var(--danger)">0 duties</span>
          <span class="wl-pill-tag">No duties this week</span>
        </div>` : `
        <div class="wl-pill" style="border-color:#d1fae5">
          <span class="wl-pill-icon">✅</span>
          <span class="wl-pill-name">All teachers</span>
          <span class="wl-pill-val" style="color:var(--primary)">assigned</span>
          <span class="wl-pill-tag">No idle teachers</span>
        </div>`}
      </div>

      <!-- Full ranking bars -->
      <div style="margin-top:16px">
        <p style="font-size:0.8rem;font-weight:600;color:var(--text-muted);margin-bottom:8px">
          All ${counts.length} teacher${counts.length > 1 ? 's' : ''} · Gap: ${gap} duties
        </p>
        ${bars}
      </div>
    </div>`;
}

// ── 4. Confirmation rate (monthly) ─────────────────────────────────────────

function renderConfirmationSection(reportData, dashData) {
  const { confirmed, onTime, late, noPoints } = _computeConfirmationStats(reportData);

  const now       = new Date();
  const monthName = now.toLocaleString(lang() === 'ar' ? 'ar-OM' : 'en-GB', { month: 'long' });
  const year      = now.getFullYear();

  // On-time rate among confirmed duties
  const onTimePct   = confirmed > 0 ? Math.round((onTime   / confirmed) * 100) : 0;
  const latePct     = confirmed > 0 ? Math.round((late     / confirmed) * 100) : 0;
  const noPointsPct = confirmed > 0 ? Math.round((noPoints / confirmed) * 100) : 0;

  // Per-teacher reliability table (top 5 by confirmations)
  const teachers = (reportData?.teachers ?? []).slice(0, 6);
  const maxConf  = Math.max(...teachers.map(t => t.confirmations), 1);

  const teacherRows = teachers.length > 0
    ? teachers.map((t, i) => {
        const barPct   = Math.round((t.confirmations / maxConf) * 100);
        const ptColor  = t.total_points > 0 ? 'var(--primary)' : 'var(--text-muted)';
        return `
          <tr>
            <td>${rankBadge(i)}</td>
            <td style="font-weight:600">${escHtml(t.teacher_name)}</td>
            <td>
              <div style="display:flex;align-items:center;gap:6px">
                <div style="flex:1;background:#e9ecef;border-radius:4px;height:8px;overflow:hidden">
                  <div style="width:${barPct}%;height:8px;background:var(--nav);border-radius:4px;transition:width .4s"></div>
                </div>
                <span style="font-size:0.8rem;font-weight:700;min-width:20px">${t.confirmations}</span>
              </div>
            </td>
            <td><span style="font-weight:700;color:${ptColor}">${t.total_points} pts</span></td>
            <td style="font-size:0.78rem">
              <span class="pill pill-green">${t.on_time}</span>
              <span class="pill pill-yellow" style="margin-inline-start:3px">${t.late}</span>
            </td>
          </tr>`;
      }).join('')
    : `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:20px">
         No confirmation data for ${monthName} ${year}
       </td></tr>`;

  // Big confirmation rate ring
  const ringColor    = onTimePct >= 75 ? 'var(--primary)' : onTimePct >= 50 ? 'var(--warning)' : 'var(--danger)';
  const circumference = 2 * Math.PI * 30;
  const dashOff       = circumference * (1 - onTimePct / 100);

  return `
    <div class="section-card">
      <h3>✅ Confirmation Rate · <span style="font-weight:400;font-size:0.82rem;color:var(--text-muted)">${monthName} ${year}</span></h3>

      <div class="conf-layout">
        <!-- Ring + total -->
        <div class="conf-ring-wrap">
          <svg width="88" height="88" viewBox="0 0 88 88">
            <circle cx="44" cy="44" r="30" fill="none" stroke="#e5e7eb" stroke-width="9"/>
            <circle cx="44" cy="44" r="30" fill="none"
                    stroke="${ringColor}" stroke-width="9"
                    stroke-dasharray="${circumference.toFixed(1)}"
                    stroke-dashoffset="${dashOff.toFixed(1)}"
                    stroke-linecap="round"
                    transform="rotate(-90 44 44)"/>
            <text x="44" y="48" text-anchor="middle"
                  font-size="16" font-weight="800" fill="${ringColor}">${onTimePct}%</text>
          </svg>
          <div style="text-align:center;font-size:0.78rem;color:var(--text-muted);margin-top:4px">On-time rate</div>
          <div style="text-align:center;font-size:1.2rem;font-weight:800;color:var(--nav);margin-top:6px">${confirmed}</div>
          <div style="text-align:center;font-size:0.75rem;color:var(--text-muted)">total confirmed</div>
        </div>

        <!-- Breakdown bars -->
        <div class="conf-breakdown">
          <div class="conf-bar-row">
            <span class="conf-bar-label">On time <span style="font-size:0.72rem">(2 pts)</span></span>
            <div class="conf-bar-track">
              <div class="conf-bar-fill" style="width:${onTimePct}%;background:var(--primary)"></div>
            </div>
            <span class="conf-bar-num green">${onTime}</span>
            <span class="conf-bar-pct">${onTimePct}%</span>
          </div>
          <div class="conf-bar-row">
            <span class="conf-bar-label">Late 1–5m <span style="font-size:0.72rem">(1 pt)</span></span>
            <div class="conf-bar-track">
              <div class="conf-bar-fill" style="width:${latePct}%;background:var(--warning)"></div>
            </div>
            <span class="conf-bar-num orange">${late}</span>
            <span class="conf-bar-pct">${latePct}%</span>
          </div>
          <div class="conf-bar-row">
            <span class="conf-bar-label">No points <span style="font-size:0.72rem">(0 pts)</span></span>
            <div class="conf-bar-track">
              <div class="conf-bar-fill" style="width:${noPointsPct}%;background:var(--danger)"></div>
            </div>
            <span class="conf-bar-num red">${noPoints}</span>
            <span class="conf-bar-pct">${noPointsPct}%</span>
          </div>
        </div>
      </div>

      ${teachers.length > 0 ? `
      <!-- Per-teacher reliability -->
      <div style="margin-top:18px;overflow-x:auto">
        <p style="font-size:0.8rem;font-weight:600;color:var(--text-muted);margin-bottom:8px">Teacher Reliability</p>
        <table style="width:100%;border-collapse:collapse;font-size:0.83rem">
          <thead>
            <tr style="border-bottom:1px solid var(--border)">
              <th style="padding:6px 8px;text-align:start;color:var(--text-muted);font-size:0.76rem">#</th>
              <th style="padding:6px 8px;text-align:start;color:var(--text-muted);font-size:0.76rem">Teacher</th>
              <th style="padding:6px 8px;text-align:start;color:var(--text-muted);font-size:0.76rem">Confirmations</th>
              <th style="padding:6px 8px;text-align:start;color:var(--text-muted);font-size:0.76rem">Points</th>
              <th style="padding:6px 8px;text-align:start;color:var(--text-muted);font-size:0.76rem">On Time / Late</th>
            </tr>
          </thead>
          <tbody>${teacherRows}</tbody>
        </table>
      </div>` : ''}
    </div>`;
}

// ── 5. Warnings ────────────────────────────────────────────────────────────

function renderWarningsSection(warnings) {
  if (!warnings?.length) return '';
  const items = warnings.map(w => `<li>${escHtml(w)}</li>`).join('');
  return `
    <div class="section-card" style="border-left:4px solid var(--warning)">
      <h3>⚠️ ${I18N.t('warnings')}</h3>
      <ul class="warn-list">${items}</ul>
    </div>`;
}

// ── 6. Week sections (current + next) ──────────────────────────────────────

function renderWeekSection(stats, label) {
  if (!stats) return `
    <div class="section-card">
      <h3>${escHtml(label)}</h3>
      <p style="color:var(--text-muted);font-size:0.85rem">${I18N.t('no_week_plan')}</p>
    </div>`;

  const assignedPct = stats.total_slots > 0
    ? Math.round((stats.assigned_slots / stats.total_slots) * 100) : 0;

  const miniStats = `
    <div class="mini-stat-grid">
      <div class="mini-stat">
        <div class="mini-stat-value">${stats.total_slots}</div>
        <div class="mini-stat-label">Total Slots</div>
      </div>
      <div class="mini-stat">
        <div class="mini-stat-value green">${stats.assigned_slots}</div>
        <div class="mini-stat-label">Assigned</div>
      </div>
      <div class="mini-stat">
        <div class="mini-stat-value ${stats.unassigned_slots > 0 ? 'red' : 'green'}">${stats.unassigned_slots}</div>
        <div class="mini-stat-label">Empty</div>
      </div>
      <div class="mini-stat">
        <div class="mini-stat-value">${assignedPct}%</div>
        <div class="mini-stat-label">Filled</div>
      </div>
    </div>`;

  // Day-by-day fill bars
  let dayBarsHtml = '';
  if (stats.duties_per_day && Object.keys(stats.duties_per_day).length > 0) {
    const maxDay = Math.max(...Object.values(stats.duties_per_day), 1);
    const today  = _today();
    dayBarsHtml = `
      <p style="font-size:0.8rem;font-weight:600;color:var(--text-muted);margin:14px 0 8px">By Day</p>
      ${Object.entries(stats.duties_per_day).map(([d, c]) => {
        const pct     = Math.round((c / maxDay) * 100);
        const isToday = d === today;
        return `
          <div class="day-fill-bar">
            <span class="day-fill-bar-name" style="${isToday ? 'color:var(--nav);font-weight:700' : ''}">
              ${escHtml(_dayName(d))} ${isToday ? '◀' : ''}
            </span>
            <div class="day-fill-bar-track">
              <div class="day-fill-bar-fill"
                   style="width:${pct}%;${isToday ? 'background:var(--nav)' : ''}"></div>
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
    <p style="font-size:0.8rem;font-weight:600;color:var(--text-muted);margin:14px 0 8px">By Duty Type</p>
    ${barRow(I18N.t('morning_endofday'), morningCount, maxType)}
    ${barRow(I18N.t('break_duty'),       breakCount,   maxType, 'break-type')}`;

  // Teacher duty bars (top 6)
  let topHtml = '';
  if (stats.teacher_counts?.length > 0) {
    const maxT = stats.teacher_counts[0].count || 1;
    topHtml = `
      <p style="font-size:0.8rem;font-weight:600;color:var(--text-muted);margin:14px 0 8px">By Teacher</p>
      ${stats.teacher_counts.slice(0, 6).map(t => barRow(t.teacher_name, t.count, maxT)).join('')}
      ${stats.teacher_counts.length > 6
        ? `<p style="font-size:0.75rem;color:var(--text-muted);margin-top:4px">+${stats.teacher_counts.length-6} more</p>`
        : ''}`;
  }

  return `
    <div class="section-card">
      <h3>📅 ${escHtml(label)} — ${statusPill(stats.status)}
        <small style="font-weight:400;color:var(--text-muted);font-size:0.76rem"> v${stats.version ?? 1}</small>
      </h3>
      ${miniStats}
      ${dayBarsHtml}
      ${typeHtml}
      ${topHtml}
    </div>`;
}

// ── 7. Teacher leaderboard + no-duty list ──────────────────────────────────

function renderTeacherInsights(dashData) {
  // Top teachers leaderboard
  let topHtml = '';
  const top = dashData.top_teachers_this_week ?? [];
  if (top.length > 0) {
    const rows = top.map((t, i) => `
      <tr>
        <td style="width:32px">${rankBadge(i)}</td>
        <td style="font-weight:600">${escHtml(t.teacher_name)}</td>
        <td>
          <span style="font-size:1.05rem;font-weight:800;color:var(--primary)">${t.count}</span>
          <span style="font-size:0.75rem;color:var(--text-muted);margin-inline-start:3px">duties</span>
        </td>
      </tr>`).join('');
    topHtml = `
      <div class="section-card">
        <h3>🏆 Most Active This Week</h3>
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

  // Teachers without duties this week
  let noDutyHtml = '';
  const noDuty = dashData.teachers_without_duties_this_week ?? [];
  if (noDuty.length > 0) {
    const chips = noDuty.map(t =>
      `<span class="no-duty-chip">${escHtml(t.teacher_name)}</span>`
    ).join('');
    noDutyHtml = `
      <div class="section-card" style="border-left:4px solid var(--warning)">
        <h3>📋 No Duties This Week
          <span style="background:#fee2e2;color:#b91c1c;border-radius:10px;
                       padding:2px 8px;font-size:0.75rem;font-weight:700;
                       margin-inline-start:8px">${noDuty.length}</span>
        </h3>
        <p style="font-size:0.82rem;color:var(--text-muted);margin-bottom:10px">
          Consider assigning duties to these teachers for a balanced roster.
        </p>
        <div>${chips}</div>
      </div>`;
  } else if ((dashData.current_week?.teacher_counts?.length ?? 0) > 0) {
    noDutyHtml = `
      <div class="section-card" style="border-left:4px solid var(--primary)">
        <h3>✅ Full Coverage</h3>
        <p style="font-size:0.85rem;color:var(--text-muted)">
          All active teachers have at least one duty this week.
        </p>
      </div>`;
  }

  if (!topHtml && !noDutyHtml) return '';
  return `
    <div class="two-col">
      ${topHtml  || '<div></div>'}
      ${noDutyHtml || '<div></div>'}
    </div>`;
}

/* ─── Main render ─────────────────────────────────────────────────────────── */

function renderDashboard(dashData, weekData, reportData) {
  const todayStr      = _today();
  const allTeachersMap = _buildAllTeachersMap(dashData);
  const todayStats    = _computeToday(weekData, todayStr);

  const html = [
    renderHeroSection(dashData, todayStats),
    renderTodaySection(dashData, todayStats, allTeachersMap, weekData),
    `<div class="two-col">
      ${renderWorkloadSection(dashData)}
      ${renderConfirmationSection(reportData, dashData)}
     </div>`,
    renderWarningsSection(dashData.warnings),
    `<div class="two-col">
      ${renderWeekSection(dashData.current_week, I18N.t('current_week'))}
      ${renderWeekSection(dashData.next_week,    I18N.t('next_week'))}
     </div>`,
    renderTeacherInsights(dashData),
  ].join('');

  document.getElementById('dashContent').innerHTML = html;
}

/* ─── Data loading ────────────────────────────────────────────────────────── */

async function loadDashboard() {
  const content = document.getElementById('dashContent');
  if (!content) return;

  // Show loading state
  content.innerHTML = `
    <div class="dash-loading">
      <div class="spinner"></div>
      <p>Loading dashboard…</p>
    </div>`;

  try {
    const weekStart = _weekStart();
    const now       = new Date();
    const year      = now.getFullYear();
    const month     = now.getMonth() + 1;

    // Three parallel calls — dashboard + full week (today insights) + monthly report
    const [dashRes, weekRes, reportRes] = await Promise.all([
      apiFetch('/admin/dashboard'),
      apiFetch(`/weeks/${weekStart}`),
      apiFetch(`/admin/reports/monthly-points?year=${year}&month=${month}`),
    ]);

    if (!dashRes?.ok) {
      content.innerHTML = `
        <div class="dash-error">
          <div class="error-icon">⚠️</div>
          <p>Could not load dashboard data (${dashRes?.status ?? 'network error'})</p>
          <button class="btn btn-primary btn-sm" onclick="loadDashboard()">Retry</button>
        </div>`;
      return;
    }

    const dashData   = await dashRes.json();
    const weekData   = weekRes?.ok   ? await weekRes.json()   : null;
    const reportData = reportRes?.ok ? await reportRes.json() : null;

    renderDashboard(dashData, weekData, reportData);

  } catch (err) {
    console.error('loadDashboard failed:', err);
    content.innerHTML = `
      <div class="dash-error">
        <div class="error-icon">⚠️</div>
        <p>${I18N.t('error_generic')}</p>
        <button class="btn btn-primary btn-sm" onclick="loadDashboard()">Retry</button>
      </div>`;
  }
}

async function refreshDashboard() {
  const btn     = document.getElementById('refreshBtn');
  const content = document.getElementById('dashContent');

  if (btn) btn.classList.add('spinning');
  if (content) { content.style.opacity = '0.5'; content.style.pointerEvents = 'none'; }

  await loadDashboard();

  if (content) { content.style.opacity = ''; content.style.pointerEvents = ''; }
  if (btn) btn.classList.remove('spinning');
  showToast('Dashboard refreshed', 'info');
}

/* ─── Auto-init ───────────────────────────────────────────────────────────── */

async function initDashboard() {
  await I18N.load(localStorage.getItem('firduty_lang') || 'en');
  await loadDashboard();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initDashboard);
} else {
  initDashboard();
}

document.addEventListener('DOMContentLoaded', async () => {
  await I18N.init();
  guardPage();
  await loadShifts();
});