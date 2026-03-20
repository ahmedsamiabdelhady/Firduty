/**
 * teachers.js — Teacher management for Firduty Admin UI  v2.5
 *
 * Features:
 *  - List pending / all teachers in tabbed view
 *  - Approve individual teachers or all pending at once
 *  - Add new teacher via modal (POST /teachers/)
 *  - Permanently delete teacher via modal (DELETE /teachers/{id})
 *  - Live search/filter inside each tab
 *
 * Auth: handled by auth.js (loaded before this script).
 * Uses apiFetch() for all API calls — attaches token + handles 401 redirect.
 */

/* ─── State ───────────────────────────────────────────────────────────────── */
let currentTab = 'pending';
let _allPending = [];   // cache for client-side search
let _allTeachers = [];  // cache for client-side search

/* ─── DOM helpers ─────────────────────────────────────────────────────────── */
function byId(id)           { return document.getElementById(id); }
function showEl(el, d = '') { if (el) el.style.display = d; }
function hideEl(el)         { if (el) el.style.display = 'none'; }

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ─── Toast (lightweight, doesn't rely on toastContainer existing) ────────── */
function showToast(msg, type = 'success') {
  const c = byId('toastContainer');
  if (!c) { console.log(`[toast:${type}] ${msg}`); return; }
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

/* ─── Alert bar (persistent, inside main content) ────────────────────────── */
function showAlert(msg, type) {
  const el = byId('alertMsg');
  if (!el) return;
  el.className = `alert alert-${type}`;
  el.textContent = msg;
  showEl(el);
  setTimeout(() => hideEl(el), 4500);
}
function clearAlert() { hideEl(byId('alertMsg')); }

/* ─── Tab management ──────────────────────────────────────────────────────── */
function showTab(tab) {
  currentTab = tab;
  const pending = byId('pendingSection');
  const all     = byId('allSection');
  const tabP    = byId('tabPending');
  const tabA    = byId('tabAll');

  if (pending) pending.style.display = tab === 'pending' ? '' : 'none';
  if (all)     all.style.display     = tab === 'all'     ? '' : 'none';
  if (tabP) tabP.classList.toggle('active', tab === 'pending');
  if (tabA) tabA.classList.toggle('active', tab === 'all');
}

/* ─── Data loading ────────────────────────────────────────────────────────── */
async function loadAll() {
  clearAlert();
  await Promise.all([loadPending(), loadAllTeachers()]);
}

async function loadPending() {
  const loading = byId('pendingLoading');
  const wrap    = byId('pendingTableWrap');
  const count   = byId('pendingCount');
  const appBtn  = byId('approveAllBtn');

  try {
    showEl(loading);
    if (wrap) wrap.innerHTML = '';

    const res = await apiFetch('/teachers/pending');
    if (!res || !res.ok) { showAlert(I18N.t('error_generic'), 'danger'); return; }

    _allPending = await res.json();

    // Update pending count badge
    if (count) {
      if (_allPending.length > 0) {
        count.textContent = _allPending.length;
        showEl(count, 'inline');
      } else {
        hideEl(count);
      }
    }

    if (appBtn) appBtn.disabled = _allPending.length === 0;

    renderTeacherList(wrap, _allPending, true);
  } catch (err) {
    console.error('loadPending failed:', err);
    showAlert(I18N.t('error_generic'), 'danger');
  } finally {
    hideEl(loading);
  }
}

async function loadAllTeachers() {
  const loading = byId('allLoading');
  const wrap    = byId('allTableWrap');

  try {
    showEl(loading);
    if (wrap) wrap.innerHTML = '';

    const res = await apiFetch('/teachers/all');
    if (!res || !res.ok) { showAlert(I18N.t('error_generic'), 'danger'); return; }

    _allTeachers = await res.json();
    renderTeacherList(wrap, _allTeachers, false);
  } catch (err) {
    console.error('loadAllTeachers failed:', err);
    showAlert(I18N.t('error_generic'), 'danger');
  } finally {
    hideEl(loading);
  }
}

/* ─── Table renderer ──────────────────────────────────────────────────────── */
function renderTeacherList(container, teachers, showApprove) {
  if (!container) return;

  if (!teachers.length) {
    container.innerHTML = emptyState(showApprove ? 'no_pending_teachers' : 'no_teachers_yet');
    return;
  }

  const isAr = I18N.getLang() === 'ar';

  const rows = teachers.map((t, i) => {
    const statusBadge = t.status === 'pending'
      ? `<span class="badge badge-pending">${I18N.t('status_pending')}</span>`
      : `<span class="badge badge-approved">${I18N.t('status_approved')}</span>`;

    const langLabel = t.preferred_language === 'ar' ? I18N.t('arabic') : I18N.t('english');
    const createdAt = t.created_at
      ? new Date(t.created_at).toLocaleDateString(isAr ? 'ar-OM' : 'en-GB') : '—';

    const approveBtn = showApprove && t.status === 'pending'
      ? `<button class="btn btn-success btn-sm" id="btn-approve-${t.id}" onclick="approveTeacher(${t.id})">${I18N.t('approve')}</button>`
      : '';

    const actionBtns = `
      <div style="display:flex;gap:5px;flex-wrap:wrap;align-items:center">
        ${approveBtn}
        <button class="btn btn-secondary btn-sm" onclick="startEditRow(${t.id})">✏️</button>
        <button class="btn btn-danger btn-sm"
                onclick="openRemoveModal(${t.id},'${escHtml(t.name).replace(/'/g,'&#39;')}')"
                title="${I18N.t('delete_teacher') || I18N.t('delete')}">🗑</button>
      </div>`;

    return `
      <tr id="teacher-row-${t.id}" data-teacher-id="${t.id}">
        <td>${i + 1}</td>
        <td id="cell-name-${t.id}"><strong>${escHtml(t.name)}</strong></td>
        <td id="cell-email-${t.id}" style="font-size:0.83rem;color:var(--text-muted)">${escHtml(t.email || '—')}</td>
        <td id="cell-status-${t.id}">${statusBadge}</td>
        <td id="cell-lang-${t.id}">${langLabel}</td>
        <td style="font-size:0.82rem;color:var(--text-muted)">${createdAt}</td>
        <td id="cell-actions-${t.id}">${actionBtns}</td>
      </tr>`;
  }).join('');

  container.innerHTML = `
    <table class="teacher-table">
      <thead>
        <tr>
          <th>#</th>
          <th>${I18N.t('name')}</th>
          <th>${I18N.t('email')}</th>
          <th>${I18N.t('status')}</th>
          <th>${I18N.t('language')}</th>
          <th>${I18N.t('date')}</th>
          <th>${I18N.t('actions')}</th>
        </tr>
      </thead>
      <tbody>${rows}</tbody>
    </table>`;
}

function emptyState(i18nKey) {
  return `
    <div class="empty-state">
      <div class="empty-icon">👥</div>
      <p>${I18N.t(i18nKey)}</p>
    </div>`;
}

/* ─── Inline row edit ─────────────────────────────────────────────────────── */

// Cache of teacher objects by id for quick lookup during edit
function _getTeacherById(id) {
  return [..._allPending, ..._allTeachers].find(t => t.id === id) || null;
}

function startEditRow(id) {
  const teacher = _getTeacherById(id);
  if (!teacher) return;

  const row = document.getElementById(`teacher-row-${id}`);
  if (!row) return;
  row.classList.add('teacher-row-editing');

  // Name cell
  document.getElementById(`cell-name-${id}`).innerHTML = `
    <input class="inline-edit-input" id="edit-name-${id}"
           value="${escHtml(teacher.name)}" placeholder="${I18N.t('name')}">`;

  // Email cell
  document.getElementById(`cell-email-${id}`).innerHTML = `
    <input class="inline-edit-input" id="edit-email-${id}" type="email"
           value="${escHtml(teacher.email || '')}" placeholder="${I18N.t('email')}">`;

  // Status cell
  document.getElementById(`cell-status-${id}`).innerHTML = `
    <select class="inline-edit-select" id="edit-status-${id}">
      <option value="approved" ${teacher.status === 'approved' ? 'selected' : ''}>${I18N.t('status_approved')}</option>
      <option value="pending"  ${teacher.status === 'pending'  ? 'selected' : ''}>${I18N.t('status_pending')}</option>
    </select>`;

  // Language cell
  document.getElementById(`cell-lang-${id}`).innerHTML = `
    <select class="inline-edit-select" id="edit-lang-${id}">
      <option value="ar" ${(teacher.preferred_language ?? 'ar') === 'ar' ? 'selected' : ''}>${I18N.t('arabic')}</option>
      <option value="en" ${(teacher.preferred_language ?? 'ar') === 'en' ? 'selected' : ''}>${I18N.t('english')}</option>
    </select>`;

  // Actions cell
  document.getElementById(`cell-actions-${id}`).innerHTML = `
    <div style="display:flex;gap:5px">
      <button class="btn btn-edit-save btn-sm" onclick="saveEditRow(${id})">💾 ${I18N.t('save')}</button>
      <button class="btn btn-edit-cancel btn-sm" onclick="cancelEditRow(${id})">✕</button>
    </div>`;

  // Focus name
  document.getElementById(`edit-name-${id}`)?.focus();

  // Allow Enter to save, Escape to cancel
  row.addEventListener('keydown', function _kd(e) {
    if (e.key === 'Enter')  { saveEditRow(id);   row.removeEventListener('keydown', _kd); }
    if (e.key === 'Escape') { cancelEditRow(id); row.removeEventListener('keydown', _kd); }
  });
}

async function saveEditRow(id) {
  const name   = document.getElementById(`edit-name-${id}`)?.value.trim();
  const email  = document.getElementById(`edit-email-${id}`)?.value.trim();
  const status = document.getElementById(`edit-status-${id}`)?.value;
  const lang   = document.getElementById(`edit-lang-${id}`)?.value;

  if (!name) {
    document.getElementById(`edit-name-${id}`)?.focus();
    showAlert(`${I18N.t('name')} ${I18N.t('is_required')}`, 'danger');
    return;
  }

  const saveBtn = document.querySelector(`#teacher-row-${id} .btn-edit-save`);
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = '…'; }

  try {
    const res = await apiFetch(`/teachers/${id}`, {
      method: 'PUT',
      body: JSON.stringify({
        name,
        email: email || null,
        status,
        preferred_language: lang,
      }),
    });

    if (!res || !res.ok) {
      let detail = I18N.t('error_generic');
      try { const d = await res.json(); detail = d.detail || detail; } catch (_) {}
      showAlert(detail, 'danger');
      if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = `💾 ${I18N.t('save')}`; }
      return;
    }

    showToast(I18N.t('teacher_updated_ok'), 'success');
    await loadAll();
  } catch (err) {
    console.error('saveEditRow failed:', err);
    showAlert(I18N.t('error_generic'), 'danger');
    if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = `💾 ${I18N.t('save')}`; }
  }
}

function cancelEditRow(id) {
  // Just re-render both lists to restore the row
  renderTeacherList(document.getElementById('pendingTableWrap'), _allPending, true);
  renderTeacherList(document.getElementById('allTableWrap'),    _allTeachers, false);
}

/* ─── Approve actions ─────────────────────────────────────────────────────── */
async function approveTeacher(id) {
  const btn = byId(`btn-approve-${id}`);
  if (btn) { btn.disabled = true; btn.textContent = '…'; }

  try {
    const res = await apiFetch(`/teachers/${id}/approve`, { method: 'POST' });
    if (!res || !res.ok) {
      showAlert(I18N.t('error_generic'), 'danger');
      if (btn) { btn.disabled = false; btn.textContent = I18N.t('approve'); }
      return;
    }
    showToast(I18N.t('teacher_created_ok'), 'success');
    await loadAll();
  } catch (err) {
    console.error('approveTeacher failed:', err);
    showAlert(I18N.t('error_generic'), 'danger');
    if (btn) { btn.disabled = false; btn.textContent = I18N.t('approve'); }
  }
}

async function approveAll() {
  const btn = byId('approveAllBtn');
  if (btn) btn.disabled = true;

  try {
    const res = await apiFetch('/teachers/approve-all', { method: 'POST' });
    if (!res || !res.ok) {
      showAlert(I18N.t('error_generic'), 'danger');
      if (btn) btn.disabled = false;
      return;
    }
    const data = await res.json();
    const count = data.approved ?? data.approved_count ?? 0;
    showToast(
      count > 0
        ? `${I18N.t('all_approved_ok')} (${count})`
        : I18N.t('no_pending_teachers'),
      'success'
    );
    await loadAll();
  } catch (err) {
    console.error('approveAll failed:', err);
    showAlert(I18N.t('error_generic'), 'danger');
    if (btn) btn.disabled = false;
  }
}

/* ─── Add Teacher Modal ───────────────────────────────────────────────────── */
function openAddModal() {
  // Reset form fields
  const name  = byId('addName');
  const email = byId('addEmail');
  const lang  = byId('addLang');
  if (name)  name.value  = '';
  if (email) email.value = '';
  if (lang)  lang.value  = 'ar';

  const modal = byId('addTeacherModal');
  if (modal) modal.classList.remove('hidden');
  // Focus name field after transition
  setTimeout(() => name?.focus(), 80);
}

function closeAddModal() {
  const modal = byId('addTeacherModal');
  if (modal) modal.classList.add('hidden');
}

async function saveNewTeacher() {
  const nameEl  = byId('addName');
  const emailEl = byId('addEmail');
  const langEl  = byId('addLang');
  const saveBtn = byId('addSaveBtn');

  const name  = nameEl?.value.trim();
  const email = emailEl?.value.trim();
  const lang  = langEl?.value || 'ar';

  if (!name) {
    nameEl?.focus();
    showAlert(`${I18N.t('name')} ${I18N.t('is_required')}`, 'danger');
    return;
  }

  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = '…'; }

  try {
    const res = await apiFetch('/teachers/', {
      method: 'POST',
      body: JSON.stringify({
        name,
        email: email || null,
        preferred_language: lang,
        status: 'approved',
      }),
    });

    if (!res || !res.ok) {
      let detail = I18N.t('error_generic');
      try { const d = await res.json(); detail = d.detail || detail; } catch (_) {}
      showAlert(detail, 'danger');
      return;
    }

    closeAddModal();
    showToast(I18N.t('teacher_approved_ok'), 'success');
    await loadAll();
    // Switch to All Teachers tab to show the newly added teacher
    showTab('all');
  } catch (err) {
    console.error('saveNewTeacher failed:', err);
    showAlert(I18N.t('error_generic'), 'danger');
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = I18N.t('save') || 'Save Teacher';
    }
  }
}

/* ─── Remove (Delete) Teacher Modal ───────────────────────────────────── */
function openRemoveModal(id, name) {
  const idEl   = byId('removeTeacherId');
  const nameEl = byId('removeTeacherName');
  if (idEl)   idEl.value       = id;
  if (nameEl) nameEl.textContent = name;

  const modal = byId('removeTeacherModal');
  if (modal) modal.classList.remove('hidden');
}

function closeRemoveModal() {
  const modal = byId('removeTeacherModal');
  if (modal) modal.classList.add('hidden');
}

async function confirmRemoveTeacher() {
  const id  = byId('removeTeacherId')?.value;
  const btn = byId('removeConfirmBtn');
  if (!id) return;

  if (btn) { btn.disabled = true; btn.textContent = '…'; }

  try {
    const res = await apiFetch(`/teachers/${id}`, { method: 'DELETE' });
    if (!res || !res.ok) {
      let detail = I18N.t('error_generic');
      try { const d = await res.json(); detail = d.detail || detail; } catch (_) {}
      showAlert(detail, 'danger');
      return;
    }

    closeRemoveModal();
    showToast(I18N.t('teacher_deleted_ok'), 'success');
    await loadAll();
  } catch (err) {
    console.error('confirmRemoveTeacher failed:', err);
    showAlert(I18N.t('error_generic'), 'danger');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = I18N.t('delete_teacher_confirm') || I18N.t('delete');
    }
  }
}

/* ─── Modal overlay click-outside-to-close ────────────────────────────────── */
function onModalOverlayClick(event, modalId) {
  if (event.target.id === modalId) {
    if (modalId === 'addTeacherModal')    closeAddModal();
    if (modalId === 'removeTeacherModal') closeRemoveModal();
  }
}

/* ─── Keyboard: Escape closes any open modal ──────────────────────────────── */
document.addEventListener('keydown', e => {
  if (e.key !== 'Escape') return;
  if (!byId('addTeacherModal')?.classList.contains('hidden'))    closeAddModal();
  if (!byId('removeTeacherModal')?.classList.contains('hidden')) closeRemoveModal();
});


document.addEventListener('languageChanged', () => {
  try {
    I18N.applyTranslations(document);
    renderTeacherList(document.getElementById('pendingTableWrap'), _allPending, true);
    renderTeacherList(document.getElementById('allTableWrap'), _allTeachers, false);
  } catch (err) {
    console.error('teachers languageChanged rerender failed:', err);
  }
});

/* ─── Page init ───────────────────────────────────────────────────────────── */
async function initTeachersPage() {
  // Auth guard (belt-and-suspenders — inline script already redirects)
  const token = localStorage.getItem('firduty_token');
  if (!token) { window.location.replace('login.html'); return; }

  try {
    await I18N.init();
    showTab('pending');
    await loadAll();
  } catch (err) {
    console.error('initTeachersPage failed:', err);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initTeachersPage);
} else {
  initTeachersPage();
}
