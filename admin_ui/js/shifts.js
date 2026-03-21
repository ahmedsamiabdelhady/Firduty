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

document.addEventListener('languageChanged', () => {
  renderShifts();
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
  const grid = document.getElementById('shiftsGrid');
  const empty = document.getElementById('shiftsEmpty');
  if (!grid) return;

  if (!allShifts.length) {
    grid.style.display = 'none';
    if (empty) empty.style.display = 'block';
    return;
  }

  if (empty) empty.style.display = 'none';
  grid.style.display = 'grid';
  grid.innerHTML = allShifts
    .slice()
    .sort((a, b) => (a.order ?? 0) - (b.order ?? 0) || a.id - b.id)
    .map(renderShiftCard)
    .join('');
}

function getShiftDisplayName(shift) {
  const lang = I18N.getLang();
  if (lang === 'ar') {
    return shift.name_ar || shift.name_en || '';
  }
  return shift.name_en || shift.name_ar || '';
}

function renderShiftCard(s) {
  const isBreak = s.duty_type === 'break';
  const typeLabel = isBreak ? I18N.t('break_duty') : I18N.t('morning_endofday');
  const typeCls = isBreak ? 'shift-type-break' : 'shift-type-morning';

  // Format times to HH:MM (strip seconds if backend returns HH:MM:SS)
  const startFmt = formatTime(s.start_time);
  const endFmt = formatTime(s.end_time);
  const displayName = getShiftDisplayName(s);

  return `
    <div class="shift-card" id="shift-card-${s.id}">
      <div class="shift-card-header">
        <h3 class="shift-card-title">${esc(displayName)}</h3>
        <span class="shift-type-badge ${typeCls}">${esc(typeLabel)}</span>
      </div>

      <div class="shift-card-body">
        <div class="form-group">
          <label for="shift-name-en-${s.id}">${I18N.t('name_en')}</label>
          <input
            id="shift-name-en-${s.id}"
            type="text"
            value="${escAttr(s.name_en || '')}"
          />
        </div>

        <div class="form-group">
          <label for="shift-name-ar-${s.id}">${I18N.t('name_ar')}</label>
          <input
            id="shift-name-ar-${s.id}"
            type="text"
            value="${escAttr(s.name_ar || '')}"
          />
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="shift-start-${s.id}">${I18N.t('start_time')}</label>
            <input
              id="shift-start-${s.id}"
              type="time"
              value="${escAttr(startFmt)}"
            />
          </div>

          <div class="form-group">
            <label for="shift-end-${s.id}">${I18N.t('end_time')}</label>
            <input
              id="shift-end-${s.id}"
              type="time"
              value="${escAttr(endFmt)}"
            />
          </div>
        </div>

        <div class="form-row">
          <div class="form-group">
            <label for="shift-dtype-${s.id}">${I18N.t('duty_type')}</label>
            <select id="shift-dtype-${s.id}">
              <option value="morning_endofday" ${s.duty_type === 'morning_endofday' ? 'selected' : ''}>
                ${I18N.t('morning_endofday')}
              </option>
              <option value="break" ${s.duty_type === 'break' ? 'selected' : ''}>
                ${I18N.t('break_duty')}
              </option>
            </select>
          </div>

          <div class="form-group">
            <label for="shift-order-${s.id}">${I18N.t('order')}</label>
            <input
              id="shift-order-${s.id}"
              type="number"
              value="${escAttr(String(s.order ?? 0))}"
            />
          </div>
        </div>

        <div class="card-error" id="shift-err-${s.id}" style="display:none;"></div>

        <div class="card-actions">
          <button class="btn btn-primary" type="button" onclick="saveShift(${s.id})">
            ${I18N.t('save')}
          </button>
          <button class="btn btn-danger" type="button" onclick="deleteShift(${s.id})">
            ${I18N.t('delete')}
          </button>
        </div>
      </div>
    </div>
  `;
}

/* ── Save (PUT) ─────────────────────────────────────────────────────────────── */
async function saveShift(id) {
  const nameEn = val(`shift-name-en-${id}`).trim();
  const nameAr = val(`shift-name-ar-${id}`).trim();
  const startRaw = val(`shift-start-${id}`);
  const endRaw = val(`shift-end-${id}`);
  const dtype = val(`shift-dtype-${id}`);
  const order = parseInt(val(`shift-order-${id}`), 10) || 0;

  const errEl = document.getElementById(`shift-err-${id}`);

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
    name_en: nameEn,
    name_ar: nameAr,
    start_time: startRaw,
    end_time: endRaw,
    duty_type: dtype,
    order,
  };

  const btn = document.querySelector(`#shift-card-${id} .btn-primary`);
  if (btn) {
    btn.disabled = true;
    btn.textContent = I18N.t('loading');
  }

  try {
    const res = await apiFetch(`/shifts/${id}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });

    if (res && res.ok) {
      const updated = await res.json();

      const idx = allShifts.findIndex(s => s.id === id);
      if (idx !== -1) {
        allShifts[idx] = updated;
      }

      const card = document.getElementById(`shift-card-${id}`);
      if (card) {
        const header = card.querySelector('.shift-card-title');
        if (header) {
          header.textContent = getShiftDisplayName(updated);
        }

        const badge = card.querySelector('.shift-type-badge');
        if (badge) {
          const isBreak = updated.duty_type === 'break';
          badge.textContent = isBreak ? I18N.t('break_duty') : I18N.t('morning_endofday');
          badge.className = 'shift-type-badge ' + (isBreak ? 'shift-type-break' : 'shift-type-morning');
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
    if (btn) {
      btn.disabled = false;
      btn.textContent = I18N.t('save');
    }
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
  if (err) {
    err.style.display = 'none';
    err.textContent = '';
  }
}

async function addShift() {
  const nameEn = val('add-name-en').trim();
  const nameAr = val('add-name-ar').trim();
  const startRaw = val('add-start-time');
  const endRaw = val('add-end-time');
  const dtype = val('add-duty-type');
  const order = parseInt(val('add-order'), 10) || 0;

  const errEl = document.getElementById('addError');
  if (errEl) {
    errEl.style.display = 'none';
    errEl.textContent = '';
  }

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
    name_en: nameEn,
    name_ar: nameAr || nameEn,
    start_time: startRaw,
    end_time: endRaw,
    duty_type: dtype,
    order,
  };

  try {
    const res = await apiFetch('/shifts/', {
      method: 'POST',
      body: JSON.stringify(payload),
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
function showLoading(visible) {
  const loading = document.getElementById('shiftsLoading');
  const grid = document.getElementById('shiftsGrid');
  const empty = document.getElementById('shiftsEmpty');

  if (loading) loading.style.display = visible ? 'block' : 'none';
  if (!visible) return;

  if (grid) grid.style.display = 'none';
  if (empty) empty.style.display = 'none';
}

function showCardError(id, msg) {
  const el = document.getElementById(`shift-err-${id}`);
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'block';
}

function showModalError(msg) {
  const el = document.getElementById('addError');
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'block';
}

function isValidTimeRange(start, end) {
  if (!start || !end) return false;
  return end > start;
}

function formatTime(t) {
  if (!t) return '';
  return String(t).substring(0, 5);
}

function val(id) {
  return (document.getElementById(id)?.value ?? '').trim();
}

function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function escAttr(str) {
  return esc(str);
}

async function getApiErrorMessage(res, fallback) {
  if (!res) return fallback;
  try {
    const data = await res.json();
    return data?.detail || data?.message || fallback;
  } catch (_) {
    return fallback;
  }
}

function showToast(message, type = 'success') {
  if (typeof window.showToast === 'function') {
    window.showToast(message, type);
    return;
  }

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