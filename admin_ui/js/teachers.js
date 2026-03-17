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
let deletingTeacherId = null;

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
  }, 3500);
}

function clearAlert() {
  const el = byId('alertMsg');
  if (el) el.style.display = 'none';
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

function normalize(str) {
  return String(str || '').trim().toLowerCase();
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

function updateSummary() {
  const activeTeachers = allTeachersCache.filter(t => t.active !== false);
  const approvedTeachers = allTeachersCache.filter(t => t.status === 'approved' && t.active !== false);
  const pendingTeachers = pendingTeachersCache.filter(t => t.active !== false);

  const pendingEl = byId('summaryPendingValue');
  const approvedEl = byId('summaryApprovedValue');
  const totalEl = byId('summaryTotalValue');
  const pendingCount = byId('pendingCount');

  if (pendingEl) pendingEl.textContent = pendingTeachers.length;
  if (approvedEl) approvedEl.textContent = approvedTeachers.length;
  if (totalEl) totalEl.textContent = activeTeachers.length;
  if (pendingCount) pendingCount.textContent = pendingTeachers.length;

  const approveAllBtn = byId('approveAllBtn');
  if (approveAllBtn) approveAllBtn.disabled = pendingTeachers.length === 0;
}

function emptyState(message) {
  return `
    <div class="empty-state">
      <div class="empty-icon">👥</div>
      <p>${escHtml(message)}</p>
    </div>
  `;
}

function statusBadge(status) {
  const pending = status === 'pending';
  return `<span class="badge ${pending ? 'badge-pending' : 'badge-approved'}">${pending ? 'Pending' : 'Approved'}</span>`;
}

function languageBadge(language) {
  const label = language === 'en' ? 'English' : 'Arabic';
  return `<span class="lang-chip">${label}</span>`;
}

function teacherCardActions(t, showApproveBtn) {
  return `
    <div class="teacher-actions">
      ${showApproveBtn ? `<button class="btn btn-success btn-sm" type="button" onclick="approveTeacher(${t.id})">Approve</button>` : ''}
      <button class="btn btn-secondary btn-sm" type="button" onclick="openEditTeacherModal(${t.id})">Edit</button>
      <button class="btn btn-danger btn-sm" type="button" onclick="openDeleteTeacherModal(${t.id})">Remove</button>
    </div>
  `;
}

function buildDesktopTable(teachers, showApproveBtn) {
  const rows = teachers.map((t, i) => `
    <tr>
      <td>${i + 1}</td>
      <td><strong>${escHtml(t.name)}</strong></td>
      <td>${escHtml(t.email || '—')}</td>
      <td>${statusBadge(t.status)}</td>
      <td>${languageBadge(t.preferred_language)}</td>
      <td>${formatDate(t.created_at)}</td>
      <td>
        ${teacherCardActions(t, showApproveBtn)}
      </td>
    </tr>
  `).join('');

  return `
    <div class="teachers-table-wrap">
      <table class="teacher-table">
        <thead>
          <tr>
            <th>#</th>
            <th>Name</th>
            <th>Email</th>
            <th>Status</th>
            <th>Language</th>
            <th>Date</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function buildMobileCards(teachers, showApproveBtn) {
  return `
    <div class="teacher-cards-list">
      ${teachers.map(t => `
        <article class="teacher-card-mobile">
          <div class="teacher-card-row">
            <span class="teacher-card-label">Name</span>
            <strong class="teacher-card-value">${escHtml(t.name)}</strong>
          </div>
          <div class="teacher-card-row">
            <span class="teacher-card-label">Email</span>
            <span class="teacher-card-value teacher-email-mobile">${escHtml(t.email || '—')}</span>
          </div>
          <div class="teacher-card-meta">
            ${statusBadge(t.status)}
            ${languageBadge(t.preferred_language)}
            <span class="teacher-card-date">${formatDate(t.created_at)}</span>
          </div>
          ${teacherCardActions(t, showApproveBtn)}
        </article>
      `).join('')}
    </div>
  `;
}

function buildTeachersView(teachers, showApproveBtn) {
  if (!teachers.length) {
    return emptyState(showApproveBtn ? 'No teachers awaiting approval.' : 'No teachers found.');
  }
  return `${buildDesktopTable(teachers, showApproveBtn)}${buildMobileCards(teachers, showApproveBtn)}`;
}

function renderPending() {
  const wrap = byId('pendingTableWrap');
  if (!wrap) return;
  wrap.innerHTML = buildTeachersView(getFilteredPending(), true);
}

function renderAllTeachers() {
  const wrap = byId('allTableWrap');
  if (!wrap) return;
  wrap.innerHTML = buildTeachersView(getFilteredAll(), false);
}

function renderAllViews() {
  updateSummary();
  renderPending();
  renderAllTeachers();
}

function showTab(tab) {
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
}

async function loadPending() {
  const loading = byId('pendingLoading');
  try {
    if (loading) loading.style.display = '';
    const res = await apiFetch('/teachers/pending');
    if (!res.ok) {
      showAlert('Failed to load pending teachers.', 'danger');
      return;
    }
    pendingTeachersCache = await res.json();
    renderPending();
    updateSummary();
  } catch (err) {
    console.error('loadPending failed:', err);
    showAlert('Failed to load pending teachers.', 'danger');
  } finally {
    if (loading) loading.style.display = 'none';
  }
}

async function loadAllTeachers() {
  const loading = byId('allLoading');
  try {
    if (loading) loading.style.display = '';
    const res = await apiFetch('/teachers/all');
    if (!res.ok) {
      showAlert('Failed to load teachers.', 'danger');
      return;
    }
    const rows = await res.json();
    allTeachersCache = Array.isArray(rows) ? rows.filter(t => t.active !== false) : [];
    renderAllTeachers();
    updateSummary();
  } catch (err) {
    console.error('loadAllTeachers failed:', err);
    showAlert('Failed to load teachers.', 'danger');
  } finally {
    if (loading) loading.style.display = 'none';
  }
}

async function loadAll() {
  clearAlert();
  await Promise.all([loadPending(), loadAllTeachers()]);
}

async function approveTeacher(id) {
  try {
    const res = await apiFetch(`/teachers/${id}/approve`, { method: 'POST' });
    if (!res.ok) {
      showAlert('Failed to approve teacher.', 'danger');
      return;
    }
    showAlert('Teacher approved successfully.', 'success');
    await loadAll();
  } catch (err) {
    console.error('approveTeacher failed:', err);
    showAlert('Failed to approve teacher.', 'danger');
  }
}

async function approveAll() {
  const btn = byId('approveAllBtn');
  if (btn) btn.disabled = true;
  try {
    const res = await apiFetch('/teachers/approve-all', { method: 'POST' });
    if (!res.ok) {
      showAlert('Failed to approve pending teachers.', 'danger');
      return;
    }
    const data = await res.json();
    showAlert(`Approved ${data.approved_count ?? 0} teachers.`, 'success');
    await loadAll();
  } catch (err) {
    console.error('approveAll failed:', err);
    showAlert('Failed to approve pending teachers.', 'danger');
  } finally {
    if (btn) btn.disabled = false;
  }
}

function resetTeacherForm() {
  editingTeacherId = null;
  byId('teacherModalTitle').textContent = 'Add Teacher';
  byId('teacherModalSubtitle').textContent = 'Create a teacher record directly from the admin dashboard.';
  byId('saveTeacherModalBtn').textContent = 'Save Teacher';
  byId('teacherNameInput').value = '';
  byId('teacherEmailInput').value = '';
  byId('teacherLanguageInput').value = 'ar';
  byId('teacherStatusInput').value = 'approved';
  byId('teacherFormError').style.display = 'none';
  byId('teacherFormError').textContent = '';
}

function openTeacherModal() {
  byId('teacherModalBackdrop').classList.add('open');
  byId('teacherModalBackdrop').setAttribute('aria-hidden', 'false');
}

function closeTeacherModal() {
  byId('teacherModalBackdrop').classList.remove('open');
  byId('teacherModalBackdrop').setAttribute('aria-hidden', 'true');
  resetTeacherForm();
}

function openAddTeacherModal() {
  resetTeacherForm();
  openTeacherModal();
}

function openEditTeacherModal(id) {
  const teacher = allTeachersCache.find(t => t.id === id) || pendingTeachersCache.find(t => t.id === id);
  if (!teacher) return;
  editingTeacherId = id;
  byId('teacherModalTitle').textContent = 'Edit Teacher';
  byId('teacherModalSubtitle').textContent = 'Update teacher details and approval status.';
  byId('saveTeacherModalBtn').textContent = 'Save Changes';
  byId('teacherNameInput').value = teacher.name || '';
  byId('teacherEmailInput').value = teacher.email || '';
  byId('teacherLanguageInput').value = teacher.preferred_language || 'ar';
  byId('teacherStatusInput').value = teacher.status || 'approved';
  byId('teacherFormError').style.display = 'none';
  byId('teacherFormError').textContent = '';
  openTeacherModal();
}

async function saveTeacher() {
  const errorEl = byId('teacherFormError');
  const saveBtn = byId('saveTeacherModalBtn');
  const name = byId('teacherNameInput').value.trim();
  const email = byId('teacherEmailInput').value.trim();
  const preferred_language = byId('teacherLanguageInput').value;
  const status = byId('teacherStatusInput').value;

  if (!name) {
    errorEl.textContent = 'Teacher name is required.';
    errorEl.style.display = 'block';
    return;
  }

  const payload = editingTeacherId
    ? { name, email: email || null, preferred_language, status }
    : { name, email: email || null, preferred_language, status, active: true };

  saveBtn.disabled = true;
  try {
    const res = await apiFetch(editingTeacherId ? `/teachers/${editingTeacherId}` : '/teachers/', {
      method: editingTeacherId ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const text = await res.text();
      errorEl.textContent = text || 'Failed to save teacher.';
      errorEl.style.display = 'block';
      return;
    }

    closeTeacherModal();
    showAlert(editingTeacherId ? 'Teacher updated successfully.' : 'Teacher created successfully.', 'success');
    await loadAll();
    showTab(currentTab);
  } catch (err) {
    console.error('saveTeacher failed:', err);
    errorEl.textContent = 'Failed to save teacher.';
    errorEl.style.display = 'block';
  } finally {
    saveBtn.disabled = false;
  }
}

function openDeleteTeacherModal(id) {
  const teacher = allTeachersCache.find(t => t.id === id) || pendingTeachersCache.find(t => t.id === id);
  if (!teacher) return;
  deletingTeacherId = id;
  byId('deleteTeacherName').textContent = teacher.name || 'Teacher';
  byId('deleteTeacherEmail').textContent = teacher.email || 'No email';
  byId('deleteTeacherError').style.display = 'none';
  byId('deleteTeacherError').textContent = '';
  byId('deleteTeacherBackdrop').classList.add('open');
  byId('deleteTeacherBackdrop').setAttribute('aria-hidden', 'false');
}

function closeDeleteTeacherModal() {
  deletingTeacherId = null;
  byId('deleteTeacherBackdrop').classList.remove('open');
  byId('deleteTeacherBackdrop').setAttribute('aria-hidden', 'true');
  byId('deleteTeacherError').style.display = 'none';
  byId('deleteTeacherError').textContent = '';
}

async function confirmDeleteTeacher() {
  if (!deletingTeacherId) return;
  const errorEl = byId('deleteTeacherError');
  const btn = byId('confirmDeleteTeacherBtn');
  btn.disabled = true;
  try {
    const res = await apiFetch(`/teachers/${deletingTeacherId}`, { method: 'DELETE' });
    if (!res.ok) {
      const text = await res.text();
      errorEl.textContent = text || 'Failed to remove teacher.';
      errorEl.style.display = 'block';
      return;
    }
    closeDeleteTeacherModal();
    showAlert('Teacher removed successfully.', 'success');
    await loadAll();
    showTab(currentTab);
  } catch (err) {
    console.error('confirmDeleteTeacher failed:', err);
    errorEl.textContent = 'Failed to remove teacher.';
    errorEl.style.display = 'block';
  } finally {
    btn.disabled = false;
  }
}

function handleSearchInput(event) {
  searchTerm = normalize(event.target.value);
  renderAllViews();
  showTab(currentTab);
}

function bindEvents() {
  byId('tabPending')?.addEventListener('click', () => showTab('pending'));
  byId('tabAll')?.addEventListener('click', () => showTab('all'));
  byId('teacherSearchInput')?.addEventListener('input', handleSearchInput);
  byId('refreshTeachersBtn')?.addEventListener('click', loadAll);
  byId('approveAllBtn')?.addEventListener('click', approveAll);
  byId('addTeacherBtn')?.addEventListener('click', openAddTeacherModal);
  byId('closeTeacherModalBtn')?.addEventListener('click', closeTeacherModal);
  byId('cancelTeacherModalBtn')?.addEventListener('click', closeTeacherModal);
  byId('saveTeacherModalBtn')?.addEventListener('click', saveTeacher);
  byId('closeDeleteModalBtn')?.addEventListener('click', closeDeleteTeacherModal);
  byId('cancelDeleteTeacherBtn')?.addEventListener('click', closeDeleteTeacherModal);
  byId('confirmDeleteTeacherBtn')?.addEventListener('click', confirmDeleteTeacher);

  byId('teacherModalBackdrop')?.addEventListener('click', (e) => {
    if (e.target === byId('teacherModalBackdrop')) closeTeacherModal();
  });
  byId('deleteTeacherBackdrop')?.addEventListener('click', (e) => {
    if (e.target === byId('deleteTeacherBackdrop')) closeDeleteTeacherModal();
  });
}

async function initTeachersPage() {
  bindEvents();
  showTab('pending');
  await loadAll();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initTeachersPage);
} else {
  initTeachersPage();
}
