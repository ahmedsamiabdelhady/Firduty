/**
 * reports.js — Monthly Points Report for Firduty Admin UI  v2.5
 *
 * Previously all this logic lived inline in reports.html and duplicated auth.js.
 * Now uses apiFetch() + authHeaders() from auth.js for all API calls.
 *
 * Features:
 *  - Month navigation (‹ / ›) — no year/month inputs needed
 *  - Summary stat cards
 *  - Leaderboard table with progress bars and drill-down
 *  - Teacher detail modal (per-duty breakdown)
 *  - CSV export via Blob (respects JWT auth header)
 *  - Rebuild cache
 *  - Full i18n via I18N from i18n.js
 */

/* ─── State ───────────────────────────────────────────────────────────────── */
let _reportYear  = new Date().getFullYear();
let _reportMonth = new Date().getMonth() + 1; // 1-indexed
let _reportData  = null;
let _maxPoints   = 1;

/* ─── Month names ─────────────────────────────────────────────────────────── */
const MONTHS_EN = [
  'January','February','March','April','May','June',
  'July','August','September','October','November','December',
];
const MONTHS_AR = [
  'يناير','فبراير','مارس','أبريل','مايو','يونيو',
  'يوليو','أغسطس','سبتمبر','أكتوبر','نوفمبر','ديسمبر',
];

function monthName(year, month) {
  const names = I18N.getLang() === 'ar' ? MONTHS_AR : MONTHS_EN;
  return `${names[month - 1]} ${year}`;
}

function updateMonthLabel() {
  const el = document.getElementById('monthLabel');
  if (el) el.textContent = monthName(_reportYear, _reportMonth);
}

function changeMonth(delta) {
  _reportMonth += delta;
  if (_reportMonth < 1)  { _reportMonth = 12; _reportYear--; }
  if (_reportMonth > 12) { _reportMonth = 1;  _reportYear++; }
  updateMonthLabel();
  loadReport();
}

