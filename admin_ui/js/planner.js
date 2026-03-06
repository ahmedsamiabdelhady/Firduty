/**
 * planner.js — Firduty Admin Week Planner
 * Handles: week loading, day/shift tabs, drag-and-drop, slot management
 */

const API_BASE = localStorage.getItem('firduty_api') || 'https://naval-donnamarie-firduty-6e288803.koyeb.app/';
const TOKEN = () => localStorage.getItem('firduty_token');

let currentWeekData = null;   // Full week plan JSON from API
let allTeachers = [];          // All active teachers
let pendingAssignments = {};   // slot_location_id -> { slot_index -> teacher_id }
let pendingSlots = {};         // day_date:shift_id:location_id -> slots_count
let lang = () => I18N.getLang();

// ─── Auth Helper ─────────────────────────────────────────────────────────────

function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${TOKEN()}`
  };
}

function logout() {
  localStorage.removeItem('firduty_token');
  window.location.href = 'login.html';
}

// ─── Toast ───────────────────────────────────────────────────────────────────

function showToast(message, type = 'success') {
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = message;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// ─── API Helpers ──────────────────────────────────────────────────────────────

async function apiFetch(path, opts = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: authHeaders(),
    ...opts
  });
  if (res.status === 401) { logout(); return null; }
  return res;
}

// ─── Initialization ───────────────────────────────────────────────────────────

async function initPlanner() {
  await loadTeachers();
  // Set week input to current Sunday
  const todaySunday = getCurrentSunday();
  document.getElementById('weekStartInput').value = todaySunday;
  await loadWeek();
}

function getCurrentSunday() {
  const d = new Date();
  const day = d.getDay(); // 0=Sun
  d.setDate(d.getDate() - day);
  return d.toISOString().slice(0, 10);
}

function onWeekSelected() { /* user changed date input */ }

async function loadTeachers() {
  const res = await apiFetch('/teachers/');
  if (!res || !res.ok) return;
  allTeachers = await res.json();
  renderTeacherSidebar();
}

function renderTeacherSidebar() {
  const list = document.getElementById('teacherList');
  if (!allTeachers.length) {
    list.innerHTML = '<p style="font-size:0.8rem;color:#999">No teachers</p>';
    return;
  }
  list.innerHTML = allTeachers.map(t =>
    `<div class="teacher-list-item" 
          data-teacher-id="${t.id}" 
          data-teacher-name="${t.name}" 
          draggable="true">${t.name}</div>`
  ).join('');
}

// ─── Week Loading ─────────────────────────────────────────────────────────────

async function loadWeek() {
  const weekStart = document.getElementById('weekStartInput').value;
  if (!weekStart) return;

  pendingAssignments = {};
  pendingSlots = {};

  const res = await apiFetch(`/weeks/${weekStart}`);
  if (!res) return;

  if (res.status === 404) {
    currentWeekData = null;
    document.getElementById('noPlanMsg').style.display = 'block';
    document.getElementById('dayTabs').innerHTML = '';
    document.getElementById('dayPanels').innerHTML = '<p style="color:#6c757d;text-align:center;margin-top:40px" data-i18n="no_week"></p>';
    I18N.applyTranslations();
    updateStatusBadge(null);
    return;
  }

  currentWeekData = await res.json();
  renderWeek();
}

function updateStatusBadge(status) {
  const badge = document.getElementById('weekStatusBadge');
  const versionBadge = document.getElementById('weekVersionBadge');
  if (!status) {
    badge.style.display = 'none';
    versionBadge.textContent = '';
    return;
  }
  badge.style.display = 'inline';
  badge.className = `week-status-badge status-${status}`;
  badge.textContent = I18N.t(status);
  versionBadge.textContent = `v${currentWeekData.version}`;
}

// ─── Week Rendering ───────────────────────────────────────────────────────────

const DAY_KEYS = ['day_sun', 'day_mon', 'day_tue', 'day_wed', 'day_thu'];

function renderWeek() {
  if (!currentWeekData || !currentWeekData.day_plans) return;

  updateStatusBadge(currentWeekData.status);

  const tabsEl = document.getElementById('dayTabs');
  const panelsEl = document.getElementById('dayPanels');
  tabsEl.innerHTML = '';
  panelsEl.innerHTML = '';

  currentWeekData.day_plans.forEach((dayPlan, idx) => {
    const dayDate = new Date(dayPlan.date + 'T00:00:00');
    const dayOfWeek = dayDate.getDay(); // 0=Sun
    const dayLabel = I18N.t(DAY_KEYS[dayOfWeek] || `Day ${idx}`);

    // Tab button
    const btn = document.createElement('button');
    btn.className = `tab-btn${idx === 0 ? ' active' : ''}`;
    btn.setAttribute('data-day-idx', idx);
    btn.textContent = dayLabel;
    btn.onclick = () => switchDayTab(idx);
    tabsEl.appendChild(btn);

    // Panel
    const panel = document.createElement('div');
    panel.className = `tab-panel${idx === 0 ? ' active' : ''}`;
    panel.id = `day-panel-${idx}`;
    panel.innerHTML = renderDayPanel(dayPlan);
    panelsEl.appendChild(panel);
  });

  // Initialize drag-and-drop for all slot lists
  initDragAndDrop();
}

function switchDayTab(idx) {
  document.querySelectorAll('.tab-btn').forEach((b, i) => b.classList.toggle('active', i === idx));
  document.querySelectorAll('.tab-panel').forEach((p, i) => p.classList.toggle('active', i === idx));
}

function renderDayPanel(dayPlan) {
  // Group shift_locations by shift
  const shiftMap = {};
  dayPlan.shift_locations.forEach(sl => {
    if (!shiftMap[sl.shift_id]) shiftMap[sl.shift_id] = { shift: sl.shift, locations: [] };
    shiftMap[sl.shift_id].locations.push(sl);
  });

  const shifts = Object.values(shiftMap).sort((a, b) => a.shift.order - b.shift.order);

  if (!shifts.length) {
    // Show empty state with add-shift-location buttons?
    return `<p style="color:#999;margin-top:20px;text-align:center">No shifts configured for this day.</p>`;
  }

  const shiftTabsHtml = shifts.map((s, i) =>
    `<button class="shift-tab-btn${i === 0 ? ' active' : ''}" 
      onclick="switchShiftTab('${dayPlan.date}', ${s.shift.id})"
      data-shift-id="${s.shift.id}" data-day-date="${dayPlan.date}">
      ${lang() === 'ar' ? s.shift.name_ar : s.shift.name_en}
      <small style="opacity:0.7">${s.shift.start_time.slice(0,5)}</small>
    </button>`
  ).join('');

  const shiftPanelsHtml = shifts.map((s, i) =>
    `<div class="shift-panel${i === 0 ? ' active' : ''}" 
          id="shift-panel-${dayPlan.date}-${s.shift.id}"
          style="${i === 0 ? '' : 'display:none'}">
      <div class="locations-grid">
        ${s.locations.map(sl => renderLocationColumn(dayPlan.date, sl)).join('')}
      </div>
    </div>`
  ).join('');

  return `
    <div class="shift-tabs" id="shift-tabs-${dayPlan.date}">${shiftTabsHtml}</div>
    ${shiftPanelsHtml}
  `;
}

function switchShiftTab(dayDate, shiftId) {
  const container = document.getElementById(`shift-tabs-${dayDate}`);
  if (!container) return;
  container.querySelectorAll('.shift-tab-btn').forEach(b => {
    b.classList.toggle('active', parseInt(b.dataset.shiftId) === shiftId);
  });
  // Show/hide panels
  document.querySelectorAll(`[id^="shift-panel-${dayDate}-"]`).forEach(p => {
    p.style.display = p.id === `shift-panel-${dayDate}-${shiftId}` ? 'block' : 'none';
  });
}

function renderLocationColumn(dayDate, sl) {
  const locName = lang() === 'ar' ? sl.location.name_ar : sl.location.name_en;
  const slots = [];
  for (let i = 0; i < sl.slots_count; i++) {
    const assignment = sl.assignments.find(a => a.slot_index === i);
    slots.push(renderSlot(sl.id, i, assignment));
  }

  return `
    <div class="location-column" data-sl-id="${sl.id}" data-day="${dayDate}" data-shift="${sl.shift_id}" data-loc="${sl.location_id}">
      <div class="location-header">
        <span class="location-name">${locName}</span>
        <div class="slot-controls">
          <button class="btn-slot btn-slot-sub" onclick="changeSlots('${dayDate}',${sl.shift_id},${sl.location_id},-1)">−</button>
          <span class="slot-count" id="slot-count-${sl.id}">${sl.slots_count}</span>
          <button class="btn-slot btn-slot-add" onclick="changeSlots('${dayDate}',${sl.shift_id},${sl.location_id},+1)">+</button>
        </div>
      </div>
      <div class="slots-list" id="slots-${sl.id}" data-sl-id="${sl.id}">
        ${slots.join('')}
      </div>
    </div>
  `;
}

function renderSlot(slId, slotIdx, assignment) {
  if (assignment && assignment.teacher_id) {
    return `
      <div class="slot-item filled" data-sl-id="${slId}" data-slot-idx="${slotIdx}" data-teacher-id="${assignment.teacher_id}">
        <div class="teacher-card" data-teacher-id="${assignment.teacher_id}" data-teacher-name="${assignment.teacher_name}">
          <span>${assignment.teacher_name}</span>
          <span class="remove-btn" onclick="removeTeacher(${slId},${slotIdx})">✕</span>
        </div>
      </div>`;
  }
  return `
    <div class="slot-item" data-sl-id="${slId}" data-slot-idx="${slotIdx}" data-teacher-id="">
      <span style="color:#bbb;font-size:0.8rem">${I18N.t('no_teacher')}</span>
    </div>`;
}

// ─── Drag & Drop ──────────────────────────────────────────────────────────────

function initDragAndDrop() {
  // Make teacher sidebar sortable (as source)
  const sidebar = document.getElementById('teacherList');
  if (sidebar) {
    new Sortable(sidebar, {
      group: { name: 'teachers', pull: 'clone', put: false },
      sort: false,
      animation: 150,
    });
  }

  // Make each slot list a drop target
  document.querySelectorAll('.slots-list').forEach(list => {
    new Sortable(list, {
      group: { name: 'teachers', pull: false, put: true },
      animation: 150,
      onAdd: function(evt) {
        const slId = parseInt(list.dataset.slId);
        const teacherId = parseInt(evt.item.dataset.teacherId);
        const teacherName = evt.item.dataset.teacherName;

        // Find the first empty slot
        const emptySlot = list.querySelector('.slot-item:not(.filled)');
        if (!emptySlot) {
          showToast('No empty slots available', 'error');
          evt.item.parentNode.removeChild(evt.item); // remove dragged clone
          return;
        }

        const slotIdx = parseInt(emptySlot.dataset.slotIdx);

        // Update local state
        recordAssignment(slId, slotIdx, teacherId);

        // Re-render the slot
        emptySlot.outerHTML = renderSlot(slId, slotIdx, {
          teacher_id: teacherId,
          teacher_name: teacherName,
          slot_index: slotIdx
        });

        // Remove the clone that SortableJS added
        evt.item.parentNode && evt.item.parentNode.removeChild(evt.item);
      }
    });
  });
}

function recordAssignment(slId, slotIdx, teacherId) {
  if (!pendingAssignments[slId]) pendingAssignments[slId] = {};
  pendingAssignments[slId][slotIdx] = teacherId;
}

function removeTeacher(slId, slotIdx) {
  recordAssignment(slId, slotIdx, null);
  const list = document.getElementById(`slots-${slId}`);
  if (!list) return;
  const slotEl = list.querySelector(`[data-slot-idx="${slotIdx}"]`);
  if (slotEl) {
    slotEl.outerHTML = renderSlot(slId, slotIdx, null);
  }
}

// ─── Slot Count Control ───────────────────────────────────────────────────────

function changeSlots(dayDate, shiftId, locationId, delta) {
  const key = `${dayDate}:${shiftId}:${locationId}`;

  // Find current slots_count from DOM
  const col = document.querySelector(`[data-day="${dayDate}"][data-shift="${shiftId}"][data-loc="${locationId}"]`);
  if (!col) return;
  const slId = parseInt(col.dataset.slId);
  const countEl = document.getElementById(`slot-count-${slId}`);
  let current = parseInt(countEl.textContent);
  const newCount = Math.max(0, current + delta);
  countEl.textContent = newCount;

  pendingSlots[key] = { dayDate, shiftId: parseInt(shiftId), locationId: parseInt(locationId), slotsCount: newCount };

  // Update slot list visually
  const list = document.getElementById(`slots-${slId}`);
  if (!list) return;
  if (delta > 0) {
    // Add empty slot
    const div = document.createElement('div');
    div.innerHTML = renderSlot(slId, current, null); // current is old count = new slotIdx
    list.appendChild(div.firstChild);
    // Re-init sortable for new slot
    initDragAndDrop();
  } else if (delta < 0 && current > 0) {
    // Remove last slot
    const lastSlot = list.querySelector(`[data-slot-idx="${current - 1}"]`);
    if (lastSlot) lastSlot.remove();
  }
}

// ─── Save / Publish / Clone ───────────────────────────────────────────────────

async function saveDraft() {
  if (!currentWeekData) return;
  await flushPendingChanges();
  showToast(I18N.t('success_saved'));
}

async function flushPendingChanges() {
  const weekStart = currentWeekData.week_start_date;

  // Flush slot count changes
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
    }
  }

  // Flush assignment changes
  const assignmentUpdates = [];
  for (const [slId, slots] of Object.entries(pendingAssignments)) {
    for (const [slotIdx, teacherId] of Object.entries(slots)) {
      assignmentUpdates.push({
        shift_location_id: parseInt(slId),
        slot_index: parseInt(slotIdx),
        teacher_id: teacherId
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
    }
  }
}

async function publishWeek() {
  if (!currentWeekData) return;
  if (!confirm(I18N.t('confirm_publish'))) return;

  await flushPendingChanges();

  const weekStart = currentWeekData.week_start_date;
  const res = await apiFetch(`/weeks/${weekStart}/status`, {
    method: 'PUT',
    body: JSON.stringify({ status: 'published' })
  });

  if (res && res.ok) {
    currentWeekData = await res.json();
    updateStatusBadge(currentWeekData.status);
    showToast(I18N.t('success_published'));
  } else {
    showToast(I18N.t('error_generic'), 'error');
  }
}

async function createWeek() {
  const weekStart = document.getElementById('weekStartInput').value;
  if (!weekStart) return;

  const res = await apiFetch(`/weeks/${weekStart}/create`, { method: 'POST' });
  if (res && res.ok) {
    currentWeekData = await res.json();
    renderWeek();
    showToast(I18N.t('success_saved'));
  } else {
    const err = res ? await res.json() : {};
    showToast(err.detail || I18N.t('error_generic'), 'error');
  }
}

async function cloneWeek() {
  const weekStart = document.getElementById('weekStartInput').value;
  if (!weekStart) return;

  const res = await apiFetch(`/weeks/${weekStart}/clone`, { method: 'POST' });
  if (res && res.ok) {
    currentWeekData = await res.json();
    renderWeek();
    showToast(I18N.t('success_cloned'));
  } else {
    const err = res ? await res.json() : {};
    showToast(err.detail || I18N.t('error_generic'), 'error');
  }
}