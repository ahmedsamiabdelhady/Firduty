/**
 * planner.js — Firduty Admin Week Planner
 * Handles: week loading, day/shift tabs, drag-and-drop, slot management.
 * Duty-type aware: break duties show grade/class input instead of location.
 *
 * Auth is handled by auth.js (loaded before this script in planner.html).
 * Use apiFetch() for all API calls — it attaches the token and handles 401.
 */

let currentWeekData = null;
let allTeachers = [];
let pendingAssignments = {};   // slId → { slotIdx → { teacher_id, grade_class } }
let pendingSlots = {};         // key → { dayDate, shiftId, locationId, slotsCount }
let selectedDate = null;       // the exact day chosen by admin in the date picker
let lang = () => I18N.getLang();

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

  const value = selectedDate || getCurrentLocalDate();
  weekInput.value = value;
}

function setPlannerBusy(isBusy, message = '') {
  const overlay = byId('plannerBusyOverlay');
  const textEl = byId('plannerLoadingText');
  const barEl = byId('plannerLoadingBar');
  const plannerMain = document.querySelector('.planner-main');

  if (textEl) {
    textEl.textContent = message || 'Loading...';
  }

  if (overlay) {
    overlay.style.display = isBusy ? 'flex' : 'none';
  }

  if (barEl) {
    barEl.classList.toggle('is-active', !!isBusy);
  }

  if (plannerMain) {
    plannerMain.style.pointerEvents = isBusy ? 'none' : '';
  }
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function pollUntilWeekVisible(weekStart, attempts = 6, delayMs = 1200) {
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await apiFetch(`/weeks/${weekStart}`);
      if (res && res.ok) {
        currentWeekData = await res.json();
        selectedDate = weekStart;
        syncWeekInputWithSelectedDate();
        pendingAssignments = {};
        pendingSlots = {};
        renderWeek();
        return true;
      }
    } catch (err) {
      console.warn('pollUntilWeekVisible attempt failed:', err);
    }

    if (i < attempts - 1) {
      await sleep(delayMs);
    }
  }

  return false;
}

/* ─── Init ────────────────────────────────────────────────────────────────── */

async function initPlanner() {
  try {
    applyWeekInputLimits();

    const weekInput = byId('weekStartInput');
    const today = getCurrentLocalDate();
    selectedDate = weekInput?.value || today;

    await Promise.all([
      loadTeachers(),
      loadWeek()
    ]);
  } catch (err) {
    console.error('initPlanner failed:', err);
    showToast(I18N.t('error_generic'), 'error');
  }
}

async function onWeekSelected() {
  applyWeekInputLimits();

  const weekInput = byId('weekStartInput');
  if (!weekInput || !weekInput.value) return;

  selectedDate = weekInput.value;
  await loadWeek();
}

/* ─── Teachers Sidebar ────────────────────────────────────────────────────── */

async function loadTeachers() {
  const teacherList = byId('teacherList');
  const teachersLoading = byId('teachersLoading');

  try {
    showEl(teachersLoading);
    if (teacherList) teacherList.innerHTML = '';

    const res = await apiFetch('/teachers/');

    if (!res || !res.ok) {
      allTeachers = [];
      renderTeacherSidebar();
      return;
    }

    allTeachers = await res.json();
    renderTeacherSidebar();
  } catch (err) {
    console.error('loadTeachers failed:', err);
    allTeachers = [];
    renderTeacherSidebar();
  } finally {
    hideEl(teachersLoading);
  }
}

function renderTeacherSidebar() {
  const list = byId('teacherList');
  if (!list) return;

  if (!allTeachers.length) {
    list.innerHTML = `<p style="font-size:0.8rem;color:#999">${I18N.t('no_teachers_yet') || 'No teachers'}</p>`;
    return;
  }

  list.innerHTML = allTeachers.map(t => `
    <div class="teacher-list-item"
         data-teacher-id="${t.id}"
         data-teacher-name="${escHtml(t.name)}"
         draggable="true">${escHtml(t.name)}</div>
  `).join('');
}

