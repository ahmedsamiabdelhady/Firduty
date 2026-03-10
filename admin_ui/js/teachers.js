/**
 * teachers.js — Teacher Approval management for Firduty Admin UI
 *
 * Endpoints used:
 *   GET  /teachers/pending          — list teachers awaiting approval
 *   GET  /teachers/all              — list all teachers
 *   POST /teachers/{id}/approve     — approve a single teacher
 *   POST /teachers/approve-all      — approve all pending teachers
 */

const API_BASE = localStorage.getItem('firduty_api') || 'https://YOUR-APP-NAME.koyeb.app/';
const TOKEN = () => localStorage.getItem('firduty_token');

function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${TOKEN()}`,
  };
}

function logout() {
  localStorage.removeItem('firduty_token');
  window.location.href = 'login.html';
}

// ─── Tab management ───────────────────────────────────────────────────────────

let currentTab = 'pending';

function showTab(tab) {
  currentTab = tab;
  document.getElementById('pendingSection').style.display = tab === 'pending' ? '' : 'none';
  document.getElementById('allSection').style.display     = tab === 'all'     ? '' : 'none';
  document.getElementById('tabPending').classList.toggle('active', tab === 'pending');
  document.getElementById('tabAll').classList.toggle('active',     tab === 'all');
}

// ─── Data loading ─────────────────────────────────────────────────────────────

async function loadAll() {
  clearAlert();
  await Promise.all([loadPending(), loadAllTeachers()]);
}

async function loadPending() {
  document.getElementById('pendingLoading').style.display = '';
  document.getElementById('pendingTableWrap').innerHTML = '';

  const res = await fetch(`${API_BASE}teachers/pending`, { headers: authHeaders() });
  document.getElementById('pendingLoading').style.display = 'none';

  if (res.status === 401) { logout(); return; }
  if (!res.ok) {
    showAlert(I18N.t('error_generic'), 'danger');
    return;
  }

  const teachers = await res.json();

  // Update pending badge
  const badge = document.getElementById('pendingCount');
  if (teachers.length > 0) {
    badge.textContent = teachers.length;
    badge.style.display = '';
  } else {
    badge.style.display = 'none';
  }

  // Disable "Approve All" if nothing pending
  document.getElementById('approveAllBtn').disabled = teachers.length === 0;

  document.getElementById('pendingTableWrap').innerHTML =
    teachers.length === 0 ? emptyState('no_pending_teachers') : buildTable(teachers, true);
}

async function loadAllTeachers() {
  document.getElementById('allLoading').style.display = '';
  document.getElementById('allTableWrap').innerHTML = '';

  const res = await fetch(`${API_BASE}teachers/all`, { headers: authHeaders() });
  document.getElementById('allLoading').style.display = 'none';

  if (res.status === 401) { logout(); return; }
  if (!res.ok) {
    showAlert(I18N.t('error_generic'), 'danger');
    return;
  }

  const teachers = await res.json();
  document.getElementById('allTableWrap').innerHTML =
    teachers.length === 0 ? emptyState('no_teachers_yet') : buildTable(teachers, false);
}

// ─── Approve actions ──────────────────────────────────────────────────────────

async function approveTeacher(id) {
  const btn = document.getElementById(`btn-approve-${id}`);
  if (btn) { btn.disabled = true; btn.textContent = '...'; }

  const res = await fetch(`${API_BASE}teachers/${id}/approve`, {
    method: 'POST',
    headers: authHeaders(),
  });

  if (res.status === 401) { logout(); return; }
  if (!res.ok) {
    showAlert(I18N.t('error_generic'), 'danger');
    if (btn) { btn.disabled = false; btn.textContent = I18N.t('approve'); }
    return;
  }

  showAlert(I18N.t('teacher_approved_ok'), 'success');
  await loadAll();
}

async function approveAll() {
  const btn = document.getElementById('approveAllBtn');
  btn.disabled = true;

  const res = await fetch(`${API_BASE}teachers/approve-all`, {
    method: 'POST',
    headers: authHeaders(),
  });

  if (res.status === 401) { logout(); return; }
  if (!res.ok) {
    showAlert(I18N.t('error_generic'), 'danger');
    btn.disabled = false;
    return;
  }

  const data = await res.json();
  const count = data.approved_count ?? 0;
  showAlert(
    count > 0
      ? `${I18N.t('all_approved_ok')} (${count})`
      : I18N.t('no_pending_teachers'),
    'success',
  );
  await loadAll();
}

// ─── Render helpers ───────────────────────────────────────────────────────────

function buildTable(teachers, showApproveBtn) {
  const isAr = I18N.getLang() === 'ar';

  const headers = [
    `<th>#</th>`,
    `<th data-i18n="name">${I18N.t('name')}</th>`,
    `<th>Email</th>`,
    `<th data-i18n="status">${I18N.t('status')}</th>`,
    `<th data-i18n="language">${I18N.t('language')}</th>`,
    `<th data-i18n="date">${I18N.t('date')}</th>`,
    showApproveBtn ? `<th data-i18n="actions">${I18N.t('actions')}</th>` : '',
  ].join('');

  const rows = teachers.map((t, i) => {
    const statusBadge = t.status === 'pending'
      ? `<span class="badge badge-pending">${I18N.t('status_pending')}</span>`
      : `<span class="badge badge-approved">${I18N.t('status_approved')}</span>`;

    const lang = t.preferred_language === 'ar' ? I18N.t('arabic') : I18N.t('english');
    const createdAt = t.created_at ? new Date(t.created_at).toLocaleDateString(isAr ? 'ar-OM' : 'en-GB') : '—';
    const email = t.email || '—';

    const approveCell = showApproveBtn
      ? `<td><button class="btn btn-success btn-sm" id="btn-approve-${t.id}"
             onclick="approveTeacher(${t.id})">${I18N.t('approve')}</button></td>`
      : '';

    return `<tr>
      <td>${i + 1}</td>
      <td><strong>${escHtml(t.name)}</strong></td>
      <td>${escHtml(email)}</td>
      <td>${statusBadge}</td>
      <td>${lang}</td>
      <td>${createdAt}</td>
      ${approveCell}
    </tr>`;
  }).join('');

  return `<table class="teacher-table">
    <thead><tr>${headers}</tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

function emptyState(key) {
  return `<div class="empty-state">
    <div class="empty-icon">👥</div>
    <p>${I18N.t(key)}</p>
  </div>`;
}

function showAlert(msg, type) {
  const el = document.getElementById('alertMsg');
  el.className = `alert alert-${type}`;
  el.textContent = msg;
  el.style.display = '';
  setTimeout(() => { el.style.display = 'none'; }, 4000);
}

function clearAlert() {
  document.getElementById('alertMsg').style.display = 'none';
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}