/* ─── Toast ──────────────────────────────────────────────────────────────── */
function showToast(msg, type = 'success') {
  const c = document.getElementById('toastContainer');
  if (!c) return;
  const t = document.createElement('div');
  t.className = `toast toast-${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

/* ─── Escape HTML ─────────────────────────────────────────────────────────── */
function escHtml(str) {
  return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ─── Show / hide helpers ─────────────────────────────────────────────────── */
function showEl(id, display = 'block') {
  const el = document.getElementById(id);
  if (el) el.style.display = display;
}
function hideEl(id) {
  const el = document.getElementById(id);
  if (el) el.style.display = 'none';
}

/* ─── Load report ─────────────────────────────────────────────────────────── */
async function loadReport() {
  // Reset display
  hideEl('reportContainer');
  hideEl('summaryCards');
  hideEl('noDataMsg');
  showEl('reportLoading');

  try {
    const res = await apiFetch(
      `/admin/reports/monthly-points?year=${_reportYear}&month=${_reportMonth}`
    );

    if (!res || !res.ok) {
      showToast(I18N.t('error_generic'), 'error');
      hideEl('reportLoading');
      showEl('noDataMsg');
      return;
    }

    const data = await res.json();
    _reportData = data;

    hideEl('reportLoading');

    if (!data.teachers || data.teachers.length === 0) {
      showEl('noDataMsg');
      return;
    }

    _maxPoints = Math.max(...data.teachers.map(t => t.total_points), 1);

    renderSummaryCards(data);
    renderTable(data.teachers);

    showEl('summaryCards', 'grid');
    showEl('reportContainer');
  } catch (err) {
    console.error('loadReport failed:', err);
    showToast(I18N.t('error_generic'), 'error');
    hideEl('reportLoading');
    showEl('noDataMsg');
  }
}

/* ─── Summary cards ───────────────────────────────────────────────────────── */
function renderSummaryCards(data) {
  const total = data.teachers.reduce((s, t) => s + t.total_points, 0);
  const avg   = data.teachers.length ? Math.round(total / data.teachers.length) : 0;

  const set = (id, val) => {
    const el = document.getElementById(id);
    if (el) el.textContent = val;
  };
  set('totalTeachers',      data.total_teachers);
  set('totalConfirmations', data.total_confirmations);
  set('totalPoints',        total);
  set('avgPoints',          avg);
}

/* ─── Leaderboard table ───────────────────────────────────────────────────── */
function renderTable(teachers) {
  const tbody = document.getElementById('reportBody');
  if (!tbody) return;
  tbody.innerHTML = '';

  teachers.forEach((t, idx) => {
    const rank      = idx + 1;
    const rankClass = rank === 1 ? 'rank-1' : rank === 2 ? 'rank-2' : rank === 3 ? 'rank-3' : '';
    const barPct    = _maxPoints > 0 ? Math.round((t.total_points / _maxPoints) * 100) : 0;

    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><span class="rank-badge ${rankClass}">${rank}</span></td>
      <td><strong>${escHtml(t.teacher_name)}</strong></td>
      <td>
        <strong style="font-size:1.05rem;color:var(--primary)">${t.total_points}</strong>
        <span style="font-size:0.75rem;color:var(--text-muted);margin-inline-start:3px">pts</span>
      </td>
      <td>${t.confirmations}</td>
      <td><span class="pill pill-green">${t.on_time}</span></td>
      <td><span class="pill pill-yellow">${t.late}</span></td>
      <td><span class="pill pill-gray">${t.no_points}</span></td>
      <td>
        <div class="points-bar-wrap">
          <div class="points-bar">
            <div class="points-bar-fill" style="width:${barPct}%"></div>
          </div>
          <div class="points-bar-pct">${barPct}%</div>
        </div>
      </td>
      <td>
        <button class="btn btn-secondary btn-sm"
                onclick="openDetail(${t.teacher_id},'${escHtml(t.teacher_name).replace(/'/g,'&#39;')}')"
                data-i18n="details">${I18N.t('details')}</button>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

/* ─── Detail modal ────────────────────────────────────────────────────────── */
async function openDetail(teacherId, teacherName) {
  const modal       = document.getElementById('detailModal');
  const titleEl     = document.getElementById('modalTitle');
  const summaryEl   = document.getElementById('modalSummary');
  const tbody       = document.getElementById('detailBody');
  const noDetailMsg = document.getElementById('noDetailMsg');

  if (!modal) return;
  modal.classList.remove('hidden');

  if (titleEl) titleEl.textContent = teacherName;
  if (summaryEl) summaryEl.textContent = '';
  if (noDetailMsg) noDetailMsg.style.display = 'none';
  if (tbody) tbody.innerHTML = `
    <tr><td colspan="6" style="text-align:center;padding:20px">
      <div class="spinner" style="margin:0 auto;width:24px;height:24px;border-width:2px"></div>
    </td></tr>`;

  try {
    const res = await apiFetch(
      `/admin/reports/monthly-points/${teacherId}?year=${_reportYear}&month=${_reportMonth}`
    );

    if (!res || !res.ok) {
      showToast(I18N.t('error_generic'), 'error');
      closeModal();
      return;
    }

    const data = await res.json();
    const isAr = I18N.getLang() === 'ar';

    if (summaryEl) {
      summaryEl.textContent =
        `${I18N.t('total_points')}: ${data.total_points} · ${I18N.t('confirmations')}: ${data.duties?.length ?? 0}`;
    }

    if (!tbody) return;
    tbody.innerHTML = '';

    if (!data.duties?.length) {
      if (noDetailMsg) noDetailMsg.style.display = 'block';
      return;
    }

    data.duties.forEach(d => {
      const locName   = isAr ? d.location_name_ar : d.location_name_en;
      const shiftName = isAr ? d.shift_name_ar    : d.shift_name_en;
      const ptClass   = d.points_earned === 2
        ? 'pill-green' : d.points_earned === 1 ? 'pill-yellow' : 'pill-gray';
      const confirmedTime = (d.confirmed_at_muscat ?? '').slice(11, 19) || '—';

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${escHtml(d.date)}</td>
        <td>${escHtml(shiftName ?? '—')}</td>
        <td>${escHtml(locName ?? '—')}</td>
        <td>${(d.shift_start ?? '').slice(0, 5) || '—'}</td>
        <td>${confirmedTime}</td>
        <td><span class="pill ${ptClass}">${d.points_earned} pt</span></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error('openDetail failed:', err);
    showToast(I18N.t('error_generic'), 'error');
    closeModal();
  }
}

function closeModal() {
  const modal = document.getElementById('detailModal');
  if (modal) modal.classList.add('hidden');
}

/* ─── Export CSV ──────────────────────────────────────────────────────────── */
async function exportCSV() {
  const btn = document.getElementById('exportBtn');
  if (btn) btn.disabled = true;

  try {
    const res = await fetch(
      `${window.API_BASE}/admin/reports/monthly-points/export/csv?year=${_reportYear}&month=${_reportMonth}`,
      { headers: authHeaders() }
    );

    if (!res.ok) { showToast(I18N.t('error_generic'), 'error'); return; }

    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `firduty_points_${_reportYear}_${String(_reportMonth).padStart(2, '0')}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    showToast('CSV downloaded', 'success');
  } catch (err) {
    console.error('exportCSV failed:', err);
    showToast(I18N.t('error_generic'), 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ─── Rebuild cache ───────────────────────────────────────────────────────── */
async function rebuildCache() {
  const btn = document.getElementById('rebuildBtn');
  if (btn) { btn.disabled = true; }

  try {
    const res = await apiFetch(
      `/admin/reports/monthly-points/rebuild?year=${_reportYear}&month=${_reportMonth}`,
      { method: 'POST' }
    );

    if (res?.ok) {
      showToast(I18N.t('success_saved'), 'success');
      await loadReport();
    } else {
      showToast(I18N.t('error_generic'), 'error');
    }
  } catch (err) {
    console.error('rebuildCache failed:', err);
    showToast(I18N.t('error_generic'), 'error');
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ─── Close modal on overlay click or Escape ──────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  const modal = document.getElementById('detailModal');
  if (modal) {
    modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });
  }
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});

/* ─── Auto-init ───────────────────────────────────────────────────────────── */
async function initReports() {
  await I18N.load(localStorage.getItem('firduty_lang') || 'en');
  updateMonthLabel();
  await loadReport();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initReports);
} else {
  initReports();
}

document.addEventListener('DOMContentLoaded', async () => {
  await I18N.init();
  guardPage();
  await loadShifts();
});