/* ─── Week Loading ────────────────────────────────────────────────────────── */

async function loadWeek() {
  const weekInput = byId('weekStartInput');
  const noPlanMsg = byId('noPlanMsg');
  const dayTabs = byId('dayTabs');
  const dayPanels = byId('dayPanels');
  const plannerLoading = byId('plannerLoading');

  const pickedDate = weekInput ? weekInput.value : '';
  if (!pickedDate) return;

  selectedDate = pickedDate;
  const weekStart = getWeekStartFromDate(pickedDate);

  pendingAssignments = {};
  pendingSlots = {};

  try {
    showEl(plannerLoading);
    hideEl(noPlanMsg);

    if (dayTabs) dayTabs.innerHTML = '';
    if (dayPanels) dayPanels.innerHTML = '';

    const res = await apiFetch(`/weeks/${weekStart}`);
    if (!res) {
      currentWeekData = null;
      showEl(noPlanMsg, 'block');
      updateStatusBadge(null);
      return;
    }

    if (res.status === 404) {
      currentWeekData = null;
      showEl(noPlanMsg, 'block');

      if (dayTabs) dayTabs.innerHTML = '';
      if (dayPanels) {
        dayPanels.innerHTML =
          '<p style="color:#6c757d;text-align:center;margin-top:40px" data-i18n="no_week"></p>';
      }

      I18N.applyTranslations();
      updateStatusBadge(null);
      showToast('No plan found for this week', 'info');
      return;
    }

    if (!res.ok) {
      currentWeekData = null;
      showEl(noPlanMsg, 'block');
      updateStatusBadge(null);
      showToast(await getApiErrorMessage(res, I18N.t('error_generic')), 'error');
      return;
    }

    currentWeekData = await res.json();
    renderWeek();
  } catch (err) {
    console.error('loadWeek failed:', err);
    currentWeekData = null;
    showEl(noPlanMsg, 'block');
    updateStatusBadge(null);
    showToast(I18N.t('error_generic'), 'error');
  } finally {
    hideEl(plannerLoading);
  }
}

function updateStatusBadge(status) {
  const badge = byId('weekStatusBadge');
  const vBadge = byId('weekVersionBadge');

  if (!badge || !vBadge) return;

  if (!status) {
    badge.style.display = 'none';
    vBadge.textContent = '';
    return;
  }

  badge.style.display = 'inline';
  badge.className = `week-status-badge status-${status}`;
  badge.textContent = I18N.t(status);
  vBadge.textContent = currentWeekData ? `v${currentWeekData.version}` : '';
}

/* ─── Week Rendering ──────────────────────────────────────────────────────── */

const DAY_KEYS = ['day_sun', 'day_mon', 'day_tue', 'day_wed', 'day_thu'];

function renderWeek() {
  if (!currentWeekData || !currentWeekData.day_plans) return;

  updateStatusBadge(currentWeekData.status);

  const tabsEl = byId('dayTabs');
  const panelsEl = byId('dayPanels');
  const noPlanMsg = byId('noPlanMsg');

  if (!tabsEl || !panelsEl) return;

  tabsEl.innerHTML = '';
  panelsEl.innerHTML = '';
  hideEl(noPlanMsg);

  const activeIdx = getActiveDayIndex();

  currentWeekData.day_plans.forEach((dayPlan, idx) => {
    const dayDate = new Date(dayPlan.date + 'T12:00:00');
    const dayOfWeek = dayDate.getDay();
    const dayLabel = I18N.t(DAY_KEYS[dayOfWeek] || `Day ${idx}`);

    const tab = document.createElement('button');
    tab.className = 'tab-btn' + (idx === activeIdx ? ' active' : '');
    tab.textContent = dayLabel + (dayPlan.is_published ? ' ✔' : '');
    tab.onclick = () => switchDayTab(idx);
    tabsEl.appendChild(tab);

    const panel = document.createElement('div');
    panel.className = 'tab-panel' + (idx === activeIdx ? ' active' : '');
    panel.innerHTML = renderDayPanel(dayPlan, dayPlan.is_editable);
    if (idx !== activeIdx) {
      panel.style.display = 'none';
    }
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
  if (todayMatch >= 0) return todayMatch;

  return 0;
}

function switchDayTab(idx) {
  document.querySelectorAll('.tab-btn').forEach((b, i) => b.classList.toggle('active', i === idx));
  document.querySelectorAll('.tab-panel').forEach((p, i) => {
    const isActive = i === idx;
    p.classList.toggle('active', isActive);
    p.style.display = isActive ? 'block' : 'none';
  });

  const day = currentWeekData.day_plans[idx];
  if (day) {
    selectedDate = day.date;
    const weekInput = byId('weekStartInput');
    if (weekInput) weekInput.value = day.date;
    showToast(`Loaded ${day.date}`, 'info');
  }
}

function renderDayPanel(dayPlan, isEditable) {
  const shiftMap = {};

  dayPlan.shift_locations.forEach(sl => {
    if (!shiftMap[sl.shift_id]) {
      shiftMap[sl.shift_id] = { shift: sl.shift, locations: [] };
    }
    shiftMap[sl.shift_id].locations.push(sl);
  });

  const shifts = Object.values(shiftMap).sort((a, b) => a.shift.order - b.shift.order);

  if (!shifts.length) {
    return `<p style="color:#999;margin-top:20px;text-align:center">Loading day slots...</p>`;
  }

  const dayBadge = isEditable
    ? `<span style="font-size:0.8rem;color:#15803d;background:#dcfce7;padding:4px 10px;border-radius:999px">${I18N.t('editable') || 'Editable'}</span>`
    : `<span style="font-size:0.8rem;color:#991b1b;background:#fee2e2;padding:4px 10px;border-radius:999px">${I18N.t('locked') || 'Locked'}</span>`;

  const publishBtn = dayPlan.is_published
    ? `<span style="font-size:0.8rem;color:#166534;background:#dcfce7;padding:6px 10px;border-radius:999px">✅ Published</span>`
    : `<button class="btn btn-success btn-sm" id="publish-day-btn-${dayPlan.date}" onclick="publishDay('${dayPlan.date}')">Publish Day</button>`;

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

  const shiftPanelsHtml = shifts.map((s, i) => `
    <div class="shift-panel${i === 0 ? ' active' : ''}"
         id="shift-panel-${dayPlan.date}-${s.shift.id}"
         style="${i === 0 ? 'display:block' : 'display:none'}">
      <div class="locations-grid">
        ${s.locations.map(sl => renderLocationColumn(dayPlan.date, sl, isEditable)).join('')}
      </div>
    </div>
  `).join('');

  return `
    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:12px">
      <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <strong>${dayPlan.date}</strong>
        ${dayBadge}
      </div>
      <div>
        ${publishBtn}
      </div>
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

function renderLocationColumn(dayDate, sl, isEditable) {
  const isBreak = sl.duty_type === 'break' || sl.shift.duty_type === 'break';

  let colTitle;
  if (isBreak) {
    colTitle = `<span style="color:#7c3aed">${lang() === 'ar' ? sl.shift.name_ar : sl.shift.name_en}</span>`;
  } else {
    colTitle = sl.location
      ? (lang() === 'ar' ? sl.location.name_ar : sl.location.name_en)
      : '—';
  }

  const slots = [];
  for (let i = 0; i < sl.slots_count; i++) {
    const assignment = sl.assignments.find(a => a.slot_index === i);
    slots.push(renderSlot(sl.id, i, assignment, isBreak, isEditable));
  }

  return `
    <div class="location-column"
         data-sl-id="${sl.id}"
         data-day="${dayDate}"
         data-shift="${sl.shift_id}"
         data-loc="${sl.location_id || ''}"
         data-duty-type="${isBreak ? 'break' : 'morning_endofday'}"
         data-editable="${isEditable ? 'true' : 'false'}">
      <div class="location-header">
        <span class="location-name">${colTitle}</span>
        <div class="slot-controls">
          <button class="btn-slot btn-slot-sub"
                  ${!isEditable ? 'disabled style="opacity:0.4;pointer-events:none"' : ''}
                  onclick="changeSlots('${dayDate}', ${sl.shift_id}, ${sl.location_id || 'null'}, -1)">−</button>
          <span class="slot-count" id="slot-count-${sl.id}">${sl.slots_count}</span>
          <button class="btn-slot btn-slot-add"
                  ${!isEditable ? 'disabled style="opacity:0.4;pointer-events:none"' : ''}
                  onclick="changeSlots('${dayDate}', ${sl.shift_id}, ${sl.location_id || 'null'}, +1)">+</button>
        </div>
      </div>
      <div class="slots-list"
           id="slots-${sl.id}"
           data-sl-id="${sl.id}"
           data-duty-type="${isBreak ? 'break' : 'morning_endofday'}">
        ${slots.join('')}
      </div>
    </div>
  `;
}

function renderSlot(slId, slotIdx, assignment, isBreak, isEditable = true) {
  if (assignment && assignment.teacher_id) {
    const gradeHtml = isBreak
      ? `<input class="grade-input" type="text"
                placeholder="${I18N.t('grade_class_placeholder')}"
                value="${assignment.grade_class || ''}"
                onchange="updateGradeClass(${slId}, ${slotIdx}, this.value)"
                onclick="event.stopPropagation()"
                ${!isEditable ? 'disabled' : ''}
                style="margin-top:4px;width:100%;font-size:0.8rem;padding:3px 6px;border:1px solid #c4b5fd;border-radius:4px;${!isEditable ? 'opacity:0.6;background:#f3f4f6' : ''}">`
      : '';

    return `
      <div class="slot-item filled" data-sl-id="${slId}" data-slot-idx="${slotIdx}" data-teacher-id="${assignment.teacher_id}">
        <div class="teacher-card" data-teacher-id="${assignment.teacher_id}" data-teacher-name="${escHtml(assignment.teacher_name)}">
          <span>${escHtml(assignment.teacher_name)}</span>
          ${isEditable ? `<span class="remove-btn" onclick="removeTeacher(${slId}, ${slotIdx})">✕</span>` : ''}
        </div>
        ${gradeHtml}
      </div>
    `;
  }

  return `
    <div class="slot-item" data-sl-id="${slId}" data-slot-idx="${slotIdx}" data-teacher-id="">
      <span style="color:#bbb;font-size:0.8rem">${I18N.t('no_teacher')}</span>
    </div>
  `;
}

/* ─── Grade/Class update ──────────────────────────────────────────────────── */

function updateGradeClass(slId, slotIdx, value) {
  const list = byId(`slots-${slId}`);
  const col = list?.closest('.location-column');

  if (col?.dataset.editable !== 'true') {
    showToast(I18N.t('day_locked') || 'Past days cannot be edited', 'error');
    return;
  }

  if (!pendingAssignments[slId]) pendingAssignments[slId] = {};
  if (!pendingAssignments[slId][slotIdx]) pendingAssignments[slId][slotIdx] = {};
  pendingAssignments[slId][slotIdx].grade_class = value;
}

/* ─── Drag & Drop ─────────────────────────────────────────────────────────── */

function findShiftLocationInCurrentWeek(slId) {
  if (!currentWeekData?.day_plans) return null;

  for (const day of currentWeekData.day_plans) {
    for (const sl of day.shift_locations || []) {
      if (sl.id === slId) {
        return { day, sl };
      }
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
    ? {
        teacher_id: fallbackAssignment.teacher_id ?? null,
        grade_class: fallbackAssignment.grade_class ?? null,
      }
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
      if (effective.teacher_id === teacherId) {
        return true;
      }
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

      onMove: function() {
        const col = list.closest('.location-column');
        if (!col || col.dataset.editable !== 'true') return false;
        return true;
      },

      onAdd: function(evt) {
        const col = list.closest('.location-column');
        const dayDate = col?.dataset.day;
        const day = currentWeekData?.day_plans?.find(d => d.date === dayDate);

        if (!day || !day.is_editable) {
          showToast(I18N.t('day_locked') || 'Past days cannot be edited', 'error');
          evt.item.parentNode && evt.item.parentNode.removeChild(evt.item);
          return;
        }

        const slId = parseInt(list.dataset.slId, 10);
        const teacherId = parseInt(evt.item.dataset.teacherId, 10);
        const teacherName = evt.item.dataset.teacherName;

        if (isTeacherAssignedInSameShift(slId, teacherId)) {
          showToast('Teacher already assigned in this duty', 'error');
          evt.item.parentNode && evt.item.parentNode.removeChild(evt.item);
          return;
        }

        // لو القائمة كلها مليانة، استبدل آخر/أول slot مملوءة بدل الفشل
        const filledSlots = Array.from(list.querySelectorAll('.slot-item.filled'));
        const emptySlot = list.querySelector('.slot-item:not(.filled)');

        if (!emptySlot && filledSlots.length > 0) {
          const targetSlot = filledSlots[filledSlots.length - 1];
          const slotIdx = parseInt(targetSlot.dataset.slotIdx, 10);

          replaceTeacherInSlot(slId, slotIdx, teacherId, teacherName, isBreak);

          evt.item.parentNode && evt.item.parentNode.removeChild(evt.item);
          showToast(I18N.t('teacher_replaced') || 'Teacher replaced');
          return;
        }

        if (!emptySlot) {
          showToast(
            I18N.t('no_empty_slot') || 'No empty slot available',
            'error'
          );
          evt.item.parentNode && evt.item.parentNode.removeChild(evt.item);
          return;
        }

        const slotIdx = parseInt(emptySlot.dataset.slotIdx, 10);
        recordAssignment(slId, slotIdx, teacherId, null);

        emptySlot.outerHTML = renderSlot(slId, slotIdx, {
          teacher_id: teacherId,
          teacher_name: teacherName,
          slot_index: slotIdx,
          grade_class: null,
        }, isBreak, true);

        evt.item.parentNode && evt.item.parentNode.removeChild(evt.item);
      }
    });

    list.dataset.sortableInit = 'true';
  });
}

function recordAssignment(slId, slotIdx, teacherId, gradeClass) {
  if (!pendingAssignments[slId]) pendingAssignments[slId] = {};
  pendingAssignments[slId][slotIdx] = { teacher_id: teacherId, grade_class: gradeClass };
}

function replaceTeacherInSlot(slId, slotIdx, teacherId, teacherName, isBreak) {
  recordAssignment(slId, slotIdx, teacherId, null);

  const list = byId(`slots-${slId}`);
  if (!list) return;

  const slotEl = list.querySelector(`[data-slot-idx="${slotIdx}"]`);
  if (!slotEl) return;

  slotEl.outerHTML = renderSlot(slId, slotIdx, {
    teacher_id: teacherId,
    teacher_name: teacherName,
    slot_index: slotIdx,
    grade_class: null,
  }, isBreak, true);
}

function removeTeacher(slId, slotIdx) {
  const list = byId(`slots-${slId}`);
  const col = list?.closest('.location-column');

  if (col?.dataset.editable !== 'true') {
    showToast(I18N.t('day_locked') || 'Past days cannot be edited', 'error');
    return;
  }

  recordAssignment(slId, slotIdx, null, null);

  if (!list) return;

  const slotEl = list.querySelector(`[data-slot-idx="${slotIdx}"]`);
  if (slotEl) {
    slotEl.outerHTML = renderSlot(slId, slotIdx, null, list.dataset.dutyType === 'break', true);
    showToast(I18N.t('teacher_removed') || 'Teacher removed', 'info');
  }
}

/* ─── Slot Count Control ──────────────────────────────────────────────────── */

function changeSlots(dayDate, shiftId, locationId, delta) {
  const day = currentWeekData.day_plans.find(d => d.date === dayDate);
  if (!day || !day.is_editable) {
    showToast(I18N.t('day_locked') || 'Past days cannot be edited', 'error');
    return;
  }

  const locId = locationId === 'null' ? null : locationId;
  const key = `${dayDate}:${shiftId}:${locId}`;

  const selector = locId === null
    ? `[data-day="${dayDate}"][data-shift="${shiftId}"][data-loc=""]`
    : `[data-day="${dayDate}"][data-shift="${shiftId}"][data-loc="${locId}"]`;

  const col = document.querySelector(selector);
  if (!col) return;

  const slId = parseInt(col.dataset.slId, 10);
  const countEl = byId(`slot-count-${slId}`);
  if (!countEl) return;

  const current = parseInt(countEl.textContent, 10) || 0;
  const newCount = Math.max(0, current + delta);
  countEl.textContent = newCount;

  pendingSlots[key] = {
    dayDate,
    shiftId: parseInt(shiftId, 10),
    locationId: locId ? parseInt(locId, 10) : null,
    slotsCount: newCount
  };

  const list = byId(`slots-${slId}`);
  if (!list) return;

  const isBreak = list.dataset.dutyType === 'break';

  if (delta > 0) {
    const div = document.createElement('div');
    div.innerHTML = renderSlot(slId, current, null, isBreak, true);
    list.appendChild(div.firstChild);
    initDragAndDrop();
  } else if (delta < 0 && current > 0) {
    const lastSlot = list.querySelector(`[data-slot-idx="${current - 1}"]`);
    if (lastSlot) lastSlot.remove();
  }
}

/* ─── Save / Publish / Clone ──────────────────────────────────────────────── */

async function saveDraft() {
  if (!currentWeekData) return;

  showToast('Saving...', 'info');

  try {
    await flushPendingChanges();
    showToast(I18N.t('success_saved') || 'Saved successfully');
  } catch (err) {
    console.error('saveDraft failed:', err);
  }
}

async function flushPendingChanges() {
  const weekStart = currentWeekData.week_start_date;

  if (Object.keys(pendingSlots).length > 0) {
    const updates = Object.values(pendingSlots).map(s => ({
      day_date: s.dayDate,
      shift_id: s.shiftId,
      location_id: s.locationId,
      slots_count: s.slotsCount
    }));

    const res = await apiFetch(`/weeks/${weekStart}/shift-locations`, {
      method: 'PUT',
      body: JSON.stringify(updates)
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

  const assignmentUpdates = [];
  for (const [slId, slots] of Object.entries(pendingAssignments)) {
    for (const [slotIdx, data] of Object.entries(slots)) {
      assignmentUpdates.push({
        shift_location_id: parseInt(slId, 10),
        slot_index: parseInt(slotIdx, 10),
        teacher_id: data.teacher_id,
        grade_class: data.grade_class || null,
      });
    }
  }

  if (assignmentUpdates.length > 0) {
    const res = await apiFetch(`/weeks/${weekStart}/assignments`, {
      method: 'PUT',
      body: JSON.stringify(assignmentUpdates)
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

async function publishWeek() {
  if (!currentWeekData) return;
  if (!confirm(I18N.t('confirm_publish'))) return;

  try {
    await flushPendingChanges();

    const weekStart = currentWeekData.week_start_date;
    const res = await apiFetch(`/weeks/${weekStart}/status`, {
      method: 'PUT',
      body: JSON.stringify({ status: 'published' })
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
  const originalBtnHtml = publishBtn ? publishBtn.outerHTML : null;

  if (publishBtn) {
    publishBtn.disabled = true;
    publishBtn.textContent = 'Publishing...';
  }

  try {
    await flushPendingChanges();

    const weekStart = currentWeekData.week_start_date;
    const res = await apiFetch(
      `/weeks/${weekStart}/publish-day?day_date=${dayDate}`,
      { method: 'PUT' }
    );

    if (res && res.ok) {
      let data = null;
      try {
        data = await res.json();
      } catch (_) {
        data = null;
      }

      if (data && data.day_plans) {
        currentWeekData = data;
      } else if (currentWeekData?.day_plans) {
        currentWeekData.day_plans = currentWeekData.day_plans.map(day =>
          day.date === dayDate ? { ...day, is_published: true } : day
        );
      }

      renderWeek();
      showToast('Day published successfully', 'success');
      return;
    }

    const message = await getApiErrorMessage(res, I18N.t('error_generic'));
    showToast(message, 'error');
  } catch (err) {
    showToast(err.message || I18N.t('error_generic'), 'error');
  } finally {
    const currentBtn = byId(`publish-day-btn-${dayDate}`);
    if (currentBtn) {
      currentBtn.disabled = false;
      currentBtn.textContent = 'Publish Day';
    } else if (originalBtnHtml) {
      const activePanelHeader = document.querySelector('.tab-panel.active .day-header-actions, .tab-panel.active [data-day-header-actions]');
      if (activePanelHeader && !activePanelHeader.querySelector(`#publish-day-btn-${dayDate}`)) {
        activePanelHeader.insertAdjacentHTML('beforeend', originalBtnHtml);
      }
    }
  }
}

async function createWeek() {
  const input = byId('weekStartInput');
  const selected = input?.value;
  if (!selected) return;

  const weekStart = getWeekStartFromDate(selected);
  setPlannerBusy(true, 'Creating week...');

  try {
    const res = await apiFetch(`/weeks/${weekStart}/create`, { method: 'POST' });
    if (!res) {
      throw new Error('Failed to reach server');
    }

    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      data = null;
    }

    if (res.status === 409) {
      selectedDate = weekStart;
      syncWeekInputWithSelectedDate();
      pendingAssignments = {};
      pendingSlots = {};
      await loadWeek();
      showToast(data?.detail || data?.message || 'Week already exists, loaded successfully', 'info');
      return;
    }

    if (!res.ok) {
      throw new Error(data?.detail || data?.message || 'Failed to create week');
    }

    selectedDate = weekStart;
    syncWeekInputWithSelectedDate();
    pendingAssignments = {};
    pendingSlots = {};

    await loadWeek();
    showToast(data?.message || 'Week created successfully', 'success');
  } catch (err) {
    console.error('createWeek failed:', err);
    showToast(err.message || 'Failed to create week', 'error');
  } finally {
    setPlannerBusy(false);
  }
}

async function cloneWeek() {
  const input = byId('weekStartInput');
  const selected = input?.value;
  if (!selected) return;

  const weekStart = getWeekStartFromDate(selected);
  setPlannerBusy(true, 'Cloning week...');

  try {
    const res = await apiFetch(`/weeks/${weekStart}/clone`, { method: 'POST' });
    if (!res) {
      throw new Error('Failed to reach server');
    }

    let data = null;
    try {
      data = await res.json();
    } catch (_) {
      data = null;
    }

    if (res.status === 409) {
      selectedDate = weekStart;
      syncWeekInputWithSelectedDate();
      pendingAssignments = {};
      pendingSlots = {};
      await loadWeek();
      showToast(data?.detail || data?.message || 'Week already exists, loaded successfully', 'info');
      return;
    }

    if (!res.ok) {
      throw new Error(data?.detail || data?.message || 'Clone failed');
    }

    selectedDate = weekStart;
    syncWeekInputWithSelectedDate();
    pendingAssignments = {};
    pendingSlots = {};

    await loadWeek();
    showToast(data?.message || I18N.t('success_cloned') || 'Week cloned successfully', 'success');
  } catch (err) {
    console.error('cloneWeek failed:', err);
    showToast(err.message || 'Clone failed', 'error');
  } finally {
    setPlannerBusy(false);
  }
}

/* ─── Auto Init ───────────────────────────────────────────────────────────── */

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initPlanner);
} else {
  initPlanner();
}

/* ─── Helpers ─────────────────────────────────────────────────────────────── */

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}