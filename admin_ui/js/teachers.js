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
}

/* ───────────────── Data loading ───────────────── */

async function loadAll() {
  clearAlert();
  await Promise.all([loadPending(), loadAllTeachers()]);
}

async function loadPending() {

  const pendingLoading = byId('pendingLoading');
  const pendingTableWrap = byId('pendingTableWrap');
  const pendingCount = byId('pendingCount');
  const approveAllBtn = byId('approveAllBtn');

  if (pendingLoading) pendingLoading.style.display = '';
  if (pendingTableWrap) pendingTableWrap.innerHTML = '';

  const res = await apiFetch('/teachers/pending');

  if (pendingLoading) pendingLoading.style.display = 'none';

  if (!res.ok) {
    showAlert(I18N.t('error_generic'), 'danger');
    return;
  }

  const teachers = await res.json();

  /* update pending badge */
  if (pendingCount) {
    if (teachers.length > 0) {
      pendingCount.textContent = teachers.length;
      pendingCount.style.display = '';
    } else {
      pendingCount.style.display = 'none';
    }
  }

  /* disable approve all if empty */
  if (approveAllBtn) approveAllBtn.disabled = teachers.length === 0;

  if (pendingTableWrap) {
    pendingTableWrap.innerHTML =
      teachers.length === 0
        ? emptyState('no_pending_teachers')
        : buildTable(teachers, true);
  }
}

async function loadAllTeachers() {

  const allLoading = byId('allLoading');
  const allTableWrap = byId('allTableWrap');

  if (allLoading) allLoading.style.display = '';
  if (allTableWrap) allTableWrap.innerHTML = '';

  const res = await apiFetch('/teachers/all');

  if (allLoading) allLoading.style.display = 'none';

  if (!res.ok) {
    showAlert(I18N.t('error_generic'), 'danger');
    return;
  }

  const teachers = await res.json();

  if (allTableWrap) {
    allTableWrap.innerHTML =
      teachers.length === 0
        ? emptyState('no_teachers_yet')
        : buildTable(teachers, false);
  }
}

/* ───────────────── Approve actions ───────────────── */

async function approveTeacher(id) {

  const btn = byId(`btn-approve-${id}`);

  if (btn) {
    btn.disabled = true;
    btn.textContent = '...';
  }

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
}

async function approveAll() {

  const btn = byId('approveAllBtn');
  if (btn) btn.disabled = true;

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
}

/* ───────────────── Table builder ───────────────── */

function buildTable(teachers, showApproveBtn) {

  const isAr = I18N.getLang() === 'ar';

  const headers = [
    `<th>#</th>`,
    `<th data-i18n="name">${I18N.t('name')}</th>`,
    `<th>Email</th>`,
    `<th data-i18n="status">${I18N.t('status')}</th>`,
    `<th data-i18n="language">${I18N.t('language')}</th>`,
    `<th data-i18n="date">${I18N.t('date')}</th>`,
    showApproveBtn ? `<th data-i18n="actions">${I18N.t('actions')}</th>` : ''
  ].join('');

  const rows = teachers.map((t, i) => {

    const statusBadge = t.status === 'pending'
      ? `<span class="badge badge-pending">${I18N.t('status_pending')}</span>`
      : `<span class="badge badge-approved">${I18N.t('status_approved')}</span>`;

    const lang =
      t.preferred_language === 'ar'
        ? I18N.t('arabic')
        : I18N.t('english');

    const createdAt = t.created_at
      ? new Date(t.created_at).toLocaleDateString(isAr ? 'ar-OM' : 'en-GB')
      : '—';

    const email = t.email || '—';

    const approveCell = showApproveBtn
      ? `<td>
          <button class="btn btn-success btn-sm"
            id="btn-approve-${t.id}"
            onclick="approveTeacher(${t.id})">
            ${I18N.t('approve')}
          </button>
        </td>`
      : '';

    return `
      <tr>
        <td>${i + 1}</td>
        <td><strong>${escHtml(t.name)}</strong></td>
        <td>${escHtml(email)}</td>
        <td>${statusBadge}</td>
        <td>${lang}</td>
        <td>${createdAt}</td>
        ${approveCell}
      </tr>
    `;

  }).join('');

  return `
    <table class="teacher-table">
      <thead>
        <tr>${headers}</tr>
      </thead>
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