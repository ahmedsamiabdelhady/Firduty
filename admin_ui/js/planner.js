/**
 * planner.js — Firduty Admin Week Planner
 * Handles: week loading, day/shift tabs, drag-and-drop, slot management.
 * Duty-type aware: break duties show grade/class label instead of location.
 *
 * Auth is handled by auth.js (loaded before this script in planner.html).
 * Use apiFetch() for all API calls — it attaches the token and handles 401.
 *
 * Changes:
 * - Shift time inline editor: click ✏️ on any shift tab panel header to edit
 *   start_time / end_time. Calls PUT /shifts/{id} — change applies to ALL days.
 * - Break duty slots: grade_class is displayed as a static read-only badge.
 *   No input/dropdown. The class label comes from the pre-seeded assignment.
 *   Drag-and-drop preserves the slot's existing grade_class automatically.
 */

let currentWeekData = null;
let allTeachers = [];
let pendingAssignments = {};   // slId → { slotIdx → { teacher_id, grade_class } }
let pendingSlots = {};         // key → { dayDate, shiftId, locationId, slotsCount }
let selectedDate = null;       // the exact day chosen by admin in the date picker
let lang = () => I18N.getLang();

// ─── Utilities ────────────────────────────────────────────────────────────────

function byId(id) {
  return document.getElementById(id);
}

function showEl(el, display = '') {
  if (el) el.style.display = display;
}

function hideEl(el) {
  if (el) el.style.display = 'none';
}

function showToast(message, type = 'success') {
  const c = byId('toastContainer');
  if (!c) return;
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = message;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

function formatDateLocal(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, '0');
  const d = String(date.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

function parseLocalDate(dateStr) {
  return new Date(`${dateStr}T12:00:00`);
}

function getWeekStartFromDate(dateStr) {
  const d = parseLocalDate(dateStr);
  d.setDate(d.getDate() - d.getDay()); // Sunday
  return formatDateLocal(d);
}

function getCurrentLocalDate() {
  return formatDateLocal(new Date());
}

function getCurrentSunday() {
  return getWeekStartFromDate(getCurrentLocalDate());
}

function getPreviousSunday() {
  const currentSunday = parseLocalDate(getCurrentSunday());
  currentSunday.setDate(currentSunday.getDate() - 7);
  return formatDateLocal(currentSunday);
}

function applyWeekInputLimits() {
  const weekInput = byId('weekStartInput');
  if (!weekInput) return;
  const minDate = getPreviousSunday();
  const today = getCurrentLocalDate();
  weekInput.min = minDate;
  if (!weekInput.value) {
    weekInput.value = today >= minDate ? today : minDate;
  } else if (weekInput.value < minDate) {
    weekInput.value = minDate;
  }
}

function syncWeekInputWithSelectedDate() {
  const weekInput = byId('weekStartInput');
  if (!weekInput) return;
  weekInput.value = selectedDate || getCurrentLocalDate();
}

function setPlannerBusy(isBusy, message = '') {
  const overlay   = byId('plannerBusyOverlay');
  const textEl    = byId('plannerLoadingText');
  const barEl     = byId('plannerLoadingBar');
  const plannerMain = document.querySelector('.planner-main');
  if (textEl) textEl.textContent = message || I18N.t('loading') || 'Loading...';
  if (overlay) overlay.style.display = isBusy ? 'flex' : 'none';
  if (barEl) barEl.classList.toggle('is-active', !!isBusy);
  if (plannerMain) plannerMain.style.pointerEvents = isBusy ? 'none' : '';
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ─── Teachers ─────────────────────────────────────────────────────────────────

async function loadTeachers() {
  const listEl    = byId('teacherList');
  const loadingEl = byId('teachersLoading');
  try {
    const res = await apiFetch('/teachers/');
    if (!res || !res.ok) return;
    allTeachers = await res.json();
    if (loadingEl) loadingEl.style.display = 'none';
    if (listEl) {
      listEl.innerHTML = allTeachers.map(t => `
        <div class="teacher-list-item"
             data-teacher-id="${t.id}"
             data-teacher-name="${escHtml(t.name)}">
          ${escHtml(t.name)}
        </div>
      `).join('');
    }
  } catch (err) {
    console.error('loadTeachers failed:', err);
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────

async function initPlanner() {
  guardPage();
  applyWeekInputLimits();
  await loadTeachers();
  await loadWeek();
}

// ─── Week Loading ─────────────────────────────────────────────────────────────

async function loadWeek() {
  const plannerLoading = byId('plannerLoading');
  const noPlanMsg      = byId('noPlanMsg');
  const dayTabs        = byId('dayTabs');
  const dayPanels      = byId('dayPanels');

  const weekInput = byId('weekStartInput');
  const pickedDate = weekInput ? weekInput.value : '';
  if (!pickedDate) return;

  selectedDate = pickedDate;
  const weekStart = getWeekStartFromDate(pickedDate);

  pendingAssignments = {};
  pendingSlots = {};

  try {
    showEl(plannerLoading);
    hideEl(noPlanMsg);
    if (dayTabs)   dayTabs.innerHTML   = '';
    if (dayPanels) dayPanels.innerHTML = '';

    const res = await apiFetch(`/weeks/${weekStart}`);
    if (!res) { currentWeekData = null; showEl(noPlanMsg, 'block'); updateStatusBadge(null); return; }

    if (res.status === 404) {
      currentWeekData = null;
      showEl(noPlanMsg, 'block');
      if (dayPanels) dayPanels.innerHTML = `<p style="color:#6c757d;text-align:center;margin-top:40px" data-i18n="no_week"></p>`;
      I18N.applyTranslations();
      updateStatusBadge(null);
      showToast(I18N.t('no_week') || 'No plan found for this week', 'info');
      return;
    }

    if (!res.ok) {
      currentWeekData = null; showEl(noPlanMsg, 'block'); updateStatusBadge(null);
      showToast(await getApiErrorMessage(res, I18N.t('error_generic')), 'error');
      return;
    }

    currentWeekData = await res.json();
    renderWeek();
  } catch (err) {
    console.error('loadWeek failed:', err);
    currentWeekData = null; showEl(noPlanMsg, 'block'); updateStatusBadge(null);
    showToast(I18N.t('error_generic'), 'error');
  } finally {
    hideEl(plannerLoading);
  }
}

function updateStatusBadge(status) {
  const badge  = byId('weekStatusBadge');
  const vBadge = byId('weekVersionBadge');
  if (!badge || !vBadge) return;
  if (!status) { badge.style.display = 'none'; vBadge.textContent = ''; return; }
  badge.style.display = 'inline';
  badge.className = `week-status-badge status-${status}`;
  badge.textContent = I18N.t(status);
  vBadge.textContent = currentWeekData ? `v${currentWeekData.version}` : '';
}

// ─── Week Rendering ───────────────────────────────────────────────────────────

const DAY_KEYS = ['day_sun', 'day_mon', 'day_tue', 'day_wed', 'day_thu'];

function renderWeek() {
  if (!currentWeekData?.day_plans) return;
  updateStatusBadge(currentWeekData.status);

  const tabsEl    = byId('dayTabs');
  const panelsEl  = byId('dayPanels');
  const noPlanMsg = byId('noPlanMsg');
  if (!tabsEl || !panelsEl) return;

  tabsEl.innerHTML   = '';
  panelsEl.innerHTML = '';
  hideEl(noPlanMsg);

  const activeIdx = getActiveDayIndex();

  currentWeekData.day_plans.forEach((dayPlan, idx) => {
    const dayDate  = new Date(dayPlan.date + 'T12:00:00');
    const dayOfWeek = dayDate.getDay();
    const dayLabel  = I18N.t(DAY_KEYS[dayOfWeek] || `Day ${idx}`);

    const tab = document.createElement('button');
    tab.className = 'tab-btn' + (idx === activeIdx ? ' active' : '');
    tab.textContent = dayLabel + (dayPlan.is_published ? ' ✔' : '');
    tab.onclick = () => switchDayTab(idx);
    tabsEl.appendChild(tab);

    const panel = document.createElement('div');
    panel.className = 'tab-panel' + (idx === activeIdx ? ' active' : '');
    panel.innerHTML = renderDayPanel(dayPlan, dayPlan.is_editable);
    if (idx !== activeIdx) panel.style.display = 'none';
    panelsEl.appendChild(panel);
  });

  initDragAndDrop();
}

function getActiveDayIndex() {
  if (!currentWeekData?.day_plans?.length) return 0;
  const exactMatch = currentWeekData.day_plans.findIndex(d => d.date === selectedDate);
  if (exactMatch >= 0) return exactMatch;
  const today = getCurrentLocalDate();
  const todayMatch = currentWeekData.day_plans.findIndex(d => d.date === today);
  return todayMatch >= 0 ? todayMatch : 0;
}

function switchDayTab(idx) {
  document.querySelectorAll('.tab-btn').forEach((b, i) => b.classList.toggle('active', i === idx));
  document.querySelectorAll('.tab-panel').forEach((p, i) => {
    const isActive = i === idx;
    p.classList.toggle('active', isActive);
    p.style.display = isActive ? 'block' : 'none';
  });
  const day = currentWeekData?.day_plans[idx];
  if (day) {
    selectedDate = day.date;
    const weekInput = byId('weekStartInput');
    if (weekInput) weekInput.value = day.date;
  }
}

function renderDayPanel(dayPlan, isEditable) {
  const shiftMap = {};
  dayPlan.shift_locations.forEach(sl => {
    if (!shiftMap[sl.shift_id]) shiftMap[sl.shift_id] = { shift: sl.shift, locations: [] };
    shiftMap[sl.shift_id].locations.push(sl);
  });
  const shifts = Object.values(shiftMap).sort((a, b) => a.shift.order - b.shift.order);

  if (!shifts.length) return `<p style="color:#999;margin-top:20px;text-align:center">Loading day slots...</p>`;

  const dayBadge = isEditable
    ? `<span style="font-size:0.8rem;color:#15803d;background:#dcfce7;padding:4px 10px;border-radius:999px">${I18N.t('editable') || 'Editable'}</span>`
    : `<span style="font-size:0.8rem;color:#991b1b;background:#fee2e2;padding:4px 10px;border-radius:999px">${I18N.t('locked') || 'Locked'}</span>`;

  const publishBtn = dayPlan.is_published
    ? `<span style="font-size:0.8rem;color:#166534;background:#dcfce7;padding:6px 10px;border-radius:999px">✅ ${I18N.t('published') || 'Published'}</span>`
    : `<button class="btn btn-success btn-sm" id="publish-day-btn-${dayPlan.date}" onclick="publishDay('${dayPlan.date}')">${I18N.t('publish_day') || 'Publish Day'}</button>`;

  // Shift tab buttons
  const shiftTabsHtml = shifts.map((s, i) => {
    const dutyBadge = s.shift.duty_type === 'break'
      ? `<span style="font-size:0.7rem;background:#ede9fe;color:#5b21b6;border-radius:8px;padding:1px 7px;margin-inline-start:6px">${I18N.t('break')}</span>`
      : '';
    return `
      <button class="shift-tab-btn${i === 0 ? ' active' : ''}"
              onclick="switchShiftTab('${dayPlan.date}', ${s.shift.id})"
              data-shift-id="${s.shift.id}"
              data-day-date="${dayPlan.date}">
        ${lang() === 'ar' ? s.shift.name_ar : s.shift.name_en}
        ${dutyBadge}
        <small style="opacity:0.7">${s.shift.start_time.slice(0, 5)}</small>
      </button>
    `;
  }).join('');

  // Shift panel bodies — each includes an inline time editor header
  const shiftPanelsHtml = shifts.map((s, i) => {
    const startFmt = s.shift.start_time.slice(0, 5);
    const endFmt   = s.shift.end_time.slice(0, 5);
    const shiftName = lang() === 'ar' ? s.shift.name_ar : s.shift.name_en;

    // Time editor header (always visible, applies to all days)
    const timeHeader = `
      <div class="shift-time-header" id="shift-time-header-${s.shift.id}">
        <span class="shift-time-label">
          <strong>${escHtml(shiftName)}</strong>
          <span class="shift-time-display" id="shift-time-display-${s.shift.id}">
            ${startFmt} – ${endFmt}
          </span>
        </span>
        <button class="btn-edit-time"
                title="${I18N.t('edit_shift_time') || 'Edit Time'}"
                onclick="openEditShiftTime(${s.shift.id}, '${startFmt}', '${endFmt}')">✏️</button>
      </div>
    `;

    return `
      <div class="shift-panel${i === 0 ? ' active' : ''}"
           id="shift-panel-${dayPlan.date}-${s.shift.id}"
           style="${i === 0 ? 'display:block' : 'display:none'}">
        ${timeHeader}
        <div class="locations-grid">
          ${s.locations.map(sl => renderLocationColumn(dayPlan.date, sl, isEditable)).join('')}
        </div>
      </div>
    `;
  }).join('');

  return `
    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <strong>${dayPlan.date}</strong>
        ${dayBadge}
      </div>
      <div>${publishBtn}</div>
    </div>
    <div class="shift-tabs" id="shift-tabs-${dayPlan.date}">${shiftTabsHtml}</div>
    ${shiftPanelsHtml}
  `;
}

function switchShiftTab(dayDate, shiftId) {
  const container = byId(`shift-tabs-${dayDate}`);
  if (!container) return;
  container.querySelectorAll('.shift-tab-btn').forEach(b => {
    b.classList.toggle('active', parseInt(b.dataset.shiftId, 10) === shiftId);
  });
  document.querySelectorAll(`[id^="shift-panel-${dayDate}-"]`).forEach(p => {
    p.style.display = p.id === `shift-panel-${dayDate}-${shiftId}` ? 'block' : 'none';
  });
}

// ─── Shift Time Inline Editor ─────────────────────────────────────────────────
//
// Clicking ✏️ opens a floating card anchored to the shift time header.
// PUT /shifts/{id} updates the Shift record, which is shared across all days.
// After saving, the week is reloaded so every day panel reflects the new time.

function openEditShiftTime(shiftId, currentStart, currentEnd) {
  closeEditShiftTime(); // close any previously open editor

  const headerId = `shift-time-header-${shiftId}`;
  const headerEl = byId(headerId);
  if (!headerEl) return;

  const card = document.createElement('div');
  card.id = 'shiftTimeEditor';
  card.className = 'shift-time-editor-card';
  card.innerHTML = `
    <p class="shift-time-editor-note">⚠️ ${I18N.t('time_applies_all_days') || 'This change applies to all days of the week'}</p>
    <div class="shift-time-editor-fields">
      <label>
        ${I18N.t('shift_start_time') || 'Start Time'}
        <input type="time" id="editShiftStart" value="${currentStart}">
      </label>
      <label>
        ${I18N.t('shift_end_time') || 'End Time'}
        <input type="time" id="editShiftEnd" value="${currentEnd}">
      </label>
    </div>
    <div class="shift-time-editor-actions">
      <button class="btn btn-primary btn-sm" onclick="saveShiftTime(${shiftId})">${I18N.t('save_shift_time') || 'Save'}</button>
      <button class="btn btn-secondary btn-sm" onclick="closeEditShiftTime()">${I18N.t('cancel') || 'Cancel'}</button>
    </div>
  `;

  // Insert right after the header element
  headerEl.insertAdjacentElement('afterend', card);
  card.querySelector('#editShiftStart')?.focus();
}

async function saveShiftTime(shiftId) {
  const startInput = byId('editShiftStart');
  const endInput   = byId('editShiftEnd');
  if (!startInput || !endInput) return;

  const start_time = startInput.value;
  const end_time   = endInput.value;
  if (!start_time || !end_time) {
    showToast(I18N.t('error_generic'), 'error');
    return;
  }

  const saveBtn = document.querySelector('#shiftTimeEditor .btn-primary');
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = '...'; }

  try {
    const res = await apiFetch(`/shifts/${shiftId}`, {
      method: 'PUT',
      body: JSON.stringify({ start_time: start_time + ':00', end_time: end_time + ':00' }),
    });

    if (!res || !res.ok) {
      const msg = await getApiErrorMessage(res, I18N.t('error_generic'));
      showToast(msg, 'error');
      if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = I18N.t('save_shift_time') || 'Save'; }
      return;
    }

    closeEditShiftTime();
    showToast(I18N.t('success_shift_time_saved') || 'Shift time updated successfully');

    // Reload the week so all day panels reflect the new time
    await loadWeek();
  } catch (err) {
    console.error('saveShiftTime failed:', err);
    showToast(I18N.t('error_generic'), 'error');
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = I18N.t('save_shift_time') || 'Save'; }
  }
}

function closeEditShiftTime() {
  const existing = byId('shiftTimeEditor');
  if (existing) existing.remove();
}

// Close editor if clicking outside of it
document.addEventListener('click', (e) => {
  const editor = byId('shiftTimeEditor');
  if (editor && !editor.contains(e.target) && !e.target.classList.contains('btn-edit-time')) {
    closeEditShiftTime();
  }
});

// ─── Location Column & Slot Rendering ────────────────────────────────────────

/**
 * Returns the first letter(s) of a teacher's name for an avatar circle.
 * "Ahmed Al-Rashidi" → "A"   "Sara Nasser" → "S"
 */
function _initials(name) {
  if (!name) return '?';
  return name.trim().charAt(0).toUpperCase();
}

function renderLocationColumn(dayDate, sl, isEditable) {
  const isBreak = sl.duty_type === 'break' || sl.shift.duty_type === 'break';

  // Column title
  let colTitle;
  if (isBreak) {
    colTitle = `<span class="col-title-break">${lang() === 'ar' ? sl.shift.name_ar : sl.shift.name_en}</span>`;
  } else {
    colTitle = sl.location
      ? escHtml(lang() === 'ar' ? sl.location.name_ar : sl.location.name_en)
      : '—';
  }

  // Fill metrics
  const total  = sl.slots_count;
  const filled = sl.assignments.filter(a => getEffectiveAssignment(sl.id, a.slot_index, a).teacher_id != null).length;
  const pct    = total > 0 ? Math.round((filled / total) * 100) : 0;
  const colStatus = filled === 0 ? 'col-empty' : filled < total ? 'col-partial' : 'col-full';

  // Render each slot
  const slots = [];
  for (let i = 0; i < total; i++) {
    const assignment = sl.assignments.find(a => a.slot_index === i);
    slots.push(renderSlot(sl.id, i, assignment, isBreak, isEditable));
  }

  return `
    <div class="location-column ${colStatus}${isBreak ? ' location-column-break' : ''}"
         data-sl-id="${sl.id}"
         data-day="${dayDate}"
         data-shift="${sl.shift_id}"
         data-loc="${sl.location_id || ''}"
         data-duty-type="${isBreak ? 'break' : 'morning_endofday'}"
         data-editable="${isEditable ? 'true' : 'false'}">

      <div class="location-header">
        <span class="location-name" title="${colTitle}">${colTitle}</span>
        ${!isBreak ? `
        <div class="slot-controls">
          <button class="btn-slot btn-slot-sub"
                  ${!isEditable ? 'disabled' : ''}
                  onclick="changeSlots('${dayDate}', ${sl.shift_id}, ${sl.location_id || 'null'}, -1)">−</button>
          <span class="slot-count" id="slot-count-${sl.id}">${total}</span>
          <button class="btn-slot btn-slot-add"
                  ${!isEditable ? 'disabled' : ''}
                  onclick="changeSlots('${dayDate}', ${sl.shift_id}, ${sl.location_id || 'null'}, +1)">+</button>
        </div>` : `<span class="col-fill-label" id="col-fill-label-${sl.id}" style="font-size:0.78rem;font-weight:600;color:var(--text-muted)">${filled}/${total}</span>`}
      </div>

      <div class="col-fill-bar">
        <div class="col-fill-bar-track">
          <div class="col-fill-bar-fill" style="width:${pct}%"></div>
        </div>
        ${!isBreak ? `<span class="col-fill-label" id="col-fill-label-${sl.id}">${filled}/${total}</span>` : ''}
      </div>

      <div class="slots-list${isBreak ? ' slots-list-break' : ''}"
           id="slots-${sl.id}"
           data-sl-id="${sl.id}"
           data-duty-type="${isBreak ? 'break' : 'morning_endofday'}">
        ${slots.join('')}
      </div>
    </div>
  `;
}

/**
 * renderSlot — redesigned for clarity:
 *
 * FILLED slot:
 *   - Initials avatar circle (colour-coded by name hash)
 *   - Teacher name (truncated, full name in title tooltip)
 *   - Slot number badge
 *   - ✕ remove button — hidden by CSS, revealed on hover
 *   - For break: grade class badge (the slot's identity)
 *
 * EMPTY slot (non-break):
 *   - Dashed drop-zone card with arrow-down icon + "Drop teacher" hint
 *   - Slot number badge
 *
 * EMPTY slot (break):
 *   - The grade class IS the identity of the slot — shown large and prominent
 *   - Arrow-down drop-zone hint underneath
 */
function renderSlot(slId, slotIdx, assignment, isBreak, isEditable = true) {
  const slotNum = slotIdx + 1;
  const slotNumBadge = `<span class="slot-num">${slotNum}</span>`;

  // ── BREAK duty slot — compact grid card ─────────────────────────────────
  // The grade_class is the identity. Shown large at top; teacher name below.
  if (isBreak) {
    const gradeClass = assignment?.grade_class ?? null;
    const gradeLabel = gradeClass ? escHtml(gradeClass) : `#${slotNum}`;

    if (assignment && assignment.teacher_id) {
      const name    = assignment.teacher_name || '';
      const initial = _initials(name);
      const hue     = (assignment.teacher_id * 47) % 360;
      const removeBtn = isEditable
        ? `<button class="slot-remove-btn" onclick="removeTeacher(${slId}, ${slotIdx})" title="Remove">✕</button>`
        : '';

      return `
        <div class="slot-item slot-filled slot-break-card" data-sl-id="${slId}" data-slot-idx="${slotIdx}" data-teacher-id="${assignment.teacher_id}">
          <div class="break-card-class">${gradeLabel}</div>
          <div class="break-card-teacher">
            <span class="teacher-avatar" style="--avatar-hue:${hue}deg">${escHtml(initial)}</span>
            <span class="teacher-name" title="${escHtml(name)}">${escHtml(name)}</span>
            ${removeBtn}
          </div>
        </div>
      `;
    }

    // Empty break slot
    return `
      <div class="slot-item slot-empty slot-break-card slot-break-empty" data-sl-id="${slId}" data-slot-idx="${slotIdx}" data-teacher-id="">
        <div class="break-card-class">${gradeLabel}</div>
        ${isEditable
          ? `<div class="slot-drop-zone"><span class="slot-drop-icon">↓</span><span class="slot-drop-text">${I18N.t('no_teacher') || 'Drop'}</span></div>`
          : `<span class="slot-locked-text">—</span>`
        }
      </div>
    `;
  }

  // ── NON-BREAK slot — original full-width card ────────────────────────────
  if (assignment && assignment.teacher_id) {
    const name    = assignment.teacher_name || '';
    const initial = _initials(name);
    const hue     = (assignment.teacher_id * 47) % 360;
    const removeBtn = isEditable
      ? `<button class="slot-remove-btn" onclick="removeTeacher(${slId}, ${slotIdx})" title="Remove">✕</button>`
      : '';

    return `
      <div class="slot-item slot-filled" data-sl-id="${slId}" data-slot-idx="${slotIdx}" data-teacher-id="${assignment.teacher_id}">
        ${slotNumBadge}
        <div class="slot-inner">
          <div class="slot-row">
            <span class="teacher-avatar" style="--avatar-hue:${hue}deg">${escHtml(initial)}</span>
            <span class="teacher-name" title="${escHtml(name)}">${escHtml(name)}</span>
            ${removeBtn}
          </div>
        </div>
      </div>
    `;
  }

  // Non-break empty: dashed drop zone
  return `
    <div class="slot-item slot-empty" data-sl-id="${slId}" data-slot-idx="${slotIdx}" data-teacher-id="">
      ${slotNumBadge}
      ${isEditable
        ? `<div class="slot-drop-zone">
             <span class="slot-drop-icon">↓</span>
             <span class="slot-drop-text">${I18N.t('no_teacher') || 'Drop teacher'}</span>
           </div>`
        : `<span class="slot-locked-text">—</span>`
      }
    </div>
  `;
}

// ─── Grade Class (no longer user-editable, but updateGradeClass kept for
//     any programmatic callers during drag-drop grade preservation) ──────────

function updateGradeClass(slId, slotIdx, value) {
  if (!pendingAssignments[slId]) pendingAssignments[slId] = {};
  if (!pendingAssignments[slId][slotIdx]) pendingAssignments[slId][slotIdx] = {};
  pendingAssignments[slId][slotIdx].grade_class = value;
}

/**
 * Recomputes and updates the fill bar + column status class for a given slId.
 * Called after any in-place slot mutation (add teacher, remove teacher).
 */
function _refreshFillBar(slId) {
  const list = byId(`slots-${slId}`);
  const col  = list?.closest('.location-column');
  const bar  = col?.querySelector('.col-fill-bar-fill');
  const label = byId(`col-fill-label-${slId}`);
  const countEl = byId(`slot-count-${slId}`);
  if (!list || !col) return;

  const isBreak = list.dataset.dutyType === 'break';
  // For break cols, total comes from slot count in DOM; for non-break from the counter span
  const total  = isBreak
    ? list.querySelectorAll('.slot-item').length
    : parseInt(countEl?.textContent || '0', 10);
  const filled = list.querySelectorAll('.slot-item.slot-filled').length;
  const pct    = total > 0 ? Math.round((filled / total) * 100) : 0;

  if (bar)   bar.style.width = `${pct}%`;
  if (label) label.textContent = `${filled}/${total}`;

  col.classList.remove('col-empty', 'col-partial', 'col-full');
  col.classList.add(filled === 0 ? 'col-empty' : filled < total ? 'col-partial' : 'col-full');
}

// ─── Drag & Drop ──────────────────────────────────────────────────────────────

function findShiftLocationInCurrentWeek(slId) {
  if (!currentWeekData?.day_plans) return null;
  for (const day of currentWeekData.day_plans) {
    for (const sl of day.shift_locations || []) {
      if (sl.id === slId) return { day, sl };
    }
  }
  return null;
}

function getEffectiveAssignment(slId, slotIdx, fallbackAssignment = null) {
  const pending = pendingAssignments?.[slId]?.[slotIdx];
  if (pending) {
    return {
      teacher_id: pending.teacher_id ?? null,
      grade_class: pending.grade_class ?? fallbackAssignment?.grade_class ?? null,
    };
  }
  return fallbackAssignment
    ? { teacher_id: fallbackAssignment.teacher_id ?? null, grade_class: fallbackAssignment.grade_class ?? null }
    : { teacher_id: null, grade_class: null };
}

function isTeacherAssignedInSameShift(slId, teacherId) {
  const found = findShiftLocationInCurrentWeek(slId);
  if (!found || !teacherId) return false;
  const { day, sl } = found;
  for (const candidate of day.shift_locations || []) {
    if (candidate.shift_id !== sl.shift_id) continue;
    for (const assignment of candidate.assignments || []) {
      const effective = getEffectiveAssignment(candidate.id, assignment.slot_index, assignment);
      if (effective.teacher_id === teacherId) return true;
    }
  }
  return false;
}

async function getApiErrorMessage(res, fallbackMessage) {
  if (!res) return fallbackMessage;
  try {
    const data = await res.json();
    return data?.detail || data?.message || fallbackMessage;
  } catch (_) {
    return fallbackMessage;
  }
}

function initDragAndDrop() {
  const sidebar = byId('teacherList');
  if (sidebar && typeof Sortable !== 'undefined' && !sidebar.dataset.sortableInit) {
    new Sortable(sidebar, {
      group: { name: 'teachers', pull: 'clone', put: false },
      sort: false,
      animation: 150,
    });
    sidebar.dataset.sortableInit = 'true';
  }

  if (typeof Sortable === 'undefined') return;

  document.querySelectorAll('.slots-list').forEach(list => {
    if (list.dataset.sortableInit === 'true') return;

    const isBreak = list.dataset.dutyType === 'break';

    new Sortable(list, {
      group: { name: 'teachers', pull: false, put: true },
      animation: 150,

      onMove: function () {
        const col = list.closest('.location-column');
        if (!col || col.dataset.editable !== 'true') return false;
        return true;
      },

      onAdd: function (evt) {
        const col     = list.closest('.location-column');
        const dayDate = col?.dataset.day;
        const day     = currentWeekData?.day_plans?.find(d => d.date === dayDate);

        if (!day || !day.is_editable) {
          showToast(I18N.t('day_locked') || 'Past days cannot be edited', 'error');
          evt.item.parentNode && evt.item.parentNode.removeChild(evt.item);
          return;
        }

        const slId      = parseInt(list.dataset.slId, 10);
        const teacherId = parseInt(evt.item.dataset.teacherId, 10);
        const teacherName = evt.item.dataset.teacherName;

        if (isTeacherAssignedInSameShift(slId, teacherId)) {
          showToast(I18N.t('duplicate_teacher') || 'Teacher already assigned in this duty', 'error');
          evt.item.parentNode && evt.item.parentNode.removeChild(evt.item);
          return;
        }

        const filledSlots = Array.from(list.querySelectorAll('.slot-item.slot-filled'));
        const emptySlot   = list.querySelector('.slot-item.slot-empty');

        if (!emptySlot && filledSlots.length > 0) {
          // All slots full — replace last filled slot
          const targetSlot = filledSlots[filledSlots.length - 1];
          const slotIdx    = parseInt(targetSlot.dataset.slotIdx, 10);
          // Preserve existing grade_class for break duties
          const existingGradeClass = _getExistingGradeClass(slId, slotIdx);
          replaceTeacherInSlot(slId, slotIdx, teacherId, teacherName, isBreak, existingGradeClass);
          evt.item.parentNode && evt.item.parentNode.removeChild(evt.item);
          _refreshFillBar(slId);
          showToast(I18N.t('teacher_replaced') || 'Teacher replaced');
          return;
        }

        if (!emptySlot) {
          showToast(I18N.t('no_empty_slot') || 'No empty slot available', 'error');
          evt.item.parentNode && evt.item.parentNode.removeChild(evt.item);
          return;
        }

        const slotIdx = parseInt(emptySlot.dataset.slotIdx, 10);
        // Preserve the pre-seeded grade_class for break duties
        const gradeClass = _getExistingGradeClass(slId, slotIdx);
        recordAssignment(slId, slotIdx, teacherId, gradeClass);

        emptySlot.outerHTML = renderSlot(slId, slotIdx, {
          teacher_id:   teacherId,
          teacher_name: teacherName,
          slot_index:   slotIdx,
          grade_class:  gradeClass,
        }, isBreak, true);

        evt.item.parentNode && evt.item.parentNode.removeChild(evt.item);
        _refreshFillBar(slId);
      },
    });

    list.dataset.sortableInit = 'true';
  });
}

/**
 * Returns the pre-seeded grade_class for a break slot from currentWeekData.
 * For non-break slots returns null.
 */
function _getExistingGradeClass(slId, slotIdx) {
  const found = findShiftLocationInCurrentWeek(slId);
  if (!found) return null;
  const existing = found.sl.assignments?.find(a => a.slot_index === slotIdx);
  return existing?.grade_class ?? null;
}

function recordAssignment(slId, slotIdx, teacherId, gradeClass) {
  if (!pendingAssignments[slId]) pendingAssignments[slId] = {};
  pendingAssignments[slId][slotIdx] = { teacher_id: teacherId, grade_class: gradeClass };
}

function replaceTeacherInSlot(slId, slotIdx, teacherId, teacherName, isBreak, gradeClass = null) {
  // Preserve existing grade_class if not explicitly passed
  const resolvedGrade = gradeClass ?? _getExistingGradeClass(slId, slotIdx);
  recordAssignment(slId, slotIdx, teacherId, resolvedGrade);

  const list = byId(`slots-${slId}`);
  if (!list) return;
  const slotEl = list.querySelector(`[data-slot-idx="${slotIdx}"]`);
  if (!slotEl) return;
  slotEl.outerHTML = renderSlot(slId, slotIdx, {
    teacher_id:   teacherId,
    teacher_name: teacherName,
    slot_index:   slotIdx,
    grade_class:  resolvedGrade,
  }, isBreak, true);
}

function removeTeacher(slId, slotIdx) {
  const list = byId(`slots-${slId}`);
  const col  = list?.closest('.location-column');
  if (col?.dataset.editable !== 'true') {
    showToast(I18N.t('day_locked') || 'Past days cannot be edited', 'error');
    return;
  }

  // Preserve grade_class so the empty slot badge still shows the class
  const gradeClass = _getExistingGradeClass(slId, slotIdx);
  recordAssignment(slId, slotIdx, null, gradeClass);

  if (!list) return;
  const slotEl = list.querySelector(`[data-slot-idx="${slotIdx}"]`);
  if (slotEl) {
    const isBreak = list.dataset.dutyType === 'break';
    slotEl.outerHTML = renderSlot(slId, slotIdx, { grade_class: gradeClass }, isBreak, true);
    _refreshFillBar(slId);
    showToast(I18N.t('teacher_removed') || 'Teacher removed', 'info');
  }
}

// ─── Slot Count Control ───────────────────────────────────────────────────────

function changeSlots(dayDate, shiftId, locationId, delta) {
  const day = currentWeekData?.day_plans.find(d => d.date === dayDate);
  if (!day || !day.is_editable) {
    showToast(I18N.t('day_locked') || 'Past days cannot be edited', 'error');
    return;
  }

  const locId = locationId === 'null' ? null : locationId;
  const key   = `${dayDate}:${shiftId}:${locId}`;

  const selector = locId === null
    ? `[data-day="${dayDate}"][data-shift="${shiftId}"][data-loc=""]`
    : `[data-day="${dayDate}"][data-shift="${shiftId}"][data-loc="${locId}"]`;

  const col = document.querySelector(selector);
  if (!col) return;

  const slId     = parseInt(col.dataset.slId, 10);
  const countEl  = byId(`slot-count-${slId}`);
  if (!countEl) return;

  const current  = parseInt(countEl.textContent, 10) || 0;
  const newCount = Math.max(0, current + delta);
  countEl.textContent = newCount;

  pendingSlots[key] = {
    dayDate,
    shiftId:    parseInt(shiftId, 10),
    locationId: locId ? parseInt(locId, 10) : null,
    slotsCount: newCount,
  };
}

// ─── Save / Publish ───────────────────────────────────────────────────────────

async function flushPendingChanges() {
  const weekStart = currentWeekData?.week_start_date;
  if (!weekStart) return;

  // 1. Flush slot count changes
  const slotUpdates = Object.values(pendingSlots);
  if (slotUpdates.length > 0) {
    const res = await apiFetch(`/weeks/${weekStart}/shift-locations`, {
      method: 'PUT',
      body: JSON.stringify(slotUpdates.map(u => ({
        day_date:    u.dayDate,
        shift_id:    u.shiftId,
        location_id: u.locationId,
        slots_count: u.slotsCount,
      }))),
    });
    if (res && res.ok) {
      pendingSlots = {};
      currentWeekData = await res.json();
    } else {
      const message = await getApiErrorMessage(res, 'Failed to save slot changes');
      showToast(message, 'error');
      throw new Error(message);
    }
  }

  // 2. Flush assignment changes
  const assignmentUpdates = [];
  for (const [slId, slotMap] of Object.entries(pendingAssignments)) {
    for (const [slotIdx, data] of Object.entries(slotMap)) {
      assignmentUpdates.push({
        shift_location_id: parseInt(slId, 10),
        slot_index:        parseInt(slotIdx, 10),
        teacher_id:        data.teacher_id ?? null,
        grade_class:       data.grade_class ?? null,
      });
    }
  }

  if (assignmentUpdates.length > 0) {
    const res = await apiFetch(`/weeks/${weekStart}/assignments`, {
      method: 'PUT',
      body: JSON.stringify(assignmentUpdates),
    });
    if (res && res.ok) {
      pendingAssignments = {};
      currentWeekData = await res.json();
    } else {
      const message = await getApiErrorMessage(res, 'Failed to save assignment changes');
      showToast(message, 'error');
      throw new Error(message);
    }
  }

  renderWeek();
}

async function saveDraft() {
  if (!currentWeekData) return;
  try {
    await flushPendingChanges();
    showToast(I18N.t('success_saved'));
  } catch (err) {
    showToast(err.message || I18N.t('error_generic'), 'error');
  }
}

async function publishWeek() {
  if (!currentWeekData) return;
  if (!confirm(I18N.t('confirm_publish'))) return;

  try {
    await flushPendingChanges();
    const weekStart = currentWeekData.week_start_date;
    const res = await apiFetch(`/weeks/${weekStart}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status: 'published' }),
    });
    if (res && res.ok) {
      currentWeekData = await res.json();
      renderWeek();
      updateStatusBadge(currentWeekData.status);
      showToast(I18N.t('success_published'));
    } else {
      const err = res ? await res.json() : {};
      showToast(err.detail || I18N.t('error_generic'), 'error');
    }
  } catch (err) {
    showToast(err.message || I18N.t('error_generic'), 'error');
  }
}

async function publishDay(dayDate) {
  if (!currentWeekData) return;
  const publishBtn = byId(`publish-day-btn-${dayDate}`);
  const originalText = publishBtn?.textContent;

  if (publishBtn) {
    publishBtn.disabled = true;
    publishBtn.textContent = I18N.t('publishing') || 'Publishing...';
  }

  try {
    await flushPendingChanges();
    const weekStart = currentWeekData.week_start_date;
    const res = await apiFetch(`/weeks/${weekStart}/publish-day?day_date=${dayDate}`, { method: 'PUT' });

    if (res && res.ok) {
      let data = null;
      try { data = await res.json(); } catch (_) {}

      // Update local data model
      if (data?.day_plans) {
        currentWeekData = data;
      } else if (currentWeekData?.day_plans) {
        currentWeekData.day_plans = currentWeekData.day_plans.map(d =>
          d.date === dayDate ? { ...d, is_published: true } : d
        );
      }

      // ── Surgical DOM update — no full re-render needed ──────────────────
      // 1. Find the tab button for this day and stamp the tick instantly
      _markDayTabPublished(dayDate);

      // 2. Replace the "Publish Day" button with the "Published" badge in-place
      const btn = byId(`publish-day-btn-${dayDate}`);
      if (btn) {
        const badge = document.createElement('span');
        badge.style.cssText = 'font-size:0.8rem;color:#166534;background:#dcfce7;padding:6px 10px;border-radius:999px';
        badge.textContent = `✅ ${I18N.t('published') || 'Published'}`;
        btn.replaceWith(badge);
      }
      // ────────────────────────────────────────────────────────────────────

      showToast(I18N.t('success_day_published') || 'Day published successfully');
      return;
    }

    const message = await getApiErrorMessage(res, I18N.t('error_generic'));
    showToast(message, 'error');
  } catch (err) {
    showToast(err.message || I18N.t('error_generic'), 'error');
  } finally {
    // Only restore button if it still exists (wasn't replaced on success)
    const currentBtn = byId(`publish-day-btn-${dayDate}`);
    if (currentBtn) {
      currentBtn.disabled = false;
      currentBtn.textContent = originalText || I18N.t('publish_day') || 'Publish Day';
    }
  }
}

/**
 * Finds the tab button for a given dayDate and appends the ✔ tick mark
 * without rebuilding the tab bar. Works by matching the tab's position
 * against currentWeekData.day_plans order.
 */
function _markDayTabPublished(dayDate) {
  const tabs = document.querySelectorAll('#dayTabs .tab-btn');
  const idx  = currentWeekData?.day_plans?.findIndex(d => d.date === dayDate) ?? -1;
  if (idx < 0 || !tabs[idx]) return;

  const tab = tabs[idx];
  // Stamp the tick mark
  if (!tab.textContent.includes('✔')) {
    tab.textContent = tab.textContent.trimEnd() + ' ✔';
  }
  // Brief scale-pop animation to draw the eye
  tab.classList.remove('just-published'); // reset if already applied
  void tab.offsetWidth;                   // force reflow so animation replays
  tab.classList.add('just-published');
}

async function createWeek() {
  const input = byId('weekStartInput');
  if (!input?.value) return;
  const weekStart = getWeekStartFromDate(input.value);
  setPlannerBusy(true, I18N.t('creating_week') || 'Creating week...');

  try {
    const res = await apiFetch(`/weeks/${weekStart}/create`, { method: 'POST' });
    if (!res) throw new Error('Failed to reach server');

    let data = null;
    try { data = await res.json(); } catch (_) {}

    if (res.status === 409) {
      selectedDate = weekStart; syncWeekInputWithSelectedDate();
      pendingAssignments = {}; pendingSlots = {};
      await loadWeek();
      showToast(data?.detail || I18N.t('week_exists_loaded') || 'Week already exists, loaded successfully', 'info');
      return;
    }

    if (!res.ok) throw new Error(data?.detail || I18N.t('create_failed') || 'Failed to create week');

    selectedDate = weekStart; syncWeekInputWithSelectedDate();
    pendingAssignments = {}; pendingSlots = {};
    await loadWeek();
    showToast(data?.message || I18N.t('success_created') || 'Week created successfully');
  } catch (err) {
    showToast(err.message || I18N.t('create_failed'), 'error');
  } finally {
    setPlannerBusy(false);
  }
}

async function cloneWeek() {
  const input = byId('weekStartInput');
  if (!input?.value) return;
  const weekStart = getWeekStartFromDate(input.value);
  setPlannerBusy(true, I18N.t('cloning_week') || 'Cloning week...');

  try {
    const res = await apiFetch(`/weeks/${weekStart}/clone`, { method: 'POST' });
    if (!res) throw new Error('Failed to reach server');

    let data = null;
    try { data = await res.json(); } catch (_) {}

    if (res.status === 409) {
      selectedDate = weekStart; syncWeekInputWithSelectedDate();
      pendingAssignments = {}; pendingSlots = {};
      await loadWeek();
      showToast(data?.detail || I18N.t('week_exists_loaded') || 'Week already exists, loaded successfully', 'info');
      return;
    }

    if (!res.ok) throw new Error(data?.detail || I18N.t('clone_failed') || 'Clone failed');

    selectedDate = weekStart; syncWeekInputWithSelectedDate();
    pendingAssignments = {}; pendingSlots = {};
    await loadWeek();
    showToast(data?.message || I18N.t('success_cloned') || 'Week cloned successfully');
  } catch (err) {
    showToast(err.message || I18N.t('clone_failed'), 'error');
  } finally {
    setPlannerBusy(false);
  }
}

// ─── Auto Init ────────────────────────────────────────────────────────────────

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initPlanner);
} else {
  initPlanner();
}