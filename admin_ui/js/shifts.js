/**
 * shifts.js — Admin shift management.
 *
 * Loads all shifts via GET /shifts/
 * Renders each as an inline-editable card.
 * Saves changes via PUT /shifts/{id}
 * Creates new shifts via POST /shifts/
 * Deletes shifts via DELETE /shifts/{id}
 *
 * Validation: end_time must be after start_time before saving.
 *
 * Script load order required: i18n.js → auth.js → shifts.js
 */

'use strict';

/* ── State ─────────────────────────────────────────────────────────────────── */
let allShifts = [];

/* ── Boot ───────────────────────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', async () => {
  await I18N.init();
  guardPage();
  await loadShifts();
});

/* ── Data loading ───────────────────────────────────────────────────────────── */

async function loadShifts() {
  showLoading(true);

  try {
    const res = await apiFetch('/shifts/');
    if (!res || !res.ok) {
      const msg = await getApiErrorMessage(res, I18N.t('error_generic'));
      showToast(msg, 'error');
      showLoading(false);
      return;
    }
    allShifts = await res.json();
    renderShifts();
  } catch (err) {
    console.error('[shifts] load error:', err);
    showToast(I18N.t('error_generic'), 'error');
  } finally {
    showLoading(false);
  }
}

/* ── Rendering ──────────────────────────────────────────────────────────────── */

function renderShifts() {
  const grid  = document.getElementById('shiftsGrid');
  const empty = document.getElementById('shiftsEmpty');

  if (!grid) return;

  if (!allShifts.length) {
    grid.style.display  = 'none';
    empty.style.display = 'block';
    return;
  }

  empty.style.display = 'none';
  grid.style.display  = 'grid';

  grid.innerHTML = allShifts
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || a.id - b.id)
    .map(renderShiftCard)
    .join('');
}

function renderShiftCard(s) {
  const isBreak    = s.duty_type === 'break';
  const typeLabel  = isBreak
    ? I18N.t('break_duty')
    : I18N.t('morning_endofday');
  const typeCls    = isBreak ? 'shift-type-break' : 'shift-type-morning';

  // Format times to HH:MM (strip seconds if backend returns HH:MM:SS)
  const startFmt = formatTime(s.start_time);
  const endFmt   = formatTime(s.end_time);

  return `
  <div class="shift-card" id="shift-card-${s.id}" data-id="${s.id}">
    <div class="shift-card-header">
      <span class="shift-card-title">${esc(s.name_en)}</span>
      <span class="shift-type-badge ${typeCls}">${typeLabel}</span>
    </div>

    <div class="shift-card-body">
      <!-- Name (English) -->
      <div class="shift-edit-row">
        <span class="shift-edit-label" data-i18n="name_en">${I18N.t('name_en')}</span>
        <input class="shift-edit-input"
               id="shift-name-en-${s.id}"
               type="text"
               value="${esc(s.name_en)}"
               placeholder="Morning Duty">
      </div>

      <!-- Name (Arabic) -->
      <div class="shift-edit-row">
        <span class="shift-edit-label" data-i18n="name_ar">${I18N.t('name_ar')}</span>
        <input class="shift-edit-input"
               id="shift-name-ar-${s.id}"
               type="text"
               value="${esc(s.name_ar)}"
               placeholder="المناوبة الصباحية"
               dir="rtl">
      </div>

      <!-- Start time -->
      <div class="shift-time-row">
        <label for="shift-start-${s.id}">${I18N.t('start_time')}</label>
        <input class="shift-time-input"
               id="shift-start-${s.id}"
               type="time"
               value="${startFmt}">
      </div>

      <!-- End time -->
      <div class="shift-time-row">
        <label for="shift-end-${s.id}">${I18N.t('end_time')}</label>
        <input class="shift-time-input"
               id="shift-end-${s.id}"
               type="time"
               value="${endFmt}">
      </div>

      <!-- Time validation error -->
      <p class="shift-error" id="shift-err-${s.id}" style="display:none"></p>

      <!-- Duty type -->
      <div class="shift-edit-row">
        <span class="shift-edit-label">${I18N.t('duty_type')}</span>
        <select class="shift-edit-input" id="shift-dtype-${s.id}">
          <option value="morning_endofday" ${!isBreak ? 'selected' : ''}>${I18N.t('morning_endofday')}</option>
          <option value="break"            ${ isBreak ? 'selected' : ''}>${I18N.t('break_duty')}</option>
        </select>
      </div>

      <!-- Order -->
      <div class="shift-edit-row">
        <span class="shift-edit-label">${I18N.t('order')}</span>
        <input class="shift-edit-input"
               id="shift-order-${s.id}"
               type="number"
               min="0"
               value="${s.order ?? 0}">
      </div>
    </div>

    <div class="shift-card-actions">
      <button class="btn btn-primary btn-sm"
              onclick="saveShift(${s.id})">${I18N.t('save')}</button>
      <button class="btn btn-danger btn-sm"
              onclick="deleteShift(${s.id})">${I18N.t('delete')}</button>
    </div>
  </div>`;
}

/* ── Save (PUT) ─────────────────────────────────────────────────────────────── */

async function saveShift(id) {
  const nameEn  = val(`shift-name-en-${id}`).trim();
  const nameAr  = val(`shift-name-ar-${id}`).trim();
  const startRaw = val(`shift-start-${id}`);
  const endRaw   = val(`shift-end-${id}`);
  const dtype   = val(`shift-dtype-${id}`);
  const order   = parseInt(val(`shift-order-${id}`), 10) || 0;
  const errEl   = document.getElementById(`shift-err-${id}`);

  // ── Validation ──────────────────────────────────────────────────────────────
  if (errEl) errEl.style.display = 'none';

  if (!nameEn) {
    showCardError(id, I18N.t('name_en_required'));
    return;
  }
  if (!startRaw || !endRaw) {
    showCardError(id, I18N.t('start_end_required'));
    return;
  }
  if (!isValidTimeRange(startRaw, endRaw)) {
    showCardError(id, I18N.t('invalid_time_range'));
    return;
  }

  const payload = {
    name_en:    nameEn,
    name_ar:    nameAr,
    start_time: startRaw,   // "HH:MM" — backend accepts this for time fields
    end_time:   endRaw,
    duty_type:  dtype,
    order,
  };

  const btn = document.querySelector(`#shift-card-${id} .btn-primary`);
  if (btn) { btn.disabled = true; btn.textContent = I18N.t('loading'); }

  try {
    const res = await apiFetch(`/shifts/${id}`, {
      method: 'PUT',
      body:   JSON.stringify(payload),
    });

    if (res && res.ok) {
      const updated = await res.json();
      // Update local state
      const idx = allShifts.findIndex(s => s.id === id);
      if (idx !== -1) allShifts[idx] = updated;

      // Re-render just this card's header to reflect new name/type
      const card = document.getElementById(`shift-card-${id}`);
      if (card) {
        const header = card.querySelector('.shift-card-title');
        if (header) header.textContent = updated.name_en;
        const badge = card.querySelector('.shift-type-badge');
        if (badge) {
          const isBreak = updated.duty_type === 'break';
          badge.textContent  = isBreak ? I18N.t('break_duty') : I18N.t('morning_endofday');
          badge.className    = 'shift-type-badge ' + (isBreak ? 'shift-type-break' : 'shift-type-morning');
        }
      }
      showToast(I18N.t('shift_saved'), 'success');
    } else {
      const msg = await getApiErrorMessage(res, I18N.t('error_generic'));
      showCardError(id, msg);
    }
  } catch (err) {
    console.error('[shifts] save error:', err);
    showCardError(id, I18N.t('error_generic'));
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = I18N.t('save'); }
  }
}

/* ── Add (POST) ─────────────────────────────────────────────────────────────── */

function openAddModal() {
  clearAddModal();
  document.getElementById('addModal')?.classList.remove('hidden');
}

function closeAddModal() {
  document.getElementById('addModal')?.classList.add('hidden');
}

function clearAddModal() {
  ['add-name-en', 'add-name-ar', 'add-start-time', 'add-end-time'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = '';
  });
  const orderEl = document.getElementById('add-order');
  if (orderEl) orderEl.value = '0';
  const dtype = document.getElementById('add-duty-type');
  if (dtype) dtype.value = 'morning_endofday';
  const err = document.getElementById('addError');
  if (err) { err.style.display = 'none'; err.textContent = ''; }
}

async function addShift() {
  const nameEn   = val('add-name-en').trim();
  const nameAr   = val('add-name-ar').trim();
  const startRaw = val('add-start-time');
  const endRaw   = val('add-end-time');
  const dtype    = val('add-duty-type');
  const order    = parseInt(val('add-order'), 10) || 0;
  const errEl    = document.getElementById('addError');

  if (errEl) { errEl.style.display = 'none'; errEl.textContent = ''; }

  if (!nameEn) {
    showModalError(I18N.t('name_en_required'));
    return;
  }
  if (!startRaw || !endRaw) {
    showModalError(I18N.t('start_end_required'));
    return;
  }
  if (!isValidTimeRange(startRaw, endRaw)) {
    showModalError(I18N.t('invalid_time_range'));
    return;
  }

  const payload = {
    name_en:    nameEn,
    name_ar:    nameAr || nameEn,
    start_time: startRaw,
    end_time:   endRaw,
    duty_type:  dtype,
    order,
  };

  try {
    const res = await apiFetch('/shifts/', {
      method: 'POST',
      body:   JSON.stringify(payload),
    });

    if (res && res.ok) {
      const created = await res.json();
      allShifts.push(created);
      renderShifts();
      closeAddModal();
      showToast(I18N.t('shift_saved'), 'success');
    } else {
      const msg = await getApiErrorMessage(res, I18N.t('error_generic'));
      showModalError(msg);
    }
  } catch (err) {
    console.error('[shifts] add error:', err);
    showModalError(I18N.t('error_generic'));
  }
}

/* ── Delete ─────────────────────────────────────────────────────────────────── */

async function deleteShift(id) {
  if (!confirm(I18N.t('confirm_delete_shift'))) return;

  try {
    const res = await apiFetch(`/shifts/${id}`, { method: 'DELETE' });

    if (res && (res.ok || res.status === 204)) {
      allShifts = allShifts.filter(s => s.id !== id);
      renderShifts();
      showToast(I18N.t('shift_deleted'), 'success');
    } else {
      const msg = await getApiErrorMessage(res, I18N.t('error_generic'));
      showToast(msg, 'error');
    }
  } catch (err) {
    console.error('[shifts] delete error:', err);
    showToast(I18N.t('error_generic'), 'error');
  }
}

/* ── Helpers ─────────────────────────────────────────────────────────────────── */

/** Show/hide the full-page loading indicator. */
function showLoading(visible) {
  const loading = document.getElementById('shiftsLoading');
  const grid    = document.getElementById('shiftsGrid');
  const empty   = document.getElementById('shiftsEmpty');
  if (loading) loading.style.display = visible ? 'block' : 'none';
  if (!visible) return;
  if (grid)  grid.style.display  = 'none';
  if (empty) empty.style.display = 'none';
}

/** Display a validation error message inside a card. */
function showCardError(id, msg) {
  const el = document.getElementById(`shift-err-${id}`);
  if (!el) return;
  el.textContent  = msg;
  el.style.display = 'block';
}

/** Display a validation error inside the add modal. */
function showModalError(msg) {
  const el = document.getElementById('addError');
  if (!el) return;
  el.textContent  = msg;
  el.style.display = 'block';
}

/**
 * Validate that end is strictly after start.
 * Both values are "HH:MM" strings from <input type="time">.
 */
function isValidTimeRange(start, end) {
  if (!start || !end) return false;
  // Compare lexicographically — works for HH:MM format
  return end > start;
}

/**
 * Format a time string from the backend (may be "HH:MM:SS" or "HH:MM")
 * to "HH:MM" for <input type="time">.
 */
function formatTime(t) {
  if (!t) return '';
  return String(t).substring(0, 5);
}

/** Get the value of an input by id. */
function val(id) {
  return (document.getElementById(id)?.value ?? '').trim();
}

/** HTML-escape a string to prevent XSS in card rendering. */
function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Extract a human-readable error from an API response.
 * Falls back to the provided default message.
 */
async function getApiErrorMessage(res, fallback) {
  if (!res) return fallback;
  try {
    const data = await res.json();
    return data?.detail || data?.message || fallback;
  } catch (_) {
    return fallback;
  }
}

/** Show a toast notification. Reuses showToast from auth.js if available. */
function showToast(message, type = 'success') {
  // auth.js exposes showToast globally — use it if present
  if (typeof window.showToast === 'function') {
    window.showToast(message, type);
    return;
  }

  // Fallback: simple toast built inline
  const container = document.getElementById('toastContainer');
  if (!container) {
    alert(message);
    return;
  }

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  setTimeout(() => toast.classList.add('show'), 10);
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}
