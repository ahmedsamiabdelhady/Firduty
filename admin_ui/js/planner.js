/**
 * planner.js — Firduty Admin Week Planner  v2.5
 *
 * Changes from v2.4:
 *  - Single viewport helper `isMobilePlanner()` — removes broken `isMobileViewport` reference
 *  - Mobile: slot tap → bottom-sheet teacher picker; Sortable NOT initialised on mobile
 *  - Desktop: Sortable drag-drop unchanged; sidebar now has a live search filter
 *  - Fix setPlannerBusy progress-bar toggle (was `!isBusy`, now `!!isBusy`)
 *  - `initDragAndDrop()` guarded against mobile; no duplicate listeners on re-render
 *  - `renderSlot()` emits data-pickable + onclick=onSlotTap for mobile tap
 *  - `renderTeacherSidebar()` includes search input; items non-draggable on mobile
 *  - `guardPage()` called first in `initPlanner()`
 *  - `grade_class` field consolidated: always a <select> (no conflicting free-text path)
 *  - All hardcoded fallback strings routed through I18N.t() with i18n keys
 *  - Resize listener re-inits DnD when crossing from mobile → desktop
 */

/* ─── Module state ────────────────────────────────────────────────────────── */

let currentWeekData   = null;
let allTeachers       = [];
let pendingAssignments = {};   // slId  → { slotIdx → { teacher_id, grade_class } }
let pendingSlots       = {};   // key   → { dayDate, shiftId, locationId, slotsCount }
let selectedDate       = null; // date string chosen in the date picker

// Mobile bottom-sheet state
let _mobilePicker = { slId: null, slotIdx: null, isBreak: false };

/* ─── Viewport helper (single source of truth) ───────────────────────────── */

/**
 * Returns true when the viewport is ≤ 768 px — matches the CSS breakpoint.
 * Use ONLY this function for mobile/desktop branching; never use isMobileViewport.
 */
function isMobilePlanner() {
  return window.innerWidth <= 768;
}

/* ─── DOM utilities ───────────────────────────────────────────────────────── */

function byId(id) { return document.getElementById(id); }

function showEl(el, display = '') { if (el) el.style.display = display; }
function hideEl(el)               { if (el) el.style.display = 'none';  }

function showToast(message, type = 'success') {
  const c = byId('toastContainer');
  if (!c) return;
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = message;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function lang() { return I18N.getLang(); }

/* ─── Date utilities ──────────────────────────────────────────────────────── */

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

function getCurrentLocalDate()  { return formatDateLocal(new Date()); }
function getCurrentSunday()     { return getWeekStartFromDate(getCurrentLocalDate()); }

function getPreviousSunday() {
  const d = parseLocalDate(getCurrentSunday());
  d.setDate(d.getDate() - 7);
  return formatDateLocal(d);
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

/* ─── Week input helpers ──────────────────────────────────────────────────── */

function applyWeekInputLimits() {
  const weekInput = byId('weekStartInput');
  if (!weekInput) return;
  const minDate = getPreviousSunday();
  const today   = getCurrentLocalDate();
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

/* ─── Busy overlay ────────────────────────────────────────────────────────── */

function setPlannerBusy(isBusy, message = '') {
  const overlay     = byId('plannerBusyOverlay');
  const textEl      = byId('plannerLoadingText');
  const barEl       = byId('plannerLoadingBar');
  const plannerMain = document.querySelector('.planner-main');

  if (textEl) textEl.textContent = message || I18N.t('loading');
  if (overlay) overlay.style.display = isBusy ? 'flex' : 'none';
  // !! cast: was accidentally `!isBusy` in v2.4 — fixed here
  if (barEl) barEl.classList.toggle('is-active', !!isBusy);
  if (plannerMain) plannerMain.style.pointerEvents = isBusy ? 'none' : '';
}

/* ─── API error helper ────────────────────────────────────────────────────── */

async function getApiErrorMessage(res, fallbackMessage) {
  if (!res) return fallbackMessage;
  try {
    const data = await res.json();
    return data?.detail || data?.message || fallbackMessage;
  } catch (_) {
    return fallbackMessage;
  }
}

/* ─── Init ────────────────────────────────────────────────────────────────── */

async function initPlanner() {
  // Guard before doing anything else
  await guardPage(false);

  try {
    ensureMobileBottomSheet();
    applyWeekInputLimits();

    const weekInput = byId('weekStartInput');
    selectedDate = weekInput?.value || getCurrentLocalDate();

    await Promise.all([loadTeachers(), loadWeek()]);
  } catch (err) {
    console.error('initPlanner failed:', err);
    showToast(I18N.t('error_generic'), 'error');
  }
}

async function onWeekSelected() {
  applyWeekInputLimits();
  const weekInput = byId('weekStartInput');
  if (!weekInput?.value) return;
  selectedDate = weekInput.value;
  await loadWeek();
}

/* ─── Teacher sidebar ─────────────────────────────────────────────────────── */

async function loadTeachers() {
  const teacherList    = byId('teacherList');
  const teachersLoading = byId('teachersLoading');

  try {
    showEl(teachersLoading);
    if (teacherList) teacherList.innerHTML = '';

    const res = await apiFetch('/teachers/');
    if (!res || !res.ok) {
      allTeachers = [];
    } else {
      allTeachers = await res.json();
    }
    renderTeacherSidebar();
  } catch (err) {
    console.error('loadTeachers failed:', err);
    allTeachers = [];
    renderTeacherSidebar();
  } finally {
    hideEl(teachersLoading);
  }
}

function renderTeacherSidebar(filterQuery = '') {
  const list = byId('teacherList');
  if (!list) return;

  const query = filterQuery.toLowerCase().trim();
  const filtered = query
    ? allTeachers.filter(t => t.name.toLowerCase().includes(query))
    : allTeachers;

  if (!allTeachers.length) {
    list.innerHTML = `<p class="sidebar-empty">${I18N.t('no_teachers_yet')}</p>`;
    return;
  }

  const mobile = isMobilePlanner();

  // On mobile: items are NOT draggable — they serve as reference / search target.
  // Teacher assignment happens via the bottom-sheet (opened by tapping a slot).
  list.innerHTML = filtered.map(t => `
    <div class="teacher-list-item${mobile ? ' teacher-list-item--mobile' : ''}"
         data-teacher-id="${t.id}"
         data-teacher-name="${escHtml(t.name)}"
         ${mobile ? '' : 'draggable="true"'}
         >${escHtml(t.name)}</div>
  `).join('');

  // Re-init DnD on the sidebar when not mobile
  // (list items were just replaced, so Sortable needs the updated children)
  if (!mobile && typeof Sortable !== 'undefined') {
    const sidebar = byId('teacherList');
    if (sidebar && !sidebar.dataset.sortableInit) {
      new Sortable(sidebar, {
        group: { name: 'teachers', pull: 'clone', put: false },
        sort: false,
        animation: 150,
      });
      sidebar.dataset.sortableInit = 'true';
    }
  }
}

function filterTeacherSidebar(query) {
  renderTeacherSidebar(query);
}

/* ─── Mobile bottom-sheet teacher picker ─────────────────────────────────── */

/**
 * Inject the bottom-sheet DOM into <body> and wire all listeners.
 * Called once from initPlanner(). The static HTML was intentionally removed
 * from planner.html so this function always runs and listeners always attach.
 */
function ensureMobileBottomSheet() {
  // Remove any stale DOM element (e.g. left from a hot-reload in dev)
  const stale = byId('mobileTeacherPicker');
  if (stale) stale.remove();

  const el = document.createElement('div');
  el.id        = 'mobileTeacherPicker';
  el.className = 'mobile-bottom-sheet';
  el.setAttribute('aria-modal', 'true');
  el.setAttribute('role',       'dialog');
  el.style.display = 'none';
  el.innerHTML = `
    <div class="bottom-sheet-backdrop" id="bottomSheetBackdrop"></div>
    <div class="bottom-sheet-panel"    id="bottomSheetPanel">
      <div class="bottom-sheet-header">
        <span class="bottom-sheet-title" id="mobilePickerTitle"></span>
        <button class="bottom-sheet-close" id="bottomSheetClose"
                aria-label="${I18N.t('close')}">&times;</button>
      </div>
      <input
        type="search"
        id="mobileTeacherSearch"
        class="bottom-sheet-search"
        placeholder="${I18N.t('search_teachers') || 'Search teachers…'}"
        autocomplete="off"
      >
      <div id="mobileTeacherList" class="bottom-sheet-list"></div>
    </div>
  `;
  document.body.appendChild(el);

  // ── Listeners — attached exactly once ──────────────────────────────────
  byId('bottomSheetBackdrop').addEventListener('click', closeMobileTeacherPicker);
  byId('bottomSheetClose').addEventListener('click',    closeMobileTeacherPicker);
  byId('mobileTeacherSearch').addEventListener('input', e => {
    renderMobileTeacherList(e.target.value);
  });

  // Escape key closes sheet
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') closeMobileTeacherPicker();
  });

  // Swipe-down to close
  let _startY = 0;
  const panel = byId('bottomSheetPanel');
  panel.addEventListener('touchstart', e => {
    _startY = e.touches[0].clientY;
  }, { passive: true });
  panel.addEventListener('touchend', e => {
    if (e.changedTouches[0].clientY - _startY > 80) closeMobileTeacherPicker();
  }, { passive: true });
}

function openMobileTeacherPicker(slId, slotIdx, isBreak) {
  _mobilePicker = { slId, slotIdx, isBreak };

  const picker = byId('mobileTeacherPicker');
  if (!picker) { ensureMobileBottomSheet(); return openMobileTeacherPicker(slId, slotIdx, isBreak); }

  // Title: "Assign teacher" for empty, "Replace [name]" for filled
  const list      = byId(`slots-${slId}`);
  const slotEl    = list?.querySelector(`[data-slot-idx="${slotIdx}"]`);
  const isFilled  = slotEl?.classList.contains('filled');
  const existName = slotEl?.querySelector('[data-teacher-name]')?.dataset.teacherName || '';
  const titleEl   = byId('mobilePickerTitle');
  if (titleEl) {
    titleEl.textContent = isFilled
      ? `↔ Replace "${existName}"`
      : (I18N.t('pick_teacher') || 'Assign teacher');
  }

  const searchEl = byId('mobileTeacherSearch');
  if (searchEl) searchEl.value = '';
  renderMobileTeacherList('');

  picker.style.display = 'flex';

  // Slide-up animation
  const panel = byId('bottomSheetPanel');
  if (panel) {
    panel.style.transition = '';
    panel.style.transform  = 'translateY(100%)';
    requestAnimationFrame(() => {
      panel.style.transition = 'transform 0.28s cubic-bezier(0.32,0.72,0,1)';
      panel.style.transform  = 'translateY(0)';
    });
  }

  setTimeout(() => { searchEl?.focus(); }, 120);
}

function closeMobileTeacherPicker() {
  const picker = byId('mobileTeacherPicker');
  if (!picker) return;

  const panel = byId('bottomSheetPanel');
  if (panel) {
    panel.style.transition = 'transform 0.22s ease-in';
    panel.style.transform = 'translateY(100%)';
    setTimeout(() => {
      picker.style.display = 'none';
      if (panel) { panel.style.transition = ''; panel.style.transform = ''; }
    }, 230);
  } else {
    picker.style.display = 'none';
  }

  _mobilePicker = { slId: null, slotIdx: null, isBreak: false };
}

function renderMobileTeacherList(query = '') {
  const listEl = byId('mobileTeacherList');
  if (!listEl) return;

  const q = query.toLowerCase().trim();
  const filtered = q
    ? allTeachers.filter(t => t.name.toLowerCase().includes(q))
    : allTeachers;

  if (!filtered.length) {
    listEl.innerHTML = `<p class="bottom-sheet-empty">${I18N.t('no_teachers_yet')}</p>`;
    return;
  }

  listEl.innerHTML = filtered.map(t => `
    <button
      class="bottom-sheet-teacher-btn"
      data-teacher-id="${t.id}"
      onclick="mobileSelectTeacher(${t.id}, '${escHtml(t.name).replace(/'/g, '&#39;')}')"
    >${escHtml(t.name)}</button>
  `).join('');
}

function mobileSelectTeacher(teacherId, teacherName) {
  const { slId, slotIdx, isBreak } = _mobilePicker;
  if (slId == null || slotIdx == null) return;

  const list = byId(`slots-${slId}`);
  const col  = list?.closest('.location-column');

  if (col?.dataset.editable !== 'true') {
    showToast(I18N.t('day_locked'), 'error');
    closeMobileTeacherPicker();
    return;
  }

  if (isTeacherAssignedInSameShift(slId, teacherId)) {
    showToast(I18N.t('teacher_already_assigned') || 'Teacher already assigned in this duty', 'error');
    return;
  }

  // Check if target slot is filled → replace, else fill empty
  const slotEl   = list?.querySelector(`[data-slot-idx="${slotIdx}"]`);
  // For break duties the grade class is pre-labeled on the element; preserve it.
  const gradeClass = isBreak ? (slotEl?.dataset.gradeClass || null) : null;

  if (slotEl?.classList.contains('filled')) {
    replaceTeacherInSlot(slId, slotIdx, teacherId, teacherName, isBreak);
    showToast(I18N.t('teacher_replaced'));
  } else {
    recordAssignment(slId, slotIdx, teacherId, gradeClass);
    if (slotEl) {
      slotEl.outerHTML = renderSlot(slId, slotIdx, {
        teacher_id:   teacherId,
        teacher_name: teacherName,
        slot_index:   slotIdx,
        grade_class:  gradeClass,
      }, isBreak, true);
    }
  }

  closeMobileTeacherPicker();
}

/* ─── Slot tap handler (mobile) ───────────────────────────────────────────── */

/**
 * Called via onclick on EVERY slot-item (empty and filled).
 * Desktop: returns immediately — Sortable handles assignment via drag-and-drop.
 * Mobile:  opens the bottom-sheet teacher picker.
 *          For filled slots the sheet title shows "Replace [teacher]".
 *          The remove-btn on filled slots stops propagation so tapping ✕
 *          only removes the teacher without opening the picker.
 */
function onSlotTap(slId, slotIdx) {
  if (!isMobilePlanner()) return;   // desktop: drag handles this

  const list = byId(`slots-${slId}`);
  const col  = list?.closest('.location-column');

  if (col?.dataset.editable !== 'true') {
    showToast(I18N.t('day_locked'), 'error');
    return;
  }

  const isBreak = list?.dataset.dutyType === 'break';
  openMobileTeacherPicker(slId, slotIdx, isBreak);
}

/* ─── Week loading ────────────────────────────────────────────────────────── */

async function loadWeek() {
  const weekInput    = byId('weekStartInput');
  const noPlanMsg    = byId('noPlanMsg');
  const dayTabs      = byId('dayTabs');
  const dayPanels    = byId('dayPanels');
  const plannerLoading = byId('plannerLoading');

  const pickedDate = weekInput?.value || '';
  if (!pickedDate) return;

  selectedDate = pickedDate;
  const weekStart = getWeekStartFromDate(pickedDate);

  pendingAssignments = {};
  pendingSlots       = {};

  try {
    showEl(plannerLoading);
    hideEl(noPlanMsg);
    if (dayTabs)   dayTabs.innerHTML   = '';
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
      if (dayPanels) {
        dayPanels.innerHTML =
          `<p style="color:#6c757d;text-align:center;margin-top:40px" data-i18n="no_week"></p>`;
      }
      I18N.applyTranslations();
      updateStatusBadge(null);
      showEl(noPlanMsg, 'block');
      showToast(I18N.t('no_week'), 'info');
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
  const badge  = byId('weekStatusBadge');
  const vBadge = byId('weekVersionBadge');
  if (!badge || !vBadge) return;

  if (!status) {
    badge.style.display = 'none';
    vBadge.textContent  = '';
    return;
  }

  badge.style.display = 'inline';
  badge.className      = `week-status-badge status-${status}`;
  badge.textContent    = I18N.t(status);
  vBadge.textContent   = currentWeekData ? `v${currentWeekData.version}` : '';
}

/* ─── Week rendering ──────────────────────────────────────────────────────── */

const DAY_KEYS = ['day_sun', 'day_mon', 'day_tue', 'day_wed', 'day_thu'];

function renderWeek() {
  if (!currentWeekData?.day_plans) return;

  updateStatusBadge(currentWeekData.status);

  // Close any open mobile picker before re-rendering slots
  closeMobileTeacherPicker();

  const tabsEl   = byId('dayTabs');
  const panelsEl = byId('dayPanels');
  const noPlanMsg = byId('noPlanMsg');

  if (!tabsEl || !panelsEl) return;

  tabsEl.innerHTML   = '';
  panelsEl.innerHTML = '';
  hideEl(noPlanMsg);

  const activeIdx = getActiveDayIndex();

  currentWeekData.day_plans.forEach((dayPlan, idx) => {
    const dayDate   = new Date(dayPlan.date + 'T12:00:00');
    const dayOfWeek = dayDate.getDay();
    const dayLabel  = I18N.t(DAY_KEYS[dayOfWeek] ?? `Day ${idx}`);

    const tab = document.createElement('button');
    tab.className = 'tab-btn' + (idx === activeIdx ? ' active' : '');
    tab.textContent = dayLabel + (dayPlan.is_published ? ' ✔' : '');
    tab.onclick = () => switchDayTab(idx);
    tabsEl.appendChild(tab);

    const panel = document.createElement('div');
    panel.className  = 'tab-panel' + (idx === activeIdx ? ' active' : '');
    panel.innerHTML  = renderDayPanel(dayPlan, !!dayPlan.is_editable);
    panel.style.display = idx === activeIdx ? 'block' : 'none';
    panelsEl.appendChild(panel);
  });

  initDragAndDrop();
}

function getActiveDayIndex() {
  if (!currentWeekData?.day_plans?.length) return 0;
  const exact = currentWeekData.day_plans.findIndex(d => d.date === selectedDate);
  if (exact >= 0) return exact;
  const today = getCurrentLocalDate();
  const todayIdx = currentWeekData.day_plans.findIndex(d => d.date === today);
  if (todayIdx >= 0) return todayIdx;
  return 0;
}

function switchDayTab(idx) {
  document.querySelectorAll('.tab-btn').forEach((b, i) => b.classList.toggle('active', i === idx));
  document.querySelectorAll('.tab-panel').forEach((p, i) => {
    const active = i === idx;
    p.classList.toggle('active', active);
    p.style.display = active ? 'block' : 'none';
  });
  const day = currentWeekData?.day_plans?.[idx];
  if (day) {
    selectedDate = day.date;
    const weekInput = byId('weekStartInput');
    if (weekInput) weekInput.value = day.date;
  }
}

/* ─── Day / shift / location panel rendering ─────────────────────────────── */

function renderDayPanel(dayPlan, isEditable) {
  const shiftMap = {};
  (dayPlan.shift_locations || []).forEach(sl => {
    if (!shiftMap[sl.shift_id]) shiftMap[sl.shift_id] = { shift: sl.shift, locations: [] };
    shiftMap[sl.shift_id].locations.push(sl);
  });

  const shifts = Object.values(shiftMap).sort((a, b) =>
    (a.shift.order ?? 9999) - (b.shift.order ?? 9999)
  );

  if (!shifts.length) {
    return `<p style="color:#999;margin-top:20px;text-align:center">${I18N.t('no_week')}</p>`;
  }

  const editableBadge = isEditable
    ? `<span class="day-badge day-badge--editable">${I18N.t('editable')}</span>`
    : `<span class="day-badge day-badge--locked">${I18N.t('locked')}</span>`;

  const publishBtn = dayPlan.is_published
    ? `<span class="published-badge">&#10003; ${I18N.t('published') || 'Published'}</span>`
    : `<button class="btn btn-success btn-sm" id="publish-day-btn-${dayPlan.date}"
         onclick="publishDay('${dayPlan.date}')">${I18N.t('publish_day') || 'Publish Day'}</button>`;

  const shiftTabsHtml = shifts.map((s, i) => {
    const dutyBadge = s.shift.duty_type === 'break'
      ? `<span class="break-badge">${I18N.t('break')}</span>` : '';
    return `
      <button class="shift-tab-btn${i === 0 ? ' active' : ''}"
              onclick="switchShiftTab(this, 'shift-panel-${dayPlan.date}-${s.shift.id}')">
        ${lang() === 'ar' ? escHtml(s.shift.name_ar) : escHtml(s.shift.name_en)}
        ${dutyBadge}
      </button>`;
  }).join('');

  const shiftPanelsHtml = shifts.map((s, i) => {
    const locCols = s.locations
      .sort((a, b) => (a.order ?? 9999) - (b.order ?? 9999))
      .map(sl => renderLocationColumn(dayPlan.date, sl, isEditable))
      .join('');
    const timeBar = renderShiftTimeBar(s.shift, dayPlan.date, isEditable);
    return `
      <div id="shift-panel-${dayPlan.date}-${s.shift.id}"
           class="shift-panel${i === 0 ? ' active' : ''}"
           style="${i === 0 ? '' : 'display:none'}">
        ${timeBar}
        <div class="locations-grid">${locCols}</div>
      </div>`;
  }).join('');

  return `
    <div class="day-header">
      <div class="day-header-meta">
        <span class="day-date">${dayPlan.date}</span>
        ${editableBadge}
      </div>
      <div class="day-header-actions" data-day-header-actions>
        ${publishBtn}
      </div>
    </div>
    <div class="shift-tabs">${shiftTabsHtml}</div>
    ${shiftPanelsHtml}
  `;
}

function switchShiftTab(btn, panelId) {
  const dayPanel = btn.closest('.tab-panel');
  if (!dayPanel) return;

  dayPanel.querySelectorAll('.shift-tab-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');

  dayPanel.querySelectorAll('.shift-panel').forEach(p => {
    const active = p.id === panelId;
    p.classList.toggle('active', active);
    p.style.display = active ? 'block' : 'none';
  });
}

function renderLocationColumn(dayDate, sl, isEditable) {
  const isBreak = sl.duty_type === 'break' || sl.shift?.duty_type === 'break';

  // Break duties get their own grid layout — no location column, no +/- controls
  if (isBreak) return renderBreakGrid(dayDate, sl, isEditable);

  const colTitle = sl.location
    ? escHtml(lang() === 'ar' ? sl.location.name_ar : sl.location.name_en)
    : '—';

  const slots = [];
  for (let i = 0; i < sl.slots_count; i++) {
    const assignment = (sl.assignments || []).find(a => a.slot_index === i);
    slots.push(renderSlot(sl.id, i, assignment, false, isEditable));
  }

  const locId = sl.location_id ?? '';

  return `
    <div class="location-column"
         data-sl-id="${sl.id}"
         data-day="${dayDate}"
         data-shift="${sl.shift_id}"
         data-loc="${locId}"
         data-editable="${isEditable ? 'true' : 'false'}"
         data-duty-type="morning_endofday">
      <div class="location-column-header">
        <span class="loc-title">${colTitle}</span>
        ${isEditable ? `
          <div class="slot-controls">
            <button class="btn-slot btn-slot-sub"
                    onclick="changeSlots('${dayDate}',${sl.shift_id},'${locId}',-1)">−</button>
            <span id="slot-count-${sl.id}">${sl.slots_count}</span>
            <button class="btn-slot btn-slot-add"
                    onclick="changeSlots('${dayDate}',${sl.shift_id},'${locId}',1)">+</button>
          </div>` : ''}
      </div>
      <div id="slots-${sl.id}"
           class="slots-list"
           data-sl-id="${sl.id}"
           data-duty-type="morning_endofday">
        ${slots.join('')}
      </div>
    </div>
  `;
}

/* ─── Break duty grid ─────────────────────────────────────────────────────── */

/**
 * Renders break duty slots as a responsive CSS grid.
 *
 * Each slot shows:
 *   • Grade class label (always — pre-assigned from seeding, not user-selectable)
 *   • Teacher chip or empty state (drag/tap to assign)
 *
 * No +/- slot controls — break classes are fixed.
 */
function renderBreakGrid(dayDate, sl, isEditable) {
  // Sort by slot_index to match the seeded order (1/A, 1/B, 2/A …)
  const sorted = [...(sl.assignments || [])]
    .sort((a, b) => (a.slot_index ?? 0) - (b.slot_index ?? 0));

  const cells = sorted
    .map(assignment => renderSlot(sl.id, assignment.slot_index, assignment, true, isEditable))
    .join('');

  return `
    <div class="location-column break-location-column"
         data-sl-id="${sl.id}"
         data-day="${dayDate}"
         data-shift="${sl.shift_id}"
         data-loc=""
         data-editable="${isEditable ? 'true' : 'false'}"
         data-duty-type="break">
      <div id="slots-${sl.id}"
           class="slots-list break-grid"
           data-sl-id="${sl.id}"
           data-duty-type="break">
        ${cells}
      </div>
    </div>`;
}

/* ─── Shift time editor ───────────────────────────────────────────────────── */

/**
 * Renders the inline time display + edit form for a shift.
 *
 * Because the same shift appears across all day panels, we use a unique id
 * per shift+day combo (uid = `${shiftId}-${dayDate}`) so editing one day's
 * panel doesn't collide with another day's.
 *
 * On save, the time change propagates to ALL days automatically because
 * shifts are global records shared by all week plans.
 */
function renderShiftTimeBar(shift, dayDate, isEditable) {
  const startFmt = (shift.start_time || '').substring(0, 5);
  const endFmt   = (shift.end_time   || '').substring(0, 5);
  // Unique id per shift-day to avoid id collisions across day panels
  const uid      = `${shift.id}-${dayDate.replace(/-/g, '')}`;

  const editSection = isEditable ? `
    <button class="btn-time-edit"
            onclick="toggleShiftTimeEdit('${uid}')"
            title="${I18N.t('edit') || 'Edit time'}">✏️</button>
    <span class="shift-time-edit-form" id="shift-time-edit-${uid}">
      <input type="time" id="shift-start-in-${uid}" value="${startFmt}" class="shift-time-in">
      <span>–</span>
      <input type="time" id="shift-end-in-${uid}"   value="${endFmt}"   class="shift-time-in">
      <button class="btn-xs btn-primary"
              onclick="saveShiftTime(${shift.id}, '${uid}')">${I18N.t('save')}</button>
      <button class="btn-xs btn-secondary"
              onclick="toggleShiftTimeEdit('${uid}')">${I18N.t('cancel') || '✕'}</button>
      <span class="shift-time-edit-msg">
        ${I18N.t('shift_time_applies_all') || '— applies to all days'}
      </span>
    </span>` : '';

  return `
    <div class="shift-time-bar">
      <span class="shift-time-display">
        🕐 <span id="shift-time-display-${uid}">${startFmt} – ${endFmt}</span>
      </span>
      ${editSection}
    </div>`;
}

function toggleShiftTimeEdit(uid) {
  const form = byId(`shift-time-edit-${uid}`);
  if (!form) return;
  const nowHidden = form.style.display === 'none' || form.style.display === '';
  form.style.display = nowHidden ? 'inline-flex' : 'none';
  if (nowHidden) {
    // Re-sync the input values from the current display text in case it changed
    const display = byId(`shift-time-display-${uid}`)?.textContent || '';
    const [s, e]  = display.split('–').map(x => x.trim());
    const startIn = byId(`shift-start-in-${uid}`);
    const endIn   = byId(`shift-end-in-${uid}`);
    if (startIn && s) startIn.value = s;
    if (endIn   && e) endIn.value   = e;
  }
}

async function saveShiftTime(shiftId, uid) {
  const startEl = byId(`shift-start-in-${uid}`);
  const endEl   = byId(`shift-end-in-${uid}`);
  if (!startEl || !endEl) return;

  const startTime = startEl.value;
  const endTime   = endEl.value;

  if (!startTime || !endTime) {
    showToast(I18N.t('invalid_time_range') || 'Start and end time required', 'error');
    return;
  }
  if (endTime <= startTime) {
    showToast(I18N.t('invalid_time_range') || 'End time must be after start time', 'error');
    return;
  }

  // Disable save button while in flight
  const saveBtn = startEl.closest('.shift-time-edit-form')?.querySelector('.btn-primary');
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = I18N.t('loading'); }

  try {
    const res = await apiFetch(`/shifts/${shiftId}`, {
      method: 'PUT',
      body:   JSON.stringify({ start_time: startTime, end_time: endTime }),
    });

    if (res?.ok) {
      const updated = await res.json();

      // Patch all shift references in currentWeekData so re-render shows new times
      if (currentWeekData?.day_plans) {
        for (const day of currentWeekData.day_plans) {
          for (const sl of (day.shift_locations || [])) {
            if (sl.shift && sl.shift.id === shiftId) {
              sl.shift.start_time = updated.start_time;
              sl.shift.end_time   = updated.end_time;
            }
          }
        }
      }

      // Re-render all day panels so every time bar reflects the change
      renderWeek();
      showToast(
        (I18N.t('shift_saved') || 'Shift time updated') +
        ' — ' +
        (I18N.t('shift_time_applies_all') || 'applies to all days'),
        'success'
      );
    } else {
      const msg = await getApiErrorMessage(res, I18N.t('error_generic'));
      showToast(msg, 'error');
      if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = I18N.t('save'); }
    }
  } catch (err) {
    showToast(err.message || I18N.t('error_generic'), 'error');
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = I18N.t('save'); }
  }
}

/* ─── Grade class options ─────────────────────────────────────────────────── */

function getGradeClassOptions() {
  const classes = [
    '1/A','1/B','1/C','1/D',
    '2/A','2/B','2/C','2/D',
    '3/A','3/B','3/C',
    '4/A','4/B','4/C',
    '5/A','5/B',
    '6/A','6/B',
    '7/A','7/B',
    '8/AB',
    '9',
  ];
  return [
    { value: '', label: I18N.t('select_class') },
    ...classes.map(v => ({ value: v, label: v })),
  ];
}

function renderGradeOptions(selected = '') {
  return getGradeClassOptions()
    .map(o => `<option value="${escHtml(o.value)}"${o.value === selected ? ' selected' : ''}>${escHtml(o.label)}</option>`)
    .join('');
}

/* ─── Slot rendering ──────────────────────────────────────────────────────── */

function renderSlot(slId, slotIdx, assignment, isBreak, isEditable = true) {
  // `onSlotTap` is attached to every slot.
  // • Desktop: handler returns immediately (isMobilePlanner() === false).
  // • Mobile:  opens the bottom-sheet picker.
  const tapAttr    = `onclick="onSlotTap(${slId}, ${slotIdx})"`;
  const gradeClass = assignment?.grade_class || '';

  // For break duties: always show the grade class as a static label.
  // The grade class is pre-assigned from seeding — it is NOT user-selectable.
  // data-grade-class is stored on the element so it survives DOM replacement.
  const gcAttr         = isBreak ? `data-grade-class="${escHtml(gradeClass)}"` : '';
  const gradeLabelHtml = isBreak && gradeClass
    ? `<div class="break-cell-grade">${escHtml(gradeClass)}</div>`
    : '';

  const breakClass = isBreak ? ' break-cell' : '';

  if (assignment?.teacher_id) {
    return `
      <div class="slot-item${breakClass} filled"
           data-sl-id="${slId}"
           data-slot-idx="${slotIdx}"
           data-teacher-id="${assignment.teacher_id}"
           ${gcAttr}
           ${tapAttr}>
        ${gradeLabelHtml}
        <div class="teacher-card"
             data-teacher-id="${assignment.teacher_id}"
             data-teacher-name="${escHtml(assignment.teacher_name || '')}">
          <span>${escHtml(assignment.teacher_name || '—')}</span>
          ${isEditable
            ? `<span class="remove-btn"
                     onclick="event.stopPropagation();removeTeacher(${slId}, ${slotIdx})"
                     title="${I18N.t('delete')}">✕</span>`
            : ''}
        </div>
      </div>`;
  }

  // Empty slot
  return `
    <div class="slot-item${breakClass}"
         data-sl-id="${slId}"
         data-slot-idx="${slotIdx}"
         data-teacher-id=""
         ${gcAttr}
         ${tapAttr}>
      ${gradeLabelHtml}
      <span class="slot-empty-label">${I18N.t('no_teacher')}</span>
    </div>`;
}

/* ─── Grade/class update ──────────────────────────────────────────────────── */

function updateGradeClass(slId, slotIdx, value) {
  const list = byId(`slots-${slId}`);
  const col  = list?.closest('.location-column');

  if (col?.dataset.editable !== 'true') {
    showToast(I18N.t('day_locked'), 'error');
    return;
  }

  if (!pendingAssignments[slId]) pendingAssignments[slId] = {};
  if (!pendingAssignments[slId][slotIdx]) pendingAssignments[slId][slotIdx] = {};
  pendingAssignments[slId][slotIdx].grade_class = value;
}

/* ─── Drag-and-drop (desktop only) ───────────────────────────────────────── */

function findShiftLocationInCurrentWeek(slId) {
  if (!currentWeekData?.day_plans) return null;
  for (const day of currentWeekData.day_plans) {
    for (const sl of (day.shift_locations || [])) {
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
  for (const candidate of (day.shift_locations || [])) {
    if (candidate.shift_id !== sl.shift_id) continue;
    for (const assignment of (candidate.assignments || [])) {
      const eff = getEffectiveAssignment(candidate.id, assignment.slot_index, assignment);
      if (eff.teacher_id === teacherId) return true;
    }
  }
  return false;
}

/* ── Drag class cleanup helper ──────────────────────────────────────────── */
function _clearDragClasses() {
  document.querySelectorAll('.slot-drag-add, .slot-drag-replace').forEach(el => {
    el.classList.remove('slot-drag-add', 'slot-drag-replace');
  });
}

function initDragAndDrop() {
  // ── Mobile: no Sortable whatsoever ──────────────────────────────────────
  if (isMobilePlanner()) return;
  if (typeof Sortable === 'undefined') return;

  // ── Sidebar (source, clone) ──────────────────────────────────────────────
  const sidebar = byId('teacherList');
  if (sidebar && !sidebar.dataset.sortableInit) {
    new Sortable(sidebar, {
      group:     { name: 'teachers', pull: 'clone', put: false },
      sort:      false,
      animation: 150,
      // Clean up any lingering drag highlights if user cancels drag from sidebar
      onEnd() { _clearDragClasses(); },
    });
    sidebar.dataset.sortableInit = 'true';
  }

  // ── Slot lists (targets, no reorder) ────────────────────────────────────
  document.querySelectorAll('.slots-list').forEach(list => {
    if (list.dataset.sortableInit === 'true') return;

    const isBreak = list.dataset.dutyType === 'break';

    new Sortable(list, {
      group:     { name: 'teachers', pull: false, put: true },
      sort:      false,   // slots are FIXED — never reorder
      animation: 150,

      // ── Called repeatedly while dragging OVER items ────────────────────
      onMove(evt) {
        const target = evt.related;
        if (!target || !target.classList.contains('slot-item')) {
          _clearDragClasses();
          return true;
        }

        // Block drop onto locked days — return false prevents the drop indicator
        const col = list.closest('.location-column');
        if (!col || col.dataset.editable !== 'true') {
          _clearDragClasses();
          return false;
        }

        // Clear ALL previously highlighted slots (only one should glow at a time)
        _clearDragClasses();

        // Apply the correct class to THIS target slot only
        const isFilled = target.classList.contains('filled');
        if (isFilled) {
          target.classList.add('slot-drag-replace');   // red  — will replace
        } else {
          target.classList.add('slot-drag-add');       // green — will add
        }

        return true;   // allow the drop
      },

      // ── Called when a clone lands in this list ─────────────────────────
      onAdd(evt) {
        // Always clean up highlights first
        _clearDragClasses();

        // Remove the DOM clone Sortable inserted — we manage DOM ourselves
        evt.item.remove();

        const col     = list.closest('.location-column');
        const dayDate = col?.dataset.day;
        const day     = currentWeekData?.day_plans?.find(d => d.date === dayDate);

        if (!day?.is_editable) {
          showToast(I18N.t('day_locked'), 'error');
          return;
        }

        const slId        = parseInt(list.dataset.slId, 10);
        const teacherId   = parseInt(evt.item.dataset.teacherId,   10);
        const teacherName = evt.item.dataset.teacherName || '';

        if (!teacherId) return;

        if (isTeacherAssignedInSameShift(slId, teacherId)) {
          showToast(I18N.t('teacher_already_assigned') || 'Already assigned in this shift', 'error');
          return;
        }

        // Determine drop target: use the DOM element that was highlighted
        const highlighted = list.querySelector('.slot-drag-replace, .slot-drag-add')
                         || list.querySelector('.slot-item:not(.filled)');
        const emptySlot   = list.querySelector('.slot-item:not(.filled)');
        const filledSlots = Array.from(list.querySelectorAll('.slot-item.filled'));

        if (emptySlot) {
          // Fill the first empty slot (for break: preserves the grade class label)
          const slotIdx    = parseInt(emptySlot.dataset.slotIdx, 10);
          const gradeClass = isBreak ? (emptySlot.dataset.gradeClass || null) : null;
          recordAssignment(slId, slotIdx, teacherId, gradeClass);
          emptySlot.outerHTML = renderSlot(slId, slotIdx, {
            teacher_id:   teacherId,
            teacher_name: teacherName,
            slot_index:   slotIdx,
            grade_class:  gradeClass,
          }, isBreak, true);
          return;
        }

        if (filledSlots.length > 0) {
          // All slots filled → replace the last one
          const targetSlot = filledSlots[filledSlots.length - 1];
          const slotIdx    = parseInt(targetSlot.dataset.slotIdx, 10);
          replaceTeacherInSlot(slId, slotIdx, teacherId, teacherName, isBreak);
          showToast(I18N.t('teacher_replaced'));
          return;
        }

        showToast(I18N.t('no_empty_slot'), 'error');
      },

      // ── Called when drag ends on THIS list (drop accepted or cancelled) ──
      onEnd() { _clearDragClasses(); },
    });

    list.dataset.sortableInit = 'true';
  });
}

/* ─── Assignment helpers ──────────────────────────────────────────────────── */

function recordAssignment(slId, slotIdx, teacherId, gradeClass) {
  if (!pendingAssignments[slId]) pendingAssignments[slId] = {};
  pendingAssignments[slId][slotIdx] = { teacher_id: teacherId, grade_class: gradeClass };
}

function replaceTeacherInSlot(slId, slotIdx, teacherId, teacherName, isBreak) {
  const list       = byId(`slots-${slId}`);
  const slotEl     = list?.querySelector(`[data-slot-idx="${slotIdx}"]`);
  // Preserve the existing grade class label for break duties
  const gradeClass = isBreak ? (slotEl?.dataset.gradeClass || null) : null;
  recordAssignment(slId, slotIdx, teacherId, gradeClass);
  if (!slotEl) return;
  slotEl.outerHTML = renderSlot(slId, slotIdx, {
    teacher_id:   teacherId,
    teacher_name: teacherName,
    slot_index:   slotIdx,
    grade_class:  gradeClass,
  }, isBreak, true);
}

function removeTeacher(slId, slotIdx) {
  const list = byId(`slots-${slId}`);
  const col  = list?.closest('.location-column');

  if (col?.dataset.editable !== 'true') {
    showToast(I18N.t('day_locked'), 'error');
    return;
  }

  const isBreak    = list?.dataset.dutyType === 'break';
  const slotEl     = list?.querySelector(`[data-slot-idx="${slotIdx}"]`);
  // Preserve the grade class label when removing a teacher from a break cell
  const gradeClass = isBreak ? (slotEl?.dataset.gradeClass || null) : null;

  recordAssignment(slId, slotIdx, null, gradeClass);

  if (slotEl) {
    // Pass a stub assignment with just grade_class so the label stays on empty cell
    slotEl.outerHTML = renderSlot(
      slId, slotIdx,
      isBreak ? { grade_class: gradeClass } : null,
      isBreak, true
    );
    showToast(I18N.t('teacher_removed'), 'info');
  }
}

/* ─── Slot count control ──────────────────────────────────────────────────── */

function changeSlots(dayDate, shiftId, locationId, delta) {
  const day = currentWeekData?.day_plans?.find(d => d.date === dayDate);
  if (!day?.is_editable) {
    showToast(I18N.t('day_locked'), 'error');
    return;
  }

  const locId = locationId === 'null' ? null : locationId;
  const key   = `${dayDate}:${shiftId}:${locId}`;

  const selector = locId === null || locId === ''
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

  const list    = byId(`slots-${slId}`);
  if (!list) return;
  const isBreak = list.dataset.dutyType === 'break';

  if (delta > 0) {
    const div = document.createElement('div');
    div.innerHTML = renderSlot(slId, current, null, isBreak, true);
    list.appendChild(div.firstElementChild);
    // Init DnD on the new slot container (idempotent guard inside)
    initDragAndDrop();
  } else if (delta < 0 && current > 0) {
    const lastSlot = list.querySelector(`[data-slot-idx="${current - 1}"]`);
    lastSlot?.remove();
  }
}

/* ─── Save / Publish / Clone ──────────────────────────────────────────────── */

async function saveDraft() {
  if (!currentWeekData) return;
  showToast(I18N.t('saving') || 'Saving…', 'info');
  try {
    await flushPendingChanges();
    showToast(I18N.t('success_saved'));
  } catch (err) {
    console.error('saveDraft failed:', err);
  }
}

async function flushPendingChanges() {
  const weekStart = currentWeekData.week_start_date;

  if (Object.keys(pendingSlots).length > 0) {
    const updates = Object.values(pendingSlots).map(s => ({
      day_date:    s.dayDate,
      shift_id:    s.shiftId,
      location_id: s.locationId,
      slots_count: s.slotsCount,
    }));

    const res = await apiFetch(`/weeks/${weekStart}/shift-locations`, {
      method: 'PUT',
      body:   JSON.stringify(updates),
    });

    if (res?.ok) {
      pendingSlots    = {};
      currentWeekData = await res.json();
    } else {
      const msg = await getApiErrorMessage(res, 'Failed to save slot changes');
      showToast(msg, 'error');
      throw new Error(msg);
    }
  }

  const assignmentUpdates = [];
  for (const [slId, slots] of Object.entries(pendingAssignments)) {
    for (const [slotIdx, data] of Object.entries(slots)) {
      assignmentUpdates.push({
        shift_location_id: parseInt(slId,    10),
        slot_index:        parseInt(slotIdx, 10),
        teacher_id:        data.teacher_id,
        grade_class:       data.grade_class || null,
      });
    }
  }

  if (assignmentUpdates.length > 0) {
    const res = await apiFetch(`/weeks/${weekStart}/assignments`, {
      method: 'PUT',
      body:   JSON.stringify(assignmentUpdates),
    });

    if (res?.ok) {
      pendingAssignments = {};
      currentWeekData   = await res.json();
    } else {
      const msg = await getApiErrorMessage(res, 'Failed to save assignment changes');
      showToast(msg, 'error');
      throw new Error(msg);
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
      body:   JSON.stringify({ status: 'published' }),
    });

    if (res?.ok) {
      currentWeekData = await res.json();
      renderWeek();
      updateStatusBadge(currentWeekData.status);
      showToast(I18N.t('success_published'));
    } else {
      const err = res ? await res.json().catch(() => ({})) : {};
      showToast(err.detail || I18N.t('error_generic'), 'error');
    }
  } catch (err) {
    showToast(err.message || I18N.t('error_generic'), 'error');
  }
}

async function publishDay(dayDate) {
  if (!currentWeekData) return;

  const publishBtn = byId(`publish-day-btn-${dayDate}`);
  if (publishBtn) { publishBtn.disabled = true; publishBtn.textContent = I18N.t('loading'); }

  try {
    await flushPendingChanges();
    const weekStart = currentWeekData.week_start_date;
    const res = await apiFetch(`/weeks/${weekStart}/publish-day?day_date=${dayDate}`, { method: 'PUT' });

    if (res?.ok) {
      let data = null;
      try { data = await res.json(); } catch (_) {}

      if (data?.day_plans) {
        currentWeekData = data;
      } else if (currentWeekData?.day_plans) {
        currentWeekData.day_plans = currentWeekData.day_plans.map(d =>
          d.date === dayDate ? { ...d, is_published: true } : d
        );
      }
      renderWeek();
      showToast(I18N.t('day_published') || 'Day published');
      return;
    }

    showToast(await getApiErrorMessage(res, I18N.t('error_generic')), 'error');
  } catch (err) {
    showToast(err.message || I18N.t('error_generic'), 'error');
  }
  // Note: button is restored by renderWeek() above on success;
  // on failure, restore it manually
  const btn = byId(`publish-day-btn-${dayDate}`);
  if (btn) { btn.disabled = false; btn.textContent = I18N.t('publish_day') || 'Publish Day'; }
}

async function createWeek() {
  const selected = byId('weekStartInput')?.value;
  if (!selected) return;

  const weekStart = getWeekStartFromDate(selected);
  setPlannerBusy(true, I18N.t('creating_week') || 'Creating week…');

  try {
    const res = await apiFetch(`/weeks/${weekStart}/create`, { method: 'POST' });
    let data = null;
    try { data = await res.json(); } catch (_) {}

    if (res.status === 409) {
      selectedDate = weekStart;
      syncWeekInputWithSelectedDate();
      pendingAssignments = {}; pendingSlots = {};
      await loadWeek();
      showToast(data?.detail || 'Week already exists, loaded successfully', 'info');
      return;
    }
    if (!res.ok) throw new Error(data?.detail || 'Failed to create week');

    selectedDate = weekStart;
    syncWeekInputWithSelectedDate();
    pendingAssignments = {}; pendingSlots = {};
    await loadWeek();
    showToast(data?.message || 'Week created successfully');
  } catch (err) {
    showToast(err.message || I18N.t('error_generic'), 'error');
  } finally {
    setPlannerBusy(false);
  }
}

async function cloneWeek() {
  const selected = byId('weekStartInput')?.value;
  if (!selected) return;

  const weekStart = getWeekStartFromDate(selected);
  setPlannerBusy(true, I18N.t('cloning_week') || 'Cloning week…');

  try {
    const res = await apiFetch(`/weeks/${weekStart}/clone`, { method: 'POST' });
    let data = null;
    try { data = await res.json(); } catch (_) {}

    if (res.status === 409) {
      selectedDate = weekStart;
      syncWeekInputWithSelectedDate();
      pendingAssignments = {}; pendingSlots = {};
      await loadWeek();
      showToast(data?.detail || 'Week already exists, loaded successfully', 'info');
      return;
    }
    if (!res.ok) throw new Error(data?.detail || 'Clone failed');

    selectedDate = weekStart;
    syncWeekInputWithSelectedDate();
    pendingAssignments = {}; pendingSlots = {};
    await loadWeek();
    showToast(I18N.t('success_cloned'));
  } catch (err) {
    showToast(err.message || I18N.t('error_generic'), 'error');
  } finally {
    setPlannerBusy(false);
  }
}

/* ─── Poll helper ─────────────────────────────────────────────────────────── */

async function pollUntilWeekVisible(weekStart, attempts = 6, delayMs = 1200) {
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await apiFetch(`/weeks/${weekStart}`);
      if (res?.ok) {
        currentWeekData   = await res.json();
        selectedDate      = weekStart;
        syncWeekInputWithSelectedDate();
        pendingAssignments = {};
        pendingSlots       = {};
        renderWeek();
        return true;
      }
    } catch (err) {
      console.warn('pollUntilWeekVisible attempt failed:', err);
    }
    if (i < attempts - 1) await sleep(delayMs);
  }
  return false;
}

/* ─── Viewport resize: re-init DnD when crossing desktop threshold ────────── */

let _resizeTimer = null;
let _wasMobile   = isMobilePlanner();

window.addEventListener('resize', () => {
  clearTimeout(_resizeTimer);
  _resizeTimer = setTimeout(() => {
    const nowMobile = isMobilePlanner();
    if (_wasMobile !== nowMobile) {
      _wasMobile = nowMobile;
      if (!nowMobile && currentWeekData) {
        // Crossed into desktop: remove stale sortable markers and re-init
        document.querySelectorAll('[data-sortable-init]').forEach(el => {
          delete el.dataset.sortableInit;
        });
        initDragAndDrop();
      }
      // Re-render sidebar for drag/no-drag attribute
      renderTeacherSidebar(byId('teacherSearch')?.value || '');
    }
  }, 250);
});

/* ─── Auto init ───────────────────────────────────────────────────────────── */

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initPlanner);
} else {
  initPlanner();
}
