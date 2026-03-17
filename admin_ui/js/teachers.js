/**
 * teachers.js — Teacher management for Firduty Admin UI
 *
 * Endpoints used:
 *   GET    /teachers/pending
 *   GET    /teachers/all
 *   POST   /teachers/{id}/approve
 *   POST   /teachers/approve-all
 *   POST   /teachers/
 *   PUT    /teachers/{id}
 *   DELETE /teachers/{id}
 */

let currentTab = 'pending';
let pendingTeachersCache = [];
let allTeachersCache = [];
let searchTerm = '';
let editingTeacherId = null;
let deleteQueue = [];
const selectedTeacherIds = new Set();

function byId(id) {
  return document.getElementById(id);
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function showAlert(msg, type = 'success') {
  const el = byId('alertMsg');
  if (!el) return;
  el.className = `alert alert-${type}`;
  el.textContent = msg;
  el.style.display = '';
  clearTimeout(showAlert._timer);
  showAlert._timer = setTimeout(() => {
    el.style.display = 'none';
  }, 3600);
}

function clearAlert() {
  const el = byId('alertMsg');
  if (el) el.style.display = 'none';
}

function normalize(str) {
  return String(str || '').trim().toLowerCase();
}

function formatDate(value) {
  if (!value) return '—';
  try {
    const isAr = document.documentElement.lang === 'ar';
    return new Date(value).toLocaleDateString(isAr ? 'ar-OM' : 'en-GB');
  } catch {
    return '—';
  }
}

function statusBadge(status) {
  return status === 'pending'
    ? `<span class="badge badge-pending">Pending</span>`
    : `<span class="badge badge-approved">Approved</span>`;
}

function languageChip(lang) {
  return `<span class="lang-chip">${lang === 'ar' ? 'Arabic' : 'English'}</span>`;
}

function matchesSearch(teacher) {
  if (!searchTerm) return true;
  const blob = [teacher.name, teacher.email, teacher.status, teacher.preferred_language]
    .map(normalize)
    .join(' ');
  return blob.includes(searchTerm);
}

function getFilteredPending() {
  return pendingTeachersCache.filter(matchesSearch);
}

function getFilteredAll() {
  return allTeachersCache.filter(matchesSearch);
}

function getCurrentVisibleTeachers() {
  return currentTab === 'pending' ? getFilteredPending() : getFilteredAll();
}

function updateStats() {
  const pending = pendingTeachersCache.length;
  const approved = allTeachersCache.filter(t => t.status === 'approved').length;
  const active = allTeachersCache.length;

  if (byId('summaryPendingValue')) byId('summaryPendingValue').textContent = pending;
  if (byId('summaryApprovedValue')) byId('summaryApprovedValue').textContent = approved;
  if (byId('summaryTotalValue')) byId('summaryTotalValue').textContent = active;
  if (byId('pendingCount')) byId('pendingCount').textContent = pending;
  if (byId('allCount')) byId('allCount').textContent = active;
  if (byId('approveAllBtn')) byId('approveAllBtn').disabled = pending === 0;
}

function syncBulkbar() {
  const bulkbar = byId('teachersBulkbar');
  const selectedCount = byId('selectedCount');
  if (!bulkbar || !selectedCount) return;

  const visible = getCurrentVisibleTeachers().map(t => t.id);
  const selectedVisibleCount = visible.filter(id => selectedTeacherIds.has(id)).length;
  selectedCount.textContent = selectedVisibleCount;
  bulkbar.style.display = selectedVisibleCount > 0 ? '' : 'none';
}

function clearSelection() {
  selectedTeacherIds.clear();
  syncBulkbar();
  renderCurrentTab();
}

function toggleTeacherSelection(id, checked) {
  if (checked) selectedTeacherIds.add(id);
  else selectedTeacherIds.delete(id);
  syncBulkbar();
}

function toggleSelectAll(checked) {
  getCurrentVisibleTeachers().forEach(t => {
    if (checked) selectedTeacherIds.add(t.id);
    else selectedTeacherIds.delete(t.id);
  });
  syncBulkbar();
  renderCurrentTab();
}

function setTab(tab) {
  currentTab = tab;
  const pendingSection = byId('pendingSection');
  const allSection = byId('allSection');
  const tabPending = byId('tabPending');
  const tabAll = byId('tabAll');

  if (pendingSection) pendingSection.style.display = tab === 'pending' ? '' : 'none';
  if (allSection) allSection.style.display = tab === 'all' ? '' : 'none';
  if (tabPending) {
    tabPending.classList.toggle('active', tab === 'pending');
    tabPending.setAttribute('aria-selected', tab === 'pending' ? 'true' : 'false');
  }
  if (tabAll) {
    tabAll.classList.toggle('active', tab === 'all');
    tabAll.setAttribute('aria-selected', tab === 'all' ? 'true' : 'false');
  }

  syncBulkbar();
}

function openAddTeacherModal() {
  byId('teacherModalBackdrop')?.classList.add('open');
  byId('teacherModalBackdrop')?.setAttribute('aria-hidden', 'false');
  byId('teacherFormError').style.display = 'none';
  byId('teacherNameInput').value = '';
  byId('teacherEmailInput').value = '';
  byId('teacherLanguageInput').value = 'ar';
  byId('teacherStatusInput').value = 'approved';
  setTimeout(() => byId('teacherNameInput')?.focus(), 20);
}

function closeAddTeacherModal() {
  byId('teacherModalBackdrop')?.classList.remove('open');
  byId('teacherModalBackdrop')?.setAttribute('aria-hidden', 'true');
}

function openDeleteModal(items) {
  deleteQueue = items.slice();
  const title = byId('deleteTeacherName');
  const subtitle = byId('deleteTeacherEmail');
  const caption = byId('deleteTeacherSubtitle');
  const error = byId('deleteTeacherError');
  if (error) {
    error.textContent = '';
    error.style.display = 'none';
  }

  if (items.length === 1) {
    title.textContent = items[0].name || 'Teacher';
    subtitle.textContent = items[0].email || 'No email';
    caption.textContent = 'This will deactivate the selected teacher and remove them from active lists.';
  } else {
    title.textContent = `${items.length} teachers selected`;
    subtitle.textContent = 'The selected teachers will be deactivated.';
    caption.textContent = 'This will deactivate the selected teacher records and remove them from active lists.';
  }

  byId('deleteTeacherBackdrop')?.classList.add('open');
  byId('deleteTeacherBackdrop')?.setAttribute('aria-hidden', 'false');
}

function closeDeleteModal() {
  deleteQueue = [];
  byId('deleteTeacherBackdrop')?.classList.remove('open');
  byId('deleteTeacherBackdrop')?.setAttribute('aria-hidden', 'true');
}

async function loadAll() {
  clearAlert();
  await Promise.all([loadPending(), loadAllTeachers()]);
  updateStats();
  renderCurrentTab();
}

async function loadPending() {
  const pendingLoading = byId('pendingLoading');
  const pendingTableWrap = byId('pendingTableWrap');

  try {
    if (pendingLoading) pendingLoading.style.display = '';
    const res = await apiFetch('/teachers/pending');
    if (!res.ok) throw new Error('Failed pending');
    pendingTeachersCache = await res.json();
  } catch (err) {
    console.error('loadPending failed:', err);
    showAlert('Failed to load pending teachers.', 'danger');
  } finally {
    if (pendingLoading) pendingLoading.style.display = 'none';
    if (pendingTableWrap) pendingTableWrap.innerHTML = '';
  }
}

async function loadAllTeachers() {
  const allLoading = byId('allLoading');
  const allTableWrap = byId('allTableWrap');

  try {
    if (allLoading) allLoading.style.display = '';
    const res = await apiFetch('/teachers/all');
    if (!res.ok) throw new Error('Failed all');
    allTeachersCache = await res.json();
  } catch (err) {
    console.error('loadAllTeachers failed:', err);
    showAlert('Failed to load teachers.', 'danger');
  } finally {
    if (allLoading) allLoading.style.display = 'none';
    if (allTableWrap) allTableWrap.innerHTML = '';
  }
}

async function approveTeacher(id) {
  const btn = byId(`btn-approve-${id}`);
  if (btn) {
    btn.disabled = true;
    btn.textContent = '...';
  }

  try {
    const res = await apiFetch(`/teachers/${id}/approve`, { method: 'POST' });
    if (!res.ok) throw new Error('Approve failed');
    showAlert('Teacher approved successfully.', 'success');
    await loadAll();
  } catch (err) {
    console.error('approveTeacher failed:', err);
    showAlert('Could not approve this teacher.', 'danger');
    if (btn) {
      btn.disabled = false;
      btn.textContent = 'Approve';
    }
  }
}

async function approveAll() {
  const btn = byId('approveAllBtn');
  if (btn) btn.disabled = true;
  try {
    const res = await apiFetch('/teachers/approve-all', { method: 'POST' });
    if (!res.ok) throw new Error('Approve all failed');
    const data = await res.json();
    showAlert(data.approved_count > 0 ? `Approved ${data.approved_count} teachers.` : 'No pending teachers found.', 'success');
    await loadAll();
  } catch (err) {
    console.error('approveAll failed:', err);
    showAlert('Could not approve all pending teachers.', 'danger');
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function createTeacher() {
  const name = byId('teacherNameInput')?.value.trim();
  const email = byId('teacherEmailInput')?.value.trim();
  const preferred_language = byId('teacherLanguageInput')?.value || 'ar';
  const status = byId('teacherStatusInput')?.value || 'approved';
  const error = byId('teacherFormError');
  const btn = byId('saveTeacherModalBtn');

  if (error) {
    error.textContent = '';
    error.style.display = 'none';
  }

  if (!name) {
    error.textContent = 'Teacher name is required.';
    error.style.display = 'block';
    return;
  }

  btn.disabled = true;
  btn.textContent = 'Saving...';

  try {
    const res = await apiFetch('/teachers/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email: email || null, preferred_language, status, active: true }),
    });

    if (!res.ok) {
      let msg = 'Failed to create teacher.';
      try {
        const data = await res.json();
        msg = data.detail || msg;
      } catch {}
      throw new Error(msg);
    }

    closeAddTeacherModal();
    showAlert('Teacher created successfully.', 'success');
    await loadAll();
    setTab(status === 'pending' ? 'pending' : 'all');
  } catch (err) {
    console.error('createTeacher failed:', err);
    error.textContent = err.message || 'Failed to create teacher.';
    error.style.display = 'block';
  } finally {
    btn.disabled = false;
    btn.textContent = 'Save Teacher';
  }
}

function startEditTeacher(id) {
  editingTeacherId = id;
  renderCurrentTab();
}

function cancelEditTeacher() {
  editingTeacherId = null;
  renderCurrentTab();
}

async function saveTeacher(id) {
  const row = document.querySelector(`[data-teacher-row="${id}"]`);
  if (!row) return;

  const name = row.querySelector('[data-field="name"]')?.value.trim();
  const email = row.querySelector('[data-field="email"]')?.value.trim();
  const preferred_language = row.querySelector('[data-field="preferred_language"]')?.value || 'ar';
  const status = row.querySelector('[data-field="status"]')?.value || 'approved';

  if (!name) {
    showAlert('Teacher name is required.', 'danger');
    return;
  }

  try {
    const res = await apiFetch(`/teachers/${id}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email: email || null, preferred_language, status }),
    });

    if (!res.ok) {
      let msg = 'Failed to update teacher.';
      try {
        const data = await res.json();
        msg = data.detail || msg;
      } catch {}
      throw new Error(msg);
    }

    editingTeacherId = null;
    showAlert('Teacher updated successfully.', 'success');
    await loadAll();
  } catch (err) {
    console.error('saveTeacher failed:', err);
    showAlert(err.message || 'Failed to update teacher.', 'danger');
  }
}

function requestDeleteTeacher(id) {
  const teacher = allTeachersCache.find(t => t.id === id) || pendingTeachersCache.find(t => t.id === id);
  if (!teacher) return;
  openDeleteModal([teacher]);
}

function requestBulkDelete() {
  const items = getCurrentVisibleTeachers().filter(t => selectedTeacherIds.has(t.id));
  if (items.length === 0) return;
  openDeleteModal(items);
}

async function confirmDeleteTeachers() {
  if (!deleteQueue.length) return;
  const btn = byId('confirmDeleteTeacherBtn');
  const errEl = byId('deleteTeacherError');
  btn.disabled = true;
  btn.textContent = 'Removing...';
  if (errEl) {
    errEl.textContent = '';
    errEl.style.display = 'none';
  }

  try {
    for (const teacher of deleteQueue) {
      const res = await apiFetch(`/teachers/${teacher.id}`, { method: 'DELETE' });
      if (!res.ok) {
        let msg = `Failed to remove ${teacher.name}.`;
        try {
          const data = await res.json();
          msg = data.detail || msg;
        } catch {}
        throw new Error(msg);
      }
      selectedTeacherIds.delete(teacher.id);
    }

    closeDeleteModal();
    showAlert(deleteQueue.length > 1 ? 'Selected teachers removed.' : 'Teacher removed.', 'success');
    await loadAll();
  } catch (err) {
    console.error('confirmDeleteTeachers failed:', err);
    if (errEl) {
      errEl.textContent = err.message || 'Failed to remove teachers.';
      errEl.style.display = 'block';
    }
  } finally {
    btn.disabled = false;
    btn.textContent = 'Remove';
  }
}

function exportTeachersCsv() {
  const rows = getCurrentVisibleTeachers();
  if (!rows.length) {
    showAlert('No teachers available to export.', 'danger');
    return;
  }

  const header = ['Name', 'Email', 'Status', 'Language', 'Created At'];
  const csvRows = [header];
  rows.forEach(t => {
    csvRows.push([
      t.name || '',
      t.email || '',
      t.status || '',
      t.preferred_language === 'ar' ? 'Arabic' : 'English',
      formatDate(t.created_at),
    ]);
  });

  const csv = csvRows
    .map(cols => cols.map(value => `"${String(value).replace(/"/g, '""')}"`).join(','))
    .join('\n');

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `teachers-${currentTab}-${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function emptyState(message, actionLabel = '') {
  return `
    <div class="empty-state">
      <div class="empty-icon">👥</div>
      <p>${message}</p>
      ${actionLabel ? `<button class="btn btn-secondary btn-sm empty-action-btn" type="button" onclick="switchToAllTab()">${actionLabel}</button>` : ''}
    </div>
  `;
}

function switchToAllTab() {
  setTab('all');
  renderCurrentTab();
}

function renderCurrentTab() {
  const wrap = currentTab === 'pending' ? byId('pendingTableWrap') : byId('allTableWrap');
  if (!wrap) return;

  const teachers = getCurrentVisibleTeachers();
  const showApproveBtn = currentTab === 'pending';

  if (!teachers.length) {
    wrap.innerHTML = currentTab === 'pending'
      ? emptyState('No teachers awaiting approval.', 'View All Teachers')
      : emptyState('No teachers found.');
  } else {
    wrap.innerHTML = buildResponsiveTable(teachers, showApproveBtn);
  }

  if (currentTab === 'pending' && byId('allTableWrap')) byId('allTableWrap').innerHTML = '';
  if (currentTab === 'all' && byId('pendingTableWrap')) byId('pendingTableWrap').innerHTML = '';
  syncBulkbar();
}

function buildResponsiveTable(teachers, showApproveBtn) {
  const selectable = currentTab === 'all';
  const allVisibleSelected = selectable && teachers.length > 0 && teachers.every(t => selectedTeacherIds.has(t.id));

  const headers = `
    <tr>
      ${selectable ? `<th class="select-col"><input type="checkbox" ${allVisibleSelected ? 'checked' : ''} onchange="toggleSelectAll(this.checked)"></th>` : '<th>#</th>'}
      <th>Name</th>
      <th>Email</th>
      <th>Status</th>
      <th>Language</th>
      <th>Date</th>
      <th>Actions</th>
    </tr>
  `;

  const rows = teachers.map((teacher, index) => buildTeacherRow(teacher, index, showApproveBtn, selectable)).join('');
  const cards = teachers.map((teacher, index) => buildTeacherCard(teacher, index, showApproveBtn, selectable)).join('');

  return `
    <div class="teachers-data-view">
      <div class="teachers-table-wrap">
        <table class="teacher-table teachers-desktop-table">
          <thead>${headers}</thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
      <div class="teachers-mobile-cards">${cards}</div>
    </div>
  `;
}

function buildTeacherRow(t, index, showApproveBtn, selectable) {
  const isEditing = editingTeacherId === t.id;
  return `
    <tr data-teacher-row="${t.id}">
      ${selectable
        ? `<td class="select-col"><input type="checkbox" ${selectedTeacherIds.has(t.id) ? 'checked' : ''} onchange="toggleTeacherSelection(${t.id}, this.checked)"></td>`
        : `<td>${index + 1}</td>`}
      <td data-label="Name">${isEditing ? `<input class="table-input" data-field="name" value="${escHtml(t.name)}">` : `<strong class="teacher-name">${escHtml(t.name)}</strong>`}</td>
      <td data-label="Email">${isEditing ? `<input class="table-input" data-field="email" value="${escHtml(t.email || '')}" placeholder="Email">` : `<span class="teacher-email">${escHtml(t.email || '—')}</span>`}</td>
      <td data-label="Status">${isEditing ? `<select class="table-select" data-field="status"><option value="approved" ${t.status === 'approved' ? 'selected' : ''}>Approved</option><option value="pending" ${t.status === 'pending' ? 'selected' : ''}>Pending</option></select>` : statusBadge(t.status)}</td>
      <td data-label="Language">${isEditing ? `<select class="table-select" data-field="preferred_language"><option value="ar" ${t.preferred_language === 'ar' ? 'selected' : ''}>Arabic</option><option value="en" ${t.preferred_language === 'en' ? 'selected' : ''}>English</option></select>` : languageChip(t.preferred_language)}</td>
      <td data-label="Date">${formatDate(t.created_at)}</td>
      <td data-label="Actions">${buildActions(t, isEditing, showApproveBtn)}</td>
    </tr>
  `;
}

function buildTeacherCard(t, index, showApproveBtn, selectable) {
  const isEditing = editingTeacherId === t.id;
  return `
    <article class="teacher-mobile-card" data-teacher-row="${t.id}">
      <div class="teacher-mobile-card-top">
        <div>
          <div class="teacher-mobile-index">${selectable ? `<label class="teacher-mobile-checkbox"><input type="checkbox" ${selectedTeacherIds.has(t.id) ? 'checked' : ''} onchange="toggleTeacherSelection(${t.id}, this.checked)"> Select</label>` : `#${index + 1}`}</div>
          <h3>${isEditing ? `<input class="table-input" data-field="name" value="${escHtml(t.name)}">` : escHtml(t.name)}</h3>
        </div>
        ${isEditing ? '' : statusBadge(t.status)}
      </div>
      <div class="teacher-mobile-meta"><span>Email</span>${isEditing ? `<input class="table-input" data-field="email" value="${escHtml(t.email || '')}" placeholder="Email">` : escHtml(t.email || '—')}</div>
      <div class="teacher-mobile-meta"><span>Language</span>${isEditing ? `<select class="table-select" data-field="preferred_language"><option value="ar" ${t.preferred_language === 'ar' ? 'selected' : ''}>Arabic</option><option value="en" ${t.preferred_language === 'en' ? 'selected' : ''}>English</option></select>` : languageChip(t.preferred_language)}</div>
      <div class="teacher-mobile-meta"><span>Status</span>${isEditing ? `<select class="table-select" data-field="status"><option value="approved" ${t.status === 'approved' ? 'selected' : ''}>Approved</option><option value="pending" ${t.status === 'pending' ? 'selected' : ''}>Pending</option></select>` : statusBadge(t.status)}</div>
      <div class="teacher-mobile-meta"><span>Date</span>${formatDate(t.created_at)}</div>
      <div class="teacher-mobile-actions">${buildActions(t, isEditing, showApproveBtn)}</div>
    </article>
  `;
}

function buildActions(t, isEditing, showApproveBtn) {
  if (isEditing) {
    return `
      <div class="teacher-actions">
        <button class="btn btn-success btn-sm" type="button" onclick="saveTeacher(${t.id})">Save</button>
        <button class="btn btn-secondary btn-sm" type="button" onclick="cancelEditTeacher()">Cancel</button>
      </div>
    `;
  }

  return `
    <div class="teacher-actions">
      ${showApproveBtn ? `<button class="btn btn-success btn-sm" type="button" id="btn-approve-${t.id}" onclick="approveTeacher(${t.id})">Approve</button>` : ''}
      <button class="btn btn-secondary btn-sm" type="button" onclick="startEditTeacher(${t.id})">Edit</button>
      <button class="btn btn-danger btn-sm" type="button" onclick="requestDeleteTeacher(${t.id})">Remove</button>
    </div>
  `;
}

function wireEvents() {
  byId('addTeacherBtn')?.addEventListener('click', openAddTeacherModal);
  byId('closeTeacherModalBtn')?.addEventListener('click', closeAddTeacherModal);
  byId('cancelTeacherModalBtn')?.addEventListener('click', closeAddTeacherModal);
  byId('saveTeacherModalBtn')?.addEventListener('click', createTeacher);
  byId('refreshTeachersBtn')?.addEventListener('click', loadAll);
  byId('approveAllBtn')?.addEventListener('click', approveAll);
  byId('exportTeachersBtn')?.addEventListener('click', exportTeachersCsv);
  byId('tabPending')?.addEventListener('click', () => { setTab('pending'); renderCurrentTab(); });
  byId('tabAll')?.addEventListener('click', () => { setTab('all'); renderCurrentTab(); });
  byId('teacherSearchInput')?.addEventListener('input', (e) => {
    searchTerm = normalize(e.target.value);
    renderCurrentTab();
  });
  byId('clearSelectionBtn')?.addEventListener('click', clearSelection);
  byId('bulkDeleteBtn')?.addEventListener('click', requestBulkDelete);
  byId('closeDeleteModalBtn')?.addEventListener('click', closeDeleteModal);
  byId('cancelDeleteTeacherBtn')?.addEventListener('click', closeDeleteModal);
  byId('confirmDeleteTeacherBtn')?.addEventListener('click', confirmDeleteTeachers);

  byId('teacherModalBackdrop')?.addEventListener('click', (e) => {
    if (e.target === byId('teacherModalBackdrop')) closeAddTeacherModal();
  });
  byId('deleteTeacherBackdrop')?.addEventListener('click', (e) => {
    if (e.target === byId('deleteTeacherBackdrop')) closeDeleteModal();
  });
}

async function initTeachersPage() {
  try {
    wireEvents();
    setTab('pending');
    await loadAll();
  } catch (err) {
    console.error('initTeachersPage failed:', err);
    showAlert('Failed to initialize teachers page.', 'danger');
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initTeachersPage);
} else {
  initTeachersPage();
}
