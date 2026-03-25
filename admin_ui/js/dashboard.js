
/**
 * dashboard.js — Firduty Admin Dashboard v4.0
 * Optimized for action-first UX and cleaner data storytelling.
 */

const DASH_TZ = 'Asia/Muscat';

/* ─── Time & formatting helpers ─────────────────────────────────────────── */
function _partsInMuscat(date = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: DASH_TZ,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    weekday: 'short',
  }).formatToParts(date);
  return Object.fromEntries(parts.filter(p => p.type !== 'literal').map(p => [p.type, p.value]));
}

function _today() {
  const p = _partsInMuscat();
  return `${p.year}-${p.month}-${p.day}`;
}

function _weekStart() {
  const p = _partsInMuscat();
  const base = new Date(Date.UTC(Number(p.year), Number(p.month) - 1, Number(p.day), 12, 0, 0));
  const day = base.getUTCDay();
  base.setUTCDate(base.getUTCDate() - day);
  const yy = base.getUTCFullYear();
  const mm = String(base.getUTCMonth() + 1).padStart(2, '0');
  const dd = String(base.getUTCDate()).padStart(2, '0');
  return `${yy}-${mm}-${dd}`;
}

function _dayName(dateStr) {
  const DAYS_EN = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
  const DAYS_AR = ['الأحد', 'الاثنين', 'الثلاثاء', 'الأربعاء', 'الخميس', 'الجمعة', 'السبت'];
  const d = new Date(`${dateStr}T12:00:00`);
  return (lang() === 'ar' ? DAYS_AR : DAYS_EN)[d.getDay()];
}

function _fmtDate(dateStr) {
  const d = new Date(`${dateStr}T12:00:00`);
  return d.toLocaleDateString(lang() === 'ar' ? 'ar-OM' : 'en-GB', {
    day: 'numeric', month: 'long', year: 'numeric', timeZone: DASH_TZ,
  });
}

function _fmtTime(date = new Date()) {
  return date.toLocaleTimeString(lang() === 'ar' ? 'ar-OM' : 'en-GB', {
    hour: '2-digit', minute: '2-digit', timeZone: DASH_TZ,
  });
}

function _currentMonthYear() {
  const now = new Date();
  const monthName = now.toLocaleString(lang() === 'ar' ? 'ar-OM' : 'en-GB', { month: 'long', timeZone: DASH_TZ });
  const year = Number(new Intl.DateTimeFormat('en-CA', { year: 'numeric', timeZone: DASH_TZ }).format(now));
  return { monthName, year };
}

/* ─── Shared helpers ─────────────────────────────────────────────────────── */
function lang() { return I18N.getLang(); }

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
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
  if (!status) return `<span class="status-pill none">${I18N.t('no_week_plan') || 'No week plan'}</span>`;
  const label = I18N.t(status) || status;
  const cls = String(status).toLowerCase().includes('publish') ? 'published' : 'draft';
  return `<span class="status-pill ${cls}">${escHtml(label)}</span>`;
}

function rankBadge(i) {
  const cls = ['gold', 'silver', 'bronze'][i] ?? '';
  return `<span class="rank-badge ${cls}">${i + 1}</span>`;
}

function barRow(label, count, maxCount, cssClass = '', title = '') {
  const pct = maxCount > 0 ? Math.round((count / maxCount) * 100) : 0;
  const extra = title ? ` title="${escHtml(title)}"` : '';
  return `
    <div class="bar-row"${extra}>
      <span class="bar-label">${escHtml(label)}</span>
      <div class="bar-track"><div class="bar-fill ${cssClass}" style="width:${pct}%"></div></div>
      <span class="bar-count">${count}</span>
    </div>`;
}

function greetingText() {
  const hour = Number(_partsInMuscat().hour || '0');
  if (hour < 12) return I18N.t('good_morning') || 'Good morning';
  if (hour < 18) return I18N.t('good_afternoon') || 'Good afternoon';
  return I18N.t('good_evening') || 'Good evening';
}

/* ─── Compute helpers ────────────────────────────────────────────────────── */
function _buildAllTeachersMap(dashData) {
  const map = new Map();
  for (const t of dashData.current_week?.teacher_counts ?? []) map.set(t.teacher_id, t.teacher_name);
  for (const t of dashData.teachers_without_duties_this_week ?? []) map.set(t.teacher_id, t.teacher_name);
  return map;
}

function _computeToday(weekData, todayStr) {
  const result = { total: 0, assigned: 0, teachersOnDuty: new Map(), shiftLocations: 0 };
  if (!weekData?.day_plans) return result;
  const todayPlan = weekData.day_plans.find(d => String(d.date) === todayStr);
  if (!todayPlan) return result;
  for (const sl of todayPlan.shift_locations ?? []) {
    result.shiftLocations += 1;
    for (const a of sl.assignments ?? []) {
      result.total += 1;
      if (a.teacher_id) {
        result.assigned += 1;
        result.teachersOnDuty.set(a.teacher_id, a.teacher_name || '—');
      }
    }
  }
  return result;
}

function _computeConfirmationStats(reportData) {
  const teachers = reportData?.teachers ?? [];
  const onTime = teachers.reduce((s, t) => s + (t.on_time ?? 0), 0);
  const late = teachers.reduce((s, t) => s + (t.late ?? 0), 0);
  const noPoints = teachers.reduce((s, t) => s + (t.no_points ?? 0), 0);
  const confirmed = onTime + late + noPoints;
  return { confirmed, onTime, late, noPoints };
}

