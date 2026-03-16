/**
 * teachers.js — Teacher Approval management for Firduty Admin UI
 *
 * Endpoints used:
 *   GET  /teachers/pending
 *   GET  /teachers/all
 *   POST /teachers/{id}/approve
 *   POST /teachers/approve-all
 */

let currentTab = 'pending';
let teacherSearchTerm = '';
let pendingTeachersCache = [];
let allTeachersCache = [];

function byId(id) {
  return document.getElementById(id);
}

/* ───────────────── Tab management ───────────────── */

function showTab(tab) {
  currentTab = tab;

  const pendingSection = byId('pendingSection');
  const allSection = byId('allSection');
  const tabPending = byId('tabPending');
  const tabAll = byId('tabAll');

  if (pendingSection) pendingSection.style.display = tab === 'pending' ? '' : 'none';
  if (allSection) allSection.style.display = tab === 'all' ? '' : 'none';

  if (tabPending) tabPending.classList.toggle('active', tab === 'pending');
  if (tabAll) tabAll.classList.toggle('active', tab === 'all');

  renderVisibleTables();
}

function setTeacherSearch(value) {
  teacherSearchTerm = String(value || '').trim().toLowerCase();
  renderVisibleTables();
}

/* ───────────────── Data loading ───────────────── */

async function loadAll() {
  clearAlert();
  await Promise.all([loadPending(), loadAllTeachers()]);
}

async function loadPending() {
  const pendingLoading = byId('pendingLoading');
  const approveAllBtn = byId('approveAllBtn');

  try {
    if (pendingLoading) pendingLoading.style.display = '';

    const res = await apiFetch('/teachers/pending');

    if (!res.ok) {
      showAlert(I18N.t('error_generic'), 'danger');
      return;
    }

    pendingTeachersCache = await res.json();

    if (approveAllBtn) {
      approveAllBtn.disabled = pendingTeachersCache.length === 0;
    }

    updateStats();
    renderVisibleTables();
  } catch (err) {
    console.error('loadPending failed:', err);
    showAlert(I18N.t('error_generic'), 'danger');
  } finally {
    if (pendingLoading) pendingLoading.style.display = 'none';
  }
}

async function loadAllTeachers() {
  const allLoading = byId('allLoading');

  try {
    if (allLoading) allLoading.style.display = '';

    const res = await apiFetch('/teachers/all');

    if (!res.ok) {
      showAlert(I18N.t('error_generic'), 'danger');
      return;
    }

    allTeachersCache = await res.json();

    updateStats();
    renderVisibleTables();
  } catch (err) {
    console.error('loadAllTeachers failed:', err);
    showAlert(I18N.t('error_generic'), 'danger');
  } finally {
    if (allLoading) allLoading.style.display = 'none';
  }
}

function filterTeachers(list) {
  if (!teacherSearchTerm) return list;
  return list.filter(t => {
    const name = String(t.name || '').toLowerCase();
    const email = String(t.email || '').toLowerCase();
    const status = String(t.status || '').toLowerCase();
    return name.includes(teacherSearchTerm) || email.includes(teacherSearchTerm) || status.includes(teacherSearchTerm);
  });
}

function updateStats() {
  const statPending = byId('statPending');
  const statApproved = byId('statApproved');
  const statActive = byId('statActive');
  const pendingCount = byId('pendingCount');

  const pending = pendingTeachersCache.length;
  const approved = allTeachersCache.filter(t => t.status === 'approved').length;
  const active = allTeachersCache.filter(t => t.active !== false).length;

  if (statPending) statPending.textContent = String(pending);
  if (statApproved) statApproved.textContent = String(approved);
  if (statActive) statActive.textContent = String(active);
  if (pendingCount) pendingCount.textContent = String(pending);
}

function renderVisibleTables() {
  const pendingWrap = byId('pendingTableWrap');
  const allWrap = byId('allTableWrap');

  if (pendingWrap) {
    const teachers = filterTeachers(pendingTeachersCache);
    pendingWrap.innerHTML = teachers.length === 0 ? emptyState('no_pending_teachers') : buildTable(teachers, true);
  }

  if (allWrap) {
    const teachers = filterTeachers(allTeachersCache);
    allWrap.innerHTML = teachers.length === 0 ? emptyState('no_teachers_yet') : buildTable(teachers, false);
  }
}

/* ───────────────── Approve actions ───────────────── */

async function approveTeacher(id) {
  const btn = byId(`btn-approve-${id}`);

  if (btn) {
    btn.disabled = true;
    btn.textContent = '...';
  }

  try {
    const res = await apiFetch(`/teachers/${id}/approve`, { method: 'POST' });

    if (!res.ok) {
      showAlert(I18N.t('error_generic'), 'danger');

      if (btn) {
        btn.disabled = false;
        btn.textContent = I18N.t('approve');
      }
      return;
    }

    showAlert(I18N.t('teacher_approved_ok'), 'success');
    await loadAll();
  } catch (err) {
    console.error('approveTeacher failed:', err);
    showAlert(I18N.t('error_generic'), 'danger');

    if (btn) {
      btn.disabled = false;
      btn.textContent = I18N.t('approve');
    }
  }
}

async function approveAll() {
  const btn = byId('approveAllBtn');
  if (btn) btn.disabled = true;

  try {
    const res = await apiFetch('/teachers/approve-all', { method: 'POST' });

    if (!res.ok) {
      showAlert(I18N.t('error_generic'), 'danger');
      if (btn) btn.disabled = false;
      return;
    }

    const data = await res.json();
    const count = data.approved_count ?? 0;

    showAlert(
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

/* ───────────────── Table builder ───────────────── */

function buildTable(teachers, showApproveBtn) {
  const isAr = I18N.getLang() === 'ar';
  const labels = {
    index: '#',
    name: I18N.t('name'),
    email: 'Email',
    status: I18N.t('status'),
    language: I18N.t('language'),
    date: I18N.t('date'),
    actions: I18N.t('actions'),
  };

  const headers = [
    `<th>${labels.index}</th>`,
    `<th>${labels.name}</th>`,
    `<th>${labels.email}</th>`,
    `<th>${labels.status}</th>`,
    `<th>${labels.language}</th>`,
    `<th>${labels.date}</th>`,
    showApproveBtn ? `<th>${labels.actions}</th>` : ''
  ].join('');

  const rows = teachers.map((t, i) => {
    const statusBadge = t.status === 'pending'
      ? `<span class="badge badge-pending">${I18N.t('status_pending')}</span>`
      : `<span class="badge badge-approved">${I18N.t('status_approved')}</span>`;

    const langText = t.preferred_language === 'ar' ? I18N.t('arabic') : I18N.t('english');
    const createdAt = t.created_at
      ? new Date(t.created_at).toLocaleDateString(isAr ? 'ar-OM' : 'en-GB')
      : '—';

    const email = t.email || '—';

    const approveCell = showApproveBtn
      ? `<td class="teacher-actions-cell" data-label="${escHtml(labels.actions)}">
          <button class="btn btn-success btn-sm" id="btn-approve-${t.id}" onclick="approveTeacher(${t.id})">
            ${I18N.t('approve')}
          </button>
        </td>`
      : '';

    return `
      <tr>
        <td data-label="${escHtml(labels.index)}">${i + 1}</td>
        <td class="teacher-name-cell" data-label="${escHtml(labels.name)}"><strong>${escHtml(t.name)}</strong></td>
        <td data-label="${escHtml(labels.email)}">${escHtml(email)}</td>
        <td data-label="${escHtml(labels.status)}">${statusBadge}</td>
        <td data-label="${escHtml(labels.language)}">${langText}</td>
        <td data-label="${escHtml(labels.date)}">${createdAt}</td>
        ${approveCell}
      </tr>
    `;
  }).join('');

  return `
    <table class="teacher-table">
      <thead><tr>${headers}</tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

/* ───────────────── Helpers ───────────────── */

function emptyState(key) {
  return `
    <div class="empty-state">
      <div class="empty-icon">👥</div>
      <p>${I18N.t(key)}</p>
    </div>
  `;
}

function showAlert(msg, type) {
  const el = byId('alertMsg');
  if (!el) return;

  el.className = `alert alert-${type}`;
  el.textContent = msg;
  el.style.display = '';

  setTimeout(() => {
    el.style.display = 'none';
  }, 4000);
}

function clearAlert() {
  const el = byId('alertMsg');
  if (el) el.style.display = 'none';
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/* ───────────────── Page init ───────────────── */

async function initTeachersPage() {
  try {
    const search = byId('teacherSearchInput');
    if (search && !search.dataset.bound) {
      search.addEventListener('input', e => setTeacherSearch(e.target.value || ''));
      search.dataset.bound = 'true';
    }

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