function _dashboardInsights(dashData, weekData, reportData) {
  const today = _computeToday(weekData, _today());
  const week = dashData.current_week ?? null;
  const fillPct = week?.total_slots ? Math.round((week.assigned_slots / week.total_slots) * 100) : 0;
  const todayFillPct = today.total ? Math.round((today.assigned / today.total) * 100) : 0;
  const noDutyCount = (dashData.teachers_without_duties_this_week ?? []).length;
  const warningsCount = (dashData.warnings ?? []).length;
  const emptyToday = Math.max(0, today.total - today.assigned);
  const emptyWeek = Math.max(0, (week?.unassigned_slots ?? 0));
  const confirmation = _computeConfirmationStats(reportData);
  const onTimePct = confirmation.confirmed ? Math.round((confirmation.onTime / confirmation.confirmed) * 100) : 0;
  let healthScore = 100;
  healthScore -= Math.min(45, emptyWeek * 4);
  healthScore -= Math.min(20, emptyToday * 6);
  healthScore -= Math.min(15, warningsCount * 4);
  healthScore -= Math.min(15, noDutyCount * 3);
  healthScore -= Math.max(0, 75 - onTimePct) / 2;
  healthScore = Math.max(0, Math.min(100, Math.round(healthScore)));
  return { today, week, fillPct, todayFillPct, noDutyCount, warningsCount, emptyToday, emptyWeek, confirmation, onTimePct, healthScore };
}

/* ─── Section renderers ──────────────────────────────────────────────────── */
function renderHeroSection(dashData, weekData, reportData) {
  const insights = _dashboardInsights(dashData, weekData, reportData);
  const dateText = `${_dayName(_today())}, ${_fmtDate(_today())}`;
  const healthTone = insights.healthScore >= 80 ? 'success' : insights.healthScore >= 60 ? 'warning' : 'danger';
  const healthText = insights.healthScore >= 80
    ? (lang() === 'ar' ? 'الجدول تحت السيطرة' : 'Roster looks healthy')
    : insights.healthScore >= 60
    ? (lang() === 'ar' ? 'فيه شوية نقاط تحتاج متابعة' : 'A few items need attention')
    : (lang() === 'ar' ? 'فيه ضغط واضح على الجدول' : 'Planner needs attention');

  return `
    <section class="dash-hero">
      <div class="dash-panel dash-hero-main">
        <div class="dash-hero-top">
          <div>
            <div class="dash-eyebrow">✨ ${escHtml(greetingText())}</div>
            <div class="dash-hero-title">${lang() === 'ar' ? 'لوحة تحكم حية لإدارة المناوبات' : 'A live control room for your duty roster'}</div>
            <div class="dash-hero-subtitle">
              ${lang() === 'ar'
                ? 'بدل الداتا الجامدة، ركّز على اللي محتاج قرار سريع: اليوم ناقص كام slot، مين خارج التوزيع، وهل الأسبوع الحالي متزن ولا لا.'
                : 'Skip the dead stats. Focus on what needs action now: empty slots today, unbalanced workload, and whether the current week is actually ready.'}
            </div>
            <div class="dash-hero-meta">
              <span class="dash-meta-pill">🗓 ${dateText}</span>
              <span class="dash-meta-pill">🕓 ${I18N.t('updated_at') || 'Updated at'} ${_fmtTime()}</span>
              <span class="dash-meta-pill">📌 ${statusPill(insights.week?.status ?? null)}</span>
            </div>
          </div>
        </div>

        <div class="dash-actions">
          <a class="dash-action" href="planner.html">
            <span class="dash-action__icon">📅</span>
            <span class="dash-action__txt">
              <span class="dash-action__title">${I18N.t('week_planner') || 'Weekly Planner'}</span>
              <span class="dash-action__meta">${lang() === 'ar' ? 'افتح الجدول وعدّل التوزيع بسرعة' : 'Open the planner and fix assignments fast'}</span>
            </span>
          </a>
          <a class="dash-action" href="teachers.html">
            <span class="dash-action__icon">👩‍🏫</span>
            <span class="dash-action__txt">
              <span class="dash-action__title">${I18N.t('teacher_approval') || 'Teachers'}</span>
              <span class="dash-action__meta">${lang() === 'ar' ? 'تابع الموافقات واللغة والحالة' : 'Check approvals, status, and language'}</span>
            </span>
          </a>
          <a class="dash-action" href="reports.html">
            <span class="dash-action__icon">📈</span>
            <span class="dash-action__txt">
              <span class="dash-action__title">${I18N.t('monthly_report') || 'Monthly Report'}</span>
              <span class="dash-action__meta">${lang() === 'ar' ? 'راجع الالتزام والنقاط الشهريّة' : 'Review confirmations and monthly points'}</span>
            </span>
          </a>
          <a class="dash-action" href="shifts.html">
            <span class="dash-action__icon">⚙️</span>
            <span class="dash-action__txt">
              <span class="dash-action__title">${I18N.t('shift_management') || 'Shifts'}</span>
              <span class="dash-action__meta">${lang() === 'ar' ? 'عدّل الأوقات والمواقع والهيكل' : 'Adjust times, locations, and structure'}</span>
            </span>
          </a>
        </div>
      </div>

      <aside class="dash-panel dash-hero-side">
        <div class="dash-health-card">
          <div class="dash-health-head">
            <div>
              <div class="dash-health-title">${lang() === 'ar' ? 'درجة صحة التشغيل' : 'Roster health score'}</div>
              <div class="dash-health-sub">${healthText}</div>
            </div>
            <div class="dash-score">${insights.healthScore}</div>
          </div>
          <div class="dash-health-meter"><span style="width:${insights.healthScore}%"></span></div>
          <div class="dash-health-grid">
            <div class="dash-health-metric"><strong>${insights.emptyToday}</strong><span>${lang() === 'ar' ? 'Slots فاضية اليوم' : 'Empty slots today'}</span></div>
            <div class="dash-health-metric"><strong>${insights.noDutyCount}</strong><span>${lang() === 'ar' ? 'معلمين بدون مناوبات' : 'Teachers with no duties'}</span></div>
            <div class="dash-health-metric"><strong>${insights.warningsCount}</strong><span>${lang() === 'ar' ? 'تحذيرات تحتاج متابعة' : 'Warnings to review'}</span></div>
            <div class="dash-health-metric"><strong>${insights.onTimePct}%</strong><span>${lang() === 'ar' ? 'الالتزام في التأكيدات' : 'On-time confirmation rate'}</span></div>
          </div>
        </div>
      </aside>
    </section>`;
}

function renderPriorityStrip(dashData, weekData, reportData) {
  const insights = _dashboardInsights(dashData, weekData, reportData);
  const currentVersion = insights.week?.version ?? 1;
  const cards = [
    {
      tone: insights.emptyToday > 0 ? 'danger' : 'success',
      icon: insights.emptyToday > 0 ? '🚨' : '✅',
      value: insights.emptyToday,
      title: lang() === 'ar' ? 'أولوية اليوم' : 'Today priority',
      text: insights.emptyToday > 0
        ? (lang() === 'ar' ? `لسه فيه ${insights.emptyToday} slot فاضي في مناوبات اليوم.` : `${insights.emptyToday} slot(s) still empty in today's duties.`)
        : (lang() === 'ar' ? 'تغطية اليوم كاملة حاليًا.' : 'Today is fully covered right now.'),
      chips: [
        `${insights.today.assigned}/${insights.today.total || 0} ${lang() === 'ar' ? 'مُسند' : 'assigned'}`,
        `${insights.todayFillPct}% ${lang() === 'ar' ? 'تغطية' : 'coverage'}`,
      ],
    },
    {
      tone: insights.noDutyCount > 0 ? 'warning' : 'success',
      icon: insights.noDutyCount > 0 ? '⚖️' : '🌟',
      value: insights.noDutyCount,
      title: lang() === 'ar' ? 'توازن التوزيع' : 'Workload balance',
      text: insights.noDutyCount > 0
        ? (lang() === 'ar' ? 'فيه معلمين لسه خارج التوزيع هذا الأسبوع.' : 'Some teachers are still outside this week’s distribution.')
        : (lang() === 'ar' ? 'كل المعلمين داخل التوزيع الحالي.' : 'All active teachers are included this week.'),
      chips: [
        `${dashData.total_active_teachers ?? 0} ${lang() === 'ar' ? 'معلم نشط' : 'active teachers'}`,
        `${currentVersion} ${lang() === 'ar' ? 'نسخة أسبوع' : 'week version'}`,
      ],
    },
    {
      tone: insights.warningsCount > 0 ? 'warning' : 'success',
      icon: insights.warningsCount > 0 ? '🔔' : '📣',
      value: insights.warningsCount,
      title: lang() === 'ar' ? 'إشارات تحتاج قرار' : 'Action signals',
      text: insights.warningsCount > 0
        ? (lang() === 'ar' ? 'فيه تنبيهات من النظام يفضّل مراجعتها قبل النشر أو إعادة النشر.' : 'System warnings should be reviewed before publishing or republishing.')
        : (lang() === 'ar' ? 'مافيش تحذيرات بارزة الآن.' : 'No major system warnings right now.'),
      chips: [
        `${insights.emptyWeek} ${lang() === 'ar' ? 'فارغ هذا الأسبوع' : 'empty this week'}`,
        `${insights.onTimePct}% ${lang() === 'ar' ? 'التزام' : 'on-time'}`,
      ],
    },
  ];

  return `
    <section class="dash-priority-grid">
      ${cards.map(card => `
        <div class="priority-card" data-tone="${card.tone}">
          <div class="priority-card__top">
            <span class="priority-card__icon">${card.icon}</span>
            <span class="priority-card__badge">${card.value}</span>
          </div>
          <h3>${card.title}</h3>
          <p>${card.text}</p>
          <div class="priority-card__meta">
            ${card.chips.map(chip => `<span class="priority-chip">${chip}</span>`).join('')}
          </div>
        </div>`).join('')}
    </section>`;
}

function renderHeroStats(dashData, weekData, reportData) {
  const insights = _dashboardInsights(dashData, weekData, reportData);
  const items = [
    {
      icon: '👩‍🏫',
      tone: '',
      value: dashData.total_active_teachers ?? 0,
      label: I18N.t('active_teachers') || 'Active teachers',
      trend: lang() === 'ar' ? `${insights.noDutyCount} بدون مناوبات هذا الأسبوع` : `${insights.noDutyCount} without duties this week`,
    },
    {
      icon: '📍',
      tone: '',
      value: dashData.total_locations ?? 0,
      label: I18N.t('total_locations') || 'Total locations',
      trend: lang() === 'ar' ? `${dashData.total_shifts ?? 0} shifts نشطة` : `${dashData.total_shifts ?? 0} shift groups active`,
    },
    {
      icon: '🧩',
      tone: insights.fillPct >= 85 ? 'green' : insights.fillPct >= 60 ? 'orange' : 'red',
      value: `${insights.fillPct}%`,
      label: I18N.t('week_fill_rate') || 'Week fill rate',
      trend: lang() === 'ar' ? `${insights.emptyWeek} slot فاضي في الأسبوع الحالي` : `${insights.emptyWeek} empty slot(s) in current week`,
    },
    {
      icon: '✅',
      tone: insights.onTimePct >= 75 ? 'green' : insights.onTimePct >= 50 ? 'orange' : 'red',
      value: `${insights.onTimePct}%`,
      label: lang() === 'ar' ? 'الالتزام الشهري' : 'Monthly reliability',
      trend: lang() === 'ar' ? `${insights.confirmation.confirmed} تأكيد هذا الشهر` : `${insights.confirmation.confirmed} confirmations this month`,
    },
  ];

  return `
    <section>
      <div class="dash-section-title">
        <h2>${lang() === 'ar' ? 'لقطة سريعة' : 'Quick snapshot'}</h2>
        <div class="dash-section-caption">${lang() === 'ar' ? 'أرقام مختصرة لكن مفيدة فعلًا لاتخاذ قرار.' : 'Concise numbers that actually help you decide what to do next.'}</div>
      </div>
      <div class="dash-stat-grid">
        ${items.map(item => `
          <div class="dash-stat-card ${item.tone}">
            <div class="dash-stat-top">
              <span class="dash-stat-icon">${item.icon}</span>
            </div>
            <div class="dash-stat-value">${item.value}</div>
            <div class="dash-stat-label">${item.label}</div>
            <div class="dash-stat-trend">${item.trend}</div>
          </div>`).join('')}
      </div>
    </section>`;
}

function renderTodaySection(dashData, todayStats, allTeachersMap, weekData) {
  const todayStr = _today();
  const hasWeek = !!weekData?.day_plans;
  const status = dashData.current_week?.status ?? null;
  const fillPct = todayStats.total > 0 ? Math.round((todayStats.assigned / todayStats.total) * 100) : 0;
  const ringColor = fillPct >= 80 ? 'var(--primary)' : fillPct >= 40 ? 'var(--warning)' : 'var(--danger)';
  const circumference = 2 * Math.PI * 28;
  const dashOffset = circumference * (1 - fillPct / 100);

  const onDutyChips = [...todayStats.teachersOnDuty.values()].map(name => `<span class="td-chip td-chip--on">${escHtml(name)}</span>`).join('')
    || `<span class="td-chip td-chip--ok">${I18N.t('none_assigned') || 'None assigned'}</span>`;

  const offDuty = [...allTeachersMap.entries()]
    .filter(([id]) => !todayStats.teachersOnDuty.has(id))
    .map(([, name]) => name);
  const offDutyChips = offDuty.length > 0
    ? offDuty.map(name => `<span class="td-chip td-chip--off">${escHtml(name)}</span>`).join('')
    : `<span class="td-chip td-chip--ok">${I18N.t('all_teachers_have_duties_today') || 'All teachers have duties today'}</span>`;

  const noDataMsg = !hasWeek
    ? `<p style="color:var(--text-muted);font-size:0.85rem;padding:4px 0 12px">${I18N.t('week_data_unavailable') || 'Week data unavailable'}</p>`
    : '';

  return `
    <div class="section-card">
      <h3>📅 ${I18N.t('today_at_a_glance') || 'Today at a glance'}
        <span style="font-weight:600;color:var(--text-muted)">${_dayName(todayStr)} · ${statusPill(status)}</span>
      </h3>
      ${noDataMsg}
      <div class="today-grid">
        <div class="today-ring-wrap">
          <svg width="80" height="80" viewBox="0 0 80 80">
            <circle cx="40" cy="40" r="28" fill="none" stroke="#e5e7eb" stroke-width="8"/>
            <circle cx="40" cy="40" r="28" fill="none" stroke="${ringColor}" stroke-width="8"
              stroke-dasharray="${circumference.toFixed(1)}" stroke-dashoffset="${dashOffset.toFixed(1)}"
              stroke-linecap="round" transform="rotate(-90 40 40)"/>
            <text x="40" y="44" text-anchor="middle" font-size="16" font-weight="800" fill="${ringColor}">${fillPct}%</text>
          </svg>
          <div class="today-ring-label">${I18N.t('today_fill') || 'Today fill'}</div>
        </div>

        <div class="today-slot-counts">
          <div class="today-slot-row"><span class="today-slot-num" style="color:var(--text)">${todayStats.total}</span><span class="today-slot-lbl">${I18N.t('total_slots') || 'Total slots'}</span></div>
          <div class="today-slot-row"><span class="today-slot-num" style="color:var(--primary)">${todayStats.assigned}</span><span class="today-slot-lbl">${I18N.t('assigned') || 'Assigned'}</span></div>
          <div class="today-slot-row"><span class="today-slot-num" style="color:${todayStats.total - todayStats.assigned > 0 ? 'var(--danger)' : 'var(--primary)'}">${todayStats.total - todayStats.assigned}</span><span class="today-slot-lbl">${I18N.t('empty') || 'Empty'}</span></div>
        </div>

        <div class="today-teachers">
          <div class="today-teachers-label">✅ ${I18N.t('on_duty_today') || 'On duty today'} (${todayStats.teachersOnDuty.size})</div>
          <div class="today-chips">${onDutyChips}</div>
        </div>

        <div class="today-teachers">
          <div class="today-teachers-label ${offDuty.length > 0 ? 'warn' : ''}">${offDuty.length > 0 ? '⚠️' : '✅'} ${I18N.t('not_on_duty_today') || 'Not on duty today'} (${offDuty.length})</div>
          <div class="today-chips">${offDutyChips}</div>
        </div>
      </div>
    </div>`;
}

function renderWorkloadSection(dashData) {
  const counts = dashData.current_week?.teacher_counts ?? [];
  if (!counts.length) {
    return `
      <div class="section-card">
        <h3>⚖️ ${I18N.t('workload_distribution') || 'Workload distribution'}</h3>
        <p style="color:var(--text-muted);font-size:0.85rem">${I18N.t('no_assignments_yet_this_week') || 'No assignments yet this week'}</p>
      </div>`;
  }

  const maxCount = counts[0].count;
  const minCount = counts[counts.length - 1].count;
  const gap = maxCount - minCount;
  const balanced = gap <= 2;
  const noduty = (dashData.teachers_without_duties_this_week ?? []).length;
  const bars = counts.map((t, i) => {
    const pct = maxCount > 0 ? Math.round((t.count / maxCount) * 100) : 0;
    const isTop = i === 0;
    const isBot = i === counts.length - 1 && counts.length > 1;
    const badge = isTop ? ' 🥇' : isBot ? ' 🔻' : '';
    const color = isTop ? 'var(--primary)' : isBot ? '#f87171' : 'var(--nav)';
    return `
      <div class="bar-row">
        <span class="bar-label" title="${escHtml(t.teacher_name)}">${escHtml(t.teacher_name)}${badge}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${pct}%;background:${color}"></div></div>
        <span class="bar-count">${t.count}</span>
      </div>`;
  }).join('');

  const balanceColor = balanced ? 'var(--primary)' : gap <= 4 ? 'var(--warning)' : 'var(--danger)';
  const balanceLabel = balanced ? (I18N.t('well_balanced') || 'Well balanced') : gap <= 4 ? (I18N.t('slightly_uneven') || 'Slightly uneven') : (I18N.t('uneven_review_needed') || 'Uneven — review needed');

  return `
    <div class="section-card">
      <h3>⚖️ ${I18N.t('workload_distribution') || 'Workload distribution'}
        <span class="wl-badge" style="background:${balanceColor}12;color:${balanceColor};border:1px solid ${balanceColor}30;">${balanceLabel}</span>
      </h3>
      <div class="wl-summary">
        <div class="wl-pill">
          <span class="wl-pill-icon">🥇</span>
          <span class="wl-pill-name">${escHtml(counts[0]?.teacher_name ?? '—')}</span>
          <span class="wl-pill-val" style="color:var(--primary)">${counts[0]?.count ?? 0} ${lang() === 'ar' ? 'مناوبات' : 'duties'}</span>
          <span class="wl-pill-tag">${lang() === 'ar' ? 'الأعلى هذا الأسبوع' : 'Most this week'}</span>
        </div>
        ${counts.length > 1 ? `
          <div class="wl-pill">
            <span class="wl-pill-icon">🔻</span>
            <span class="wl-pill-name">${escHtml(counts[counts.length - 1]?.teacher_name ?? '—')}</span>
            <span class="wl-pill-val" style="color:#f87171">${counts[counts.length - 1]?.count ?? 0} ${lang() === 'ar' ? 'مناوبات' : 'duties'}</span>
            <span class="wl-pill-tag">${lang() === 'ar' ? 'الأقل ضمن المكلّفين' : 'Fewest with duties'}</span>
          </div>` : ''}
        ${noduty > 0 ? `
          <div class="wl-pill" style="border-color:#fee2e2">
            <span class="wl-pill-icon">⚠️</span>
            <span class="wl-pill-name">${noduty} ${lang() === 'ar' ? 'معلم' : noduty > 1 ? 'teachers' : 'teacher'}</span>
            <span class="wl-pill-val" style="color:var(--danger)">0 ${lang() === 'ar' ? 'مناوبات' : 'duties'}</span>
            <span class="wl-pill-tag">${lang() === 'ar' ? 'خارج التوزيع هذا الأسبوع' : 'No duties this week'}</span>
          </div>` : `
          <div class="wl-pill" style="border-color:#d1fae5">
            <span class="wl-pill-icon">✅</span>
            <span class="wl-pill-name">${lang() === 'ar' ? 'كل المعلمين' : 'All teachers'}</span>
            <span class="wl-pill-val" style="color:var(--primary)">${lang() === 'ar' ? 'داخل التوزيع' : 'covered'}</span>
            <span class="wl-pill-tag">${lang() === 'ar' ? 'لا يوجد أحد بدون مناوبات' : 'No idle teachers'}</span>
          </div>`}
      </div>
      <div style="margin-top:16px">
        <p style="font-size:0.8rem;font-weight:700;color:var(--text-muted);margin-bottom:8px">${lang() === 'ar' ? `فجوة التوزيع: ${gap}` : `Distribution gap: ${gap}`}</p>
        ${bars}
      </div>
    </div>`;
}

function renderConfirmationSection(reportData) {
  const { confirmed, onTime, late, noPoints } = _computeConfirmationStats(reportData);
  const { monthName, year } = _currentMonthYear();
  const onTimePct = confirmed > 0 ? Math.round((onTime / confirmed) * 100) : 0;
  const latePct = confirmed > 0 ? Math.round((late / confirmed) * 100) : 0;
  const noPointsPct = confirmed > 0 ? Math.round((noPoints / confirmed) * 100) : 0;
  const teachers = (reportData?.teachers ?? []).slice(0, 6);
  const maxConf = Math.max(...teachers.map(t => t.confirmations), 1);

  const teacherRows = teachers.length > 0
    ? teachers.map((t, i) => {
      const barPct = Math.round((t.confirmations / maxConf) * 100);
      const ptColor = t.total_points > 0 ? 'var(--primary)' : 'var(--text-muted)';
      return `
        <tr>
          <td>${rankBadge(i)}</td>
          <td style="font-weight:700">${escHtml(t.teacher_name)}</td>
          <td>
            <div style="display:flex;align-items:center;gap:6px">
              <div style="flex:1;background:#edf1f5;border-radius:999px;height:8px;overflow:hidden">
                <div style="width:${barPct}%;height:8px;background:var(--nav);border-radius:999px"></div>
              </div>
              <span style="font-size:0.8rem;font-weight:800;min-width:20px">${t.confirmations}</span>
            </div>
          </td>
          <td><span style="font-weight:800;color:${ptColor}">${t.total_points} ${I18N.t('pts_short') || 'pts'}</span></td>
          <td style="font-size:0.78rem"><span class="pill pill-green">${t.on_time}</span><span class="pill pill-yellow" style="margin-inline-start:4px">${t.late}</span></td>
        </tr>`;
    }).join('')
    : `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);padding:20px">${lang() === 'ar' ? `لا توجد بيانات تأكيد لـ ${monthName} ${year}` : `No confirmation data for ${monthName} ${year}`}</td></tr>`;

  const ringColor = onTimePct >= 75 ? 'var(--primary)' : onTimePct >= 50 ? 'var(--warning)' : 'var(--danger)';
  const circumference = 2 * Math.PI * 30;
  const dashOff = circumference * (1 - onTimePct / 100);

  return `
    <div class="section-card">
      <h3>✅ ${lang() === 'ar' ? 'الالتزام والتأكيدات' : 'Confirmation reliability'} <span style="font-weight:600;color:var(--text-muted)">${monthName} ${year}</span></h3>
      <div class="conf-layout">
        <div class="conf-ring-wrap">
          <svg width="88" height="88" viewBox="0 0 88 88">
            <circle cx="44" cy="44" r="30" fill="none" stroke="#e5e7eb" stroke-width="9"/>
            <circle cx="44" cy="44" r="30" fill="none" stroke="${ringColor}" stroke-width="9"
              stroke-dasharray="${circumference.toFixed(1)}" stroke-dashoffset="${dashOff.toFixed(1)}"
              stroke-linecap="round" transform="rotate(-90 44 44)"/>
            <text x="44" y="48" text-anchor="middle" font-size="16" font-weight="800" fill="${ringColor}">${onTimePct}%</text>
          </svg>
          <div style="text-align:center;font-size:0.78rem;color:var(--text-muted);margin-top:4px">${lang() === 'ar' ? 'نسبة الالتزام' : 'On-time rate'}</div>
          <div style="text-align:center;font-size:1.2rem;font-weight:900;color:var(--nav);margin-top:6px">${confirmed}</div>
          <div style="text-align:center;font-size:0.75rem;color:var(--text-muted)">${lang() === 'ar' ? 'إجمالي التأكيدات' : 'total confirmations'}</div>
        </div>
        <div class="conf-breakdown">
          <div class="conf-bar-row">
            <span class="conf-bar-label">${I18N.t('on_time') || 'On time'} <span style="font-size:0.72rem">(2 ${I18N.t('pts_short') || 'pts'})</span></span>
            <div class="conf-bar-track"><div class="conf-bar-fill" style="width:${onTimePct}%;background:var(--primary)"></div></div>
            <span class="conf-bar-num green">${onTime}</span>
            <span class="conf-bar-pct">${onTimePct}%</span>
          </div>
          <div class="conf-bar-row">
            <span class="conf-bar-label">${I18N.t('late_1_5m') || 'Late 1–5m'} <span style="font-size:0.72rem">(1 ${I18N.t('pt_short') || 'pt'})</span></span>
            <div class="conf-bar-track"><div class="conf-bar-fill" style="width:${latePct}%;background:var(--warning)"></div></div>
            <span class="conf-bar-num orange">${late}</span>
            <span class="conf-bar-pct">${latePct}%</span>
          </div>
          <div class="conf-bar-row">
            <span class="conf-bar-label">${I18N.t('no_points') || 'No points'} <span style="font-size:0.72rem">(0 ${I18N.t('pts_short') || 'pts'})</span></span>
            <div class="conf-bar-track"><div class="conf-bar-fill" style="width:${noPointsPct}%;background:var(--danger)"></div></div>
            <span class="conf-bar-num red">${noPoints}</span>
            <span class="conf-bar-pct">${noPointsPct}%</span>
          </div>
        </div>
      </div>
      ${teachers.length > 0 ? `
        <div style="margin-top:18px;overflow-x:auto">
          <p style="font-size:0.8rem;font-weight:700;color:var(--text-muted);margin-bottom:8px">${lang() === 'ar' ? 'أكثر المعلمين استقرارًا في التأكيد' : 'Most reliable teachers this month'}</p>
          <table class="teacher-mini-table">
            <thead>
              <tr>
                <th>#</th>
                <th>${I18N.t('teacher') || 'Teacher'}</th>
                <th>${lang() === 'ar' ? 'التأكيدات' : 'Confirmations'}</th>
                <th>${lang() === 'ar' ? 'النقاط' : 'Points'}</th>
                <th>${lang() === 'ar' ? 'حضور/تأخير' : 'On Time / Late'}</th>
              </tr>
            </thead>
            <tbody>${teacherRows}</tbody>
          </table>
        </div>` : ''}
    </div>`;
}

function renderWarningsSection(warnings) {
  if (!warnings?.length) return '';
  const items = warnings.map(w => `<li>${escHtml(w)}</li>`).join('');
  return `
    <div class="section-card" style="border-left:4px solid var(--warning)">
      <h3>⚠️ ${I18N.t('warnings') || 'Warnings'}</h3>
      <ul class="warn-list">${items}</ul>
    </div>`;
}

function renderWeekSection(stats, label) {
  if (!stats) {
    return `
      <div class="section-card">
        <h3>${escHtml(label)}</h3>
        <p style="color:var(--text-muted);font-size:0.85rem">${I18N.t('no_week_plan') || 'No week plan'}</p>
      </div>`;
  }

  const assignedPct = stats.total_slots > 0 ? Math.round((stats.assigned_slots / stats.total_slots) * 100) : 0;
  const miniStats = `
    <div class="mini-stat-grid">
      <div class="mini-stat"><div class="mini-stat-value">${stats.total_slots}</div><div class="mini-stat-label">${I18N.t('total_slots') || 'Total slots'}</div></div>
      <div class="mini-stat"><div class="mini-stat-value green">${stats.assigned_slots}</div><div class="mini-stat-label">${I18N.t('assigned') || 'Assigned'}</div></div>
      <div class="mini-stat"><div class="mini-stat-value ${stats.unassigned_slots > 0 ? 'red' : 'green'}">${stats.unassigned_slots}</div><div class="mini-stat-label">${I18N.t('empty') || 'Empty'}</div></div>
      <div class="mini-stat"><div class="mini-stat-value ${assignedPct >= 85 ? 'green' : assignedPct >= 60 ? 'orange' : 'red'}">${assignedPct}%</div><div class="mini-stat-label">${lang() === 'ar' ? 'نسبة التعبئة' : 'Fill rate'}</div></div>
    </div>`;

  let dayBarsHtml = '';
  if (stats.duties_per_day && Object.keys(stats.duties_per_day).length > 0) {
    const maxDay = Math.max(...Object.values(stats.duties_per_day), 1);
    const today = _today();
    dayBarsHtml = `
      <p style="font-size:0.8rem;font-weight:700;color:var(--text-muted);margin:14px 0 8px">${lang() === 'ar' ? 'التوزيع حسب اليوم' : 'By day'}</p>
      ${Object.entries(stats.duties_per_day).map(([d, c]) => {
        const pct = Math.round((c / maxDay) * 100);
        const isToday = d === today;
        return `
          <div class="bar-row">
            <span class="bar-label" style="${isToday ? 'color:var(--nav);font-weight:900' : ''}">${escHtml(_dayName(d))}${isToday ? ' ◀' : ''}</span>
            <div class="bar-track"><div class="bar-fill" style="width:${pct}%;${isToday ? 'background:var(--nav)' : ''}"></div></div>
            <span class="bar-count">${c}</span>
          </div>`;
      }).join('')}`;
  }

  const morningCount = stats.duties_per_type?.morning_endofday ?? 0;
  const breakCount = stats.duties_per_type?.break ?? 0;
  const maxType = Math.max(morningCount, breakCount, 1);
  const typeHtml = `
    <p style="font-size:0.8rem;font-weight:700;color:var(--text-muted);margin:14px 0 8px">${lang() === 'ar' ? 'حسب نوع المناوبة' : 'By duty type'}</p>
    ${barRow(I18N.t('morning_endofday') || 'Morning / End of day', morningCount, maxType)}
    ${barRow(I18N.t('break_duty') || 'Break duty', breakCount, maxType, 'break-type')}`;

  let topHtml = '';
  if (stats.teacher_counts?.length > 0) {
    const maxT = stats.teacher_counts[0].count || 1;
    topHtml = `
      <p style="font-size:0.8rem;font-weight:700;color:var(--text-muted);margin:14px 0 8px">${lang() === 'ar' ? 'أعلى المعلمين من حيث المناوبات' : 'Top teachers'}</p>
      ${stats.teacher_counts.slice(0, 6).map(t => barRow(t.teacher_name, t.count, maxT)).join('')}
      ${stats.teacher_counts.length > 6 ? `<p style="font-size:0.75rem;color:var(--text-muted);margin-top:4px">+${stats.teacher_counts.length - 6} ${lang() === 'ar' ? 'أكثر' : 'more'}</p>` : ''}`;
  }

  return `
    <div class="section-card">
      <h3>📅 ${escHtml(label)} — ${statusPill(stats.status)} <small style="font-weight:700;color:var(--text-muted)">v${stats.version ?? 1}</small></h3>
      ${miniStats}
      ${dayBarsHtml}
      ${typeHtml}
      ${topHtml}
    </div>`;
}

function renderTeacherInsights(dashData) {
  const top = dashData.top_teachers_this_week ?? [];
  const noDuty = dashData.teachers_without_duties_this_week ?? [];

  const topHtml = top.length > 0 ? `
    <div class="section-card">
      <h3>🏆 ${lang() === 'ar' ? 'الأكثر نشاطًا هذا الأسبوع' : 'Most active this week'}</h3>
      <table class="teacher-mini-table">
        <thead><tr><th>#</th><th>${I18N.t('teacher') || 'Teacher'}</th><th>${I18N.t('duties') || 'Duties'}</th></tr></thead>
        <tbody>
          ${top.map((t, i) => `
            <tr>
              <td style="width:32px">${rankBadge(i)}</td>
              <td style="font-weight:700">${escHtml(t.teacher_name)}</td>
              <td><span style="font-size:1.05rem;font-weight:900;color:var(--primary)">${t.count}</span> <span style="font-size:0.75rem;color:var(--text-muted)">${lang() === 'ar' ? 'مناوبات' : 'duties'}</span></td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>` : '<div></div>';

  let noDutyHtml = '<div></div>';
  if (noDuty.length > 0) {
    const chips = noDuty.map(t => `<span class="no-duty-chip">${escHtml(t.teacher_name)}</span>`).join('');
    noDutyHtml = `
      <div class="section-card" style="border-left:4px solid var(--warning)">
        <h3>📋 ${lang() === 'ar' ? 'بدون مناوبات هذا الأسبوع' : 'No duties this week'}
          <span style="background:#fee2e2;color:#b91c1c;border-radius:999px;padding:4px 9px;font-size:.75rem;font-weight:900;margin-inline-start:8px">${noDuty.length}</span>
        </h3>
        <p style="font-size:0.82rem;color:var(--text-muted);margin-bottom:10px">${lang() === 'ar' ? 'الأسماء دي محتاجة دخول في الجدول لو الهدف توزيع عادل.' : 'These teachers should be considered if you want a fairer roster.'}</p>
        <div>${chips}</div>
      </div>`;
  } else if ((dashData.current_week?.teacher_counts?.length ?? 0) > 0) {
    noDutyHtml = `
      <div class="section-card" style="border-left:4px solid var(--primary)">
        <h3>✅ ${lang() === 'ar' ? 'تغطية كاملة' : 'Full coverage'}</h3>
        <p style="font-size:0.85rem;color:var(--text-muted)">${lang() === 'ar' ? 'كل المعلمين النشطين لهم على الأقل مناوبة واحدة هذا الأسبوع.' : 'All active teachers have at least one duty this week.'}</p>
      </div>`;
  }

  return `<div class="two-col">${topHtml}${noDutyHtml}</div>`;
}

/* ─── Main render ────────────────────────────────────────────────────────── */
function renderDashboard(dashData, weekData, reportData) {
  const todayStr = _today();
  const allTeachersMap = _buildAllTeachersMap(dashData);
  const todayStats = _computeToday(weekData, todayStr);

  const html = [
    renderHeroSection(dashData, weekData, reportData),
    renderPriorityStrip(dashData, weekData, reportData),
    renderHeroStats(dashData, weekData, reportData),
    `<div class="two-col">${renderTodaySection(dashData, todayStats, allTeachersMap, weekData)}${renderWarningsSection(dashData.warnings) || `<div class="section-card"><h3>🧭 ${lang() === 'ar' ? 'ملحوظة سريعة' : 'Quick note'}</h3><p style="font-size:0.85rem;color:var(--text-muted)">${lang() === 'ar' ? 'مافيش تحذيرات من النظام حاليًا، فركّز على التغطية والتوازن.' : 'No system warnings right now, so focus on coverage and balance.'}</p></div>`}</div>`,
    `<div class="two-col">${renderWorkloadSection(dashData)}${renderConfirmationSection(reportData)}</div>`,
    `<div class="two-col">${renderWeekSection(dashData.current_week, I18N.t('current_week') || 'Current week')}${renderWeekSection(dashData.next_week, I18N.t('next_week') || 'Next week')}</div>`,
    renderTeacherInsights(dashData),
  ].join('');

  document.getElementById('dashContent').innerHTML = html;
}

/* ─── Data loading ───────────────────────────────────────────────────────── */
async function loadDashboard() {
  const content = document.getElementById('dashContent');
  if (!content) return;

  content.innerHTML = `
    <div class="dash-loading">
      <div class="spinner"></div>
      <p>${lang() === 'ar' ? 'جارٍ تحميل لوحة التحكم…' : 'Loading dashboard…'}</p>
    </div>`;

  try {
    const weekStart = _weekStart();
    const parts = _partsInMuscat();
    const year = Number(parts.year);
    const month = Number(parts.month);

    const [dashRes, weekRes, reportRes] = await Promise.all([
      apiFetch('/admin/dashboard'),
      apiFetch(`/weeks/${weekStart}`),
      apiFetch(`/admin/reports/monthly-points?year=${year}&month=${month}`),
    ]);

    if (!dashRes?.ok) {
      content.innerHTML = `
        <div class="dash-error">
          <div class="error-icon">⚠️</div>
          <p>${lang() === 'ar' ? 'تعذّر تحميل بيانات الداشبورد' : 'Could not load dashboard data'} (${dashRes?.status ?? 'network'})</p>
          <button class="btn btn-primary btn-sm" onclick="loadDashboard()">${I18N.t('retry') || 'Retry'}</button>
        </div>`;
      return;
    }

    const dashData = await dashRes.json();
    const weekData = weekRes?.ok ? await weekRes.json() : null;
    const reportData = reportRes?.ok ? await reportRes.json() : null;
    renderDashboard(dashData, weekData, reportData);
  } catch (err) {
    console.error('loadDashboard failed:', err);
    content.innerHTML = `
      <div class="dash-error">
        <div class="error-icon">⚠️</div>
        <p>${I18N.t('error_generic') || 'Something went wrong'}</p>
        <button class="btn btn-primary btn-sm" onclick="loadDashboard()">${I18N.t('retry') || 'Retry'}</button>
      </div>`;
  }
}

async function refreshDashboard() {
  const btn = document.getElementById('refreshBtn');
  const content = document.getElementById('dashContent');
  if (btn) btn.classList.add('spinning');
  if (content) { content.style.opacity = '0.55'; content.style.pointerEvents = 'none'; }
  await loadDashboard();
  if (content) { content.style.opacity = ''; content.style.pointerEvents = ''; }
  if (btn) btn.classList.remove('spinning');
  showToast(I18N.t('dashboard_refreshed') || (lang() === 'ar' ? 'تم تحديث لوحة التحكم' : 'Dashboard refreshed'), 'info');
}

/* ─── Auto-init ──────────────────────────────────────────────────────────── */
async function initDashboard() {
  await I18N.init();
  guardPage();
  await loadDashboard();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initDashboard);
} else {
  initDashboard();
}
