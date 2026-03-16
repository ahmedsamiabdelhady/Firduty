/**
 * teachers.js — Teachers management for Firduty Admin UI
 *
 * Features:
 *   - Pending / All tabs
 *   - Search in current tab
 *   - Approve single pending teacher
 *   - Approve all pending teachers
 *   - Add teacher modal
 *   - Inline edit rows
 *   - Remove teacher confirmation modal
 *   - Summary cards
 */

let currentTab = 'pending';
let pendingTeachers = [];
let allTeachers = [];
let filteredPendingTeachers = [];
let filteredAllTeachers = [];
let teacherToRemove = null;
let editingTeacherId = null;

function byId(id) {
  return document.getElementById(id);
}

function currentLang() {
  try {
    return typeof I18N !== 'undefined' && typeof I18N.getLang === 'function'
      ? I18N.getLang()
      : (localStorage.getItem('firduty_lang') || 'ar');
  } catch (_) {
    return 'ar';
  }
}

function isArabic() {
  return currentLang() === 'ar';
}

function t(en, ar) {
  return isArabic() ? ar : en;
}

function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function clearAlert() {
  const el = byId('alertMsg');
  if (!el) return;
  el.style.display = 'none';
  el.textContent = '';
  el.className = 'alert';
}

function showAlert(msg, type = 'success') {
  const el = byId('alertMsg');
  if (!el) return;
  el.className = `alert alert-${type}`;
  el.textContent = msg;
  el.style.display = '';

  window.clearTimeout(showAlert._timer);
  showAlert._timer = window.setTimeout(() => {
    el.style.display = 'none';
  }, 4000);
}

function setLoading(loading) {
  const pendingLoading = byId('pendingLoading');
  const allLoading = byId('allLoading');
  const pendingTableWrap = byId('pendingTableWrap');
  const allTableWrap = byId('allTableWrap');

  if (pendingLoading) pendingLoading.style.display = loading ? '' : 'none';
  if (allLoading) allLoading.style.display = loading ? '' : 'none';
  if (pendingTableWrap) pendingTableWrap.style.display = loading ? 'none' : '';
  if (allTableWrap) allTableWrap.style.display = loading ? 'none' : '';
}

function currentDataset() {
  return currentTab === 'pending' ? pendingTeachers : allTeachers;
}

function updateSummaryCards() {
  const pendingCount = pendingTeachers.length;
  const approvedCount = allTeachers.filter((item) => item.status === 'approved').length;
  const totalCount = allTeachers.length;

  if (byId('summaryPendingValue')) byId('summaryPendingValue').textContent = String(pendingCount);
  if (byId('summaryApprovedValue')) byId('summaryApprovedValue').textContent = String(approvedCount);
  if (byId('summaryTotalValue')) byId('summaryTotalValue').textContent = String(totalCount);
}

function updateCounts() {
  if (byId('pendingCount')) byId('pendingCount').textContent = String(pendingTeachers.length);
  if (byId('allCount')) byId('allCount').textContent = String(allTeachers.length);

  const approveAllBtn = byId('approveAllBtn');
  if (approveAllBtn) approveAllBtn.disabled = pendingTeachers.length === 0;
}

function showTab(tab) {
  currentTab = tab;

  const pendingSection = byId('pendingSection');
  const allSection = byId('allSection');
  const tabPending = byId('tabPending');
  const tabAll = byId('tabAll');
  const approveAllBtn = byId('approveAllBtn');
  const searchInput = byId('teachersSearch');

  editingTeacherId = null;

  if (pendingSection) pendingSection.style.display = tab === 'pending' ? '' : 'none';
  if (allSection) allSection.style.display = tab === 'all' ? '' : 'none';

  if (tabPending) tabPending.classList.toggle('active', tab === 'pending');
  if (tabAll) tabAll.classList.toggle('active', tab === 'all');

  if (approveAllBtn) approveAllBtn.style.display = tab === 'pending' ? '' : 'none';
  if (searchInput) {
    searchInput.value = '';
    searchInput.placeholder = tab === 'pending'
      ? t('Search pending teachers...', 'ابحث في المعلمين قيد الانتظار...')
      : t('Search teachers...', 'ابحث في المعلمين...');
  }

  applyStaticTranslations();
  applySearch();
}

async function loadAll() {
  clearAlert();
  setLoading(true);

  try {
    const [pendingRes, allRes] = await Promise.all([
      apiFetch('/teachers/pending'),
      apiFetch('/teachers/all'),
    ]);

    if (!pendingRes.ok || !allRes.ok) {
      showAlert(t('Failed to load teachers.', 'تعذر تحميل المعلمين.'), 'danger');
      return;
    }

    pendingTeachers = await pendingRes.json();
    allTeachers = await allRes.json();

    if (editingTeacherId && !allTeachers.some((item) => Number(item.id) === Number(editingTeacherId))) {
      editingTeacherId = null;
    }

    updateSummaryCards();
    updateCounts();
    applySearch();
  } catch (err) {
    console.error('loadAll failed:', err);
    showAlert(t('Something went wrong while loading teachers.', 'حدث خطأ أثناء تحميل المعلمين.'), 'danger');
  } finally {
    setLoading(false);
  }
}

function formatDate(value) {
  if (!value) return '—';
  try {
    const locale = isArabic() ? 'ar-OM' : 'en-GB';
    return new Date(value).toLocaleDateString(locale);
  } catch (_) {
    return '—';
  }
}

function languageLabel(value) {
  return value === 'en' ? t('English', 'الإنجليزية') : t('Arabic', 'العربية');
}

function statusBadge(value) {
  return value === 'pending'
    ? `<span class="badge badge-pending">${escHtml(t('Pending', 'قيد الانتظار'))}</span>`
    : `<span class="badge badge-approved">${escHtml(t('Approved', 'معتمد'))}</span>`;
}

function emptyState(text) {
  return `
    <div class="empty-state">
      <div class="empty-icon">👥</div>
      <p>${escHtml(text)}</p>
    </div>
  `;
}

function renderDisplayRow(teacher, index, showApprove) {
  return `
    <tr>
      <td>${index + 1}</td>
      <td><span class="teacher-name">${escHtml(teacher.name || '—')}</span></td>
      <td><span class="teacher-email">${escHtml(teacher.email || '—')}</span></td>
      <td>${statusBadge(teacher.status)}</td>
      <td><span class="lang-chip">${escHtml(languageLabel(teacher.preferred_language))}</span></td>
      <td>${formatDate(teacher.created_at)}</td>
      <td>
        <div class="teacher-actions">
          ${showApprove ? `
            <button class="btn btn-success btn-sm" type="button" onclick="approveTeacher(${Number(teacher.id)})">
              ${escHtml(t('Approve', 'اعتماد'))}
            </button>
          ` : ''}
          <button class="btn btn-secondary btn-sm" type="button" onclick="startInlineEdit(${Number(teacher.id)})">
            ${escHtml(t('Edit', 'تعديل'))}
          </button>
          <button class="btn btn-danger btn-sm" type="button" onclick="openRemoveTeacherModal(${Number(teacher.id)}, ${JSON.stringify(String(teacher.name || '')).replace(/</g, '\\u003c')})">
            ${escHtml(t('Remove', 'حذف'))}
          </button>
        </div>
      </td>
    </tr>
  `;
}

function renderInlineEditRow(teacher, index, showApprove) {
  return `
    <tr class="teacher-row-editing" id="teacher-row-${Number(teacher.id)}">
      <td>${index + 1}</td>
      <td>
        <input class="inline-input" id="edit-name-${Number(teacher.id)}" type="text" maxlength="200" value="${escHtml(teacher.name || '')}" placeholder="${escHtml(t('Teacher name', 'اسم المعلم'))}">
      </td>
      <td>
        <input class="inline-input" id="edit-email-${Number(teacher.id)}" type="email" maxlength="255" value="${escHtml(teacher.email || '')}" placeholder="${escHtml(t('Email address', 'البريد الإلكتروني'))}">
      </td>
      <td>
        <select class="inline-select" id="edit-status-${Number(teacher.id)}">
          <option value="approved" ${teacher.status === 'approved' ? 'selected' : ''}>${escHtml(t('Approved', 'معتمد'))}</option>
          <option value="pending" ${teacher.status === 'pending' ? 'selected' : ''}>${escHtml(t('Pending', 'قيد الانتظار'))}</option>
        </select>
      </td>
      <td>
        <select class="inline-select" id="edit-language-${Number(teacher.id)}">
          <option value="ar" ${teacher.preferred_language !== 'en' ? 'selected' : ''}>${escHtml(t('Arabic', 'العربية'))}</option>
          <option value="en" ${teacher.preferred_language === 'en' ? 'selected' : ''}>${escHtml(t('English', 'الإنجليزية'))}</option>
        </select>
      </td>
      <td>${formatDate(teacher.created_at)}</td>
      <td>
        <div class="inline-actions">
          <button class="btn btn-primary btn-sm" type="button" onclick="saveInlineEdit(${Number(teacher.id)})">
            ${escHtml(t('Save', 'حفظ'))}
          </button>
          <button class="btn btn-secondary btn-sm" type="button" onclick="cancelInlineEdit()">
            ${escHtml(t('Cancel', 'إلغاء'))}
          </button>
          ${showApprove ? `
            <button class="btn btn-success btn-sm" type="button" onclick="approveTeacher(${Number(teacher.id)})">
              ${escHtml(t('Approve', 'اعتماد'))}
            </button>
          ` : ''}
        </div>
      </td>
    </tr>
  `;
}

function buildTable(teachers, showApprove) {
  if (!Array.isArray(teachers) || teachers.length === 0) {
    return emptyState(
      showApprove
        ? t('No pending teachers right now.', 'لا يوجد معلمون قيد الانتظار حالياً.')
        : t('No teachers found.', 'لا يوجد معلمون.')
    );
  }

  const rows = teachers.map((teacher, index) => {
    const isEditing = Number(editingTeacherId) === Number(teacher.id);
    return isEditing
      ? renderInlineEditRow(teacher, index, showApprove)
      : renderDisplayRow(teacher, index, showApprove);
  }).join('');

  return `
    <div class="table-wrap">
      <table class="teacher-table">
        <thead>
          <tr>
            <th>#</th>
            <th>${escHtml(t('Name', 'الاسم'))}</th>
            <th>${escHtml(t('Email', 'البريد الإلكتروني'))}</th>
            <th>${escHtml(t('Status', 'الحالة'))}</th>
            <th>${escHtml(t('Language', 'اللغة'))}</th>
            <th>${escHtml(t('Date', 'التاريخ'))}</th>
            <th>${escHtml(t('Actions', 'الإجراءات'))}</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
  `;
}

function renderTables() {
  const pendingWrap = byId('pendingTableWrap');
  const allWrap = byId('allTableWrap');
  if (pendingWrap) pendingWrap.innerHTML = buildTable(filteredPendingTeachers, true);
  if (allWrap) allWrap.innerHTML = buildTable(filteredAllTeachers, false);
}

function applySearch() {
  const query = String(byId('teachersSearch')?.value || '').trim().toLowerCase();

  const filterList = (items) => {
    if (!query) return [...items];
    return items.filter((item) => {
      const haystack = [
        item.name,
        item.email,
        item.status,
        item.preferred_language,
      ].map((value) => String(value || '').toLowerCase()).join(' ');
      return haystack.includes(query);
    });
  };

  filteredPendingTeachers = filterList(pendingTeachers);
  filteredAllTeachers = filterList(allTeachers);
  renderTables();
}

function startInlineEdit(id) {
  editingTeacherId = Number(id);
  renderTables();
}

function cancelInlineEdit() {
  editingTeacherId = null;
  renderTables();
}

function getInlineValue(id, field) {
  const el = byId(`edit-${field}-${Number(id)}`);
  return el ? String(el.value || '').trim() : '';
}

async function saveInlineEdit(id) {
  const teacherId = Number(id);
  const rowEl = byId(`teacher-row-${teacherId}`);
  const payload = {
    name: getInlineValue(teacherId, 'name'),
    email: getInlineValue(teacherId, 'email') || null,
    status: getInlineValue(teacherId, 'status') || 'approved',
    preferred_language: getInlineValue(teacherId, 'language') || 'ar',
  };

  if (!payload.name) {
    showAlert(t('Teacher name is required.', 'اسم المعلم مطلوب.'), 'danger');
    return;
  }

  if (rowEl) rowEl.classList.add('row-saving');

  try {
    const res = await apiFetch(`/teachers/${teacherId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const message = await extractErrorMessage(res);
      showAlert(message || t('Failed to update teacher.', 'تعذر تحديث بيانات المعلم.'), 'danger');
      return;
    }

    editingTeacherId = null;
    showAlert(t('Teacher updated successfully.', 'تم تحديث بيانات المعلم بنجاح.'), 'success');
    await loadAll();
  } catch (err) {
    console.error('saveInlineEdit failed:', err);
    showAlert(t('Something went wrong.', 'حدث خطأ غير متوقع.'), 'danger');
  } finally {
    if (rowEl) rowEl.classList.remove('row-saving');
  }
}

async function approveTeacher(id) {
  try {
    const res = await apiFetch(`/teachers/${Number(id)}/approve`, { method: 'POST' });
    if (!res.ok) {
      showAlert(t('Failed to approve teacher.', 'تعذر اعتماد المعلم.'), 'danger');
      return;
    }

    editingTeacherId = null;
    showAlert(t('Teacher approved successfully.', 'تم اعتماد المعلم بنجاح.'), 'success');
    await loadAll();
  } catch (err) {
    console.error('approveTeacher failed:', err);
    showAlert(t('Something went wrong.', 'حدث خطأ غير متوقع.'), 'danger');
  }
}

async function approveAll() {
  const btn = byId('approveAllBtn');
  const originalText = btn?.textContent || '';

  try {
    if (btn) {
      btn.disabled = true;
      btn.textContent = t('Approving...', 'جارٍ الاعتماد...');
    }

    const res = await apiFetch('/teachers/approve-all', { method: 'POST' });
    if (!res.ok) {
      showAlert(t('Failed to approve all pending teachers.', 'تعذر اعتماد جميع المعلمين المعلقين.'), 'danger');
      return;
    }

    const data = await res.json();
    const count = Number(data?.approved_count || 0);

    showAlert(
      count > 0
        ? t(`Approved ${count} teacher(s).`, `تم اعتماد ${count} من المعلمين.`)
        : t('No pending teachers to approve.', 'لا يوجد معلمون معلقون للاعتماد.'),
      'success'
    );

    editingTeacherId = null;
    await loadAll();
  } catch (err) {
    console.error('approveAll failed:', err);
    showAlert(t('Something went wrong.', 'حدث خطأ غير متوقع.'), 'danger');
  } finally {
    if (btn) {
      btn.disabled = pendingTeachers.length === 0;
      btn.textContent = originalText || t('Approve All Pending', 'اعتماد جميع المعلقين');
    }
  }
}

function openAddTeacherModal() {
  editingTeacherId = null;
  hideTeacherFormError();
  if (byId('teacherForm')) byId('teacherForm').reset();
  if (byId('teacherLanguage')) byId('teacherLanguage').value = 'ar';
  if (byId('teacherStatus')) byId('teacherStatus').value = 'approved';
  byId('teacherModal')?.classList.add('open');
  applyStaticTranslations();
}

function closeTeacherModal() {
  hideTeacherFormError();
  byId('teacherModal')?.classList.remove('open');
}

function showTeacherFormError(message) {
  const el = byId('teacherFormError');
  if (!el) return;
  el.textContent = message;
  el.style.display = 'block';
}

function hideTeacherFormError() {
  const el = byId('teacherFormError');
  if (!el) return;
  el.textContent = '';
  el.style.display = 'none';
}

async function saveTeacher() {
  hideTeacherFormError();

  const payload = {
    name: String(byId('teacherName')?.value || '').trim(),
    email: String(byId('teacherEmail')?.value || '').trim() || null,
    preferred_language: String(byId('teacherLanguage')?.value || 'ar'),
    status: String(byId('teacherStatus')?.value || 'approved'),
    active: true,
  };

  if (!payload.name) {
    showTeacherFormError(t('Teacher name is required.', 'اسم المعلم مطلوب.'));
    return;
  }

  const saveBtn = byId('saveTeacherBtn');
  const originalText = saveBtn?.textContent || '';

  try {
    if (saveBtn) {
      saveBtn.disabled = true;
      saveBtn.textContent = t('Saving...', 'جارٍ الحفظ...');
    }

    const res = await apiFetch('/teachers/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const message = await extractErrorMessage(res);
      showTeacherFormError(message || t('Failed to add teacher.', 'تعذر إضافة المعلم.'));
      return;
    }

    closeTeacherModal();
    showAlert(t('Teacher added successfully.', 'تمت إضافة المعلم بنجاح.'), 'success');
    await loadAll();
    showTab('all');
  } catch (err) {
    console.error('saveTeacher failed:', err);
    showTeacherFormError(t('Something went wrong.', 'حدث خطأ غير متوقع.'));
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = originalText || t('Add Teacher', 'إضافة المعلم');
    }
  }
}

function openRemoveTeacherModal(id, name) {
  teacherToRemove = { id: Number(id), name: String(name || '') };
  if (byId('removeTeacherName')) byId('removeTeacherName').textContent = teacherToRemove.name || '—';
  byId('removeTeacherModal')?.classList.add('open');
}

function closeRemoveTeacherModal() {
  teacherToRemove = null;
  byId('removeTeacherModal')?.classList.remove('open');
}

async function confirmRemoveTeacher() {
  if (!teacherToRemove?.id) return;

  const btn = byId('confirmRemoveTeacherBtn');
  const originalText = btn?.textContent || '';

  try {
    if (btn) {
      btn.disabled = true;
      btn.textContent = t('Removing...', 'جارٍ الحذف...');
    }

    const res = await apiFetch(`/teachers/${teacherToRemove.id}`, { method: 'DELETE' });
    if (!res.ok) {
      showAlert(t('Failed to remove teacher.', 'تعذر حذف المعلم.'), 'danger');
      return;
    }

    editingTeacherId = null;
    closeRemoveTeacherModal();
    showAlert(t('Teacher removed successfully.', 'تم حذف المعلم بنجاح.'), 'success');
    await loadAll();
  } catch (err) {
    console.error('confirmRemoveTeacher failed:', err);
    showAlert(t('Something went wrong.', 'حدث خطأ غير متوقع.'), 'danger');
  } finally {
    if (btn) {
      btn.disabled = false;
      btn.textContent = originalText || t('Remove Teacher', 'حذف المعلم');
    }
  }
}

async function extractErrorMessage(res) {
  try {
    const data = await res.json();
    if (typeof data?.detail === 'string' && data.detail.trim()) return data.detail;
    if (typeof data?.message === 'string' && data.message.trim()) return data.message;
  } catch (_) {
    // ignore
  }
  if (res.status === 409) return t('This email is already registered.', 'هذا البريد الإلكتروني مسجل بالفعل.');
  if (res.status === 404) return t('Teacher not found.', 'المعلم غير موجود.');
  if (res.status === 400) return t('Please review the entered data.', 'يرجى مراجعة البيانات المدخلة.');
  return '';
}

function applyStaticTranslations() {
  const labels = {
    title: t('Teachers Management', 'إدارة المعلمين'),
    subtitle: t(
      'Review pending registrations, add teachers directly, edit rows inline, and remove inactive records.',
      'راجع طلبات التسجيل المعلقة، وأضف المعلمين مباشرة، وعدّل الصفوف مباشرة داخل الجدول، واحذف السجلات غير النشطة.'
    ),
    addTeacherBtn: t('+ Add New Teacher', '+ إضافة معلم جديد'),
    approveAllBtn: t('Approve All Pending', 'اعتماد جميع المعلقين'),
    refreshTeachersBtn: t('Refresh', 'تحديث'),
    summaryPendingLabel: t('Pending Teachers', 'المعلمون المعلقون'),
    summaryApprovedLabel: t('Approved Teachers', 'المعلمون المعتمدون'),
    summaryTotalLabel: t('Total Active Teachers', 'إجمالي المعلمين النشطين'),
    tabPendingLabel: t('Pending Approval', 'بانتظار الاعتماد'),
    tabAllLabel: t('All Teachers', 'كل المعلمين'),
    teachersSearch: currentTab === 'pending'
      ? t('Search pending teachers...', 'ابحث في المعلمين قيد الانتظار...')
      : t('Search teachers...', 'ابحث في المعلمين...'),
    inlineEditNote: t('Click Edit to modify any row directly inside the table.', 'اضغط تعديل لتغيير أي صف مباشرة داخل الجدول.'),
    teacherModalTitle: t('Add New Teacher', 'إضافة معلم جديد'),
    teacherModalSubtitle: t('Create a teacher directly from the admin panel.', 'أضف معلماً مباشرةً من لوحة التحكم.'),
    teacherNameLabel: t('Teacher Name', 'اسم المعلم'),
    teacherName: t('Enter teacher name', 'أدخل اسم المعلم'),
    teacherEmailLabel: t('Email', 'البريد الإلكتروني'),
    teacherEmail: t('Enter email address', 'أدخل البريد الإلكتروني'),
    teacherLanguageLabel: t('Preferred Language', 'اللغة المفضلة'),
    teacherStatusLabel: t('Account Status', 'حالة الحساب'),
    cancelTeacherBtn: t('Cancel', 'إلغاء'),
    saveTeacherBtn: t('Add Teacher', 'إضافة المعلم'),
    removeTeacherModalTitle: t('Remove Teacher', 'حذف معلم'),
    removeTeacherModalText: t('This action will hide the teacher from active teacher lists.', 'سيؤدي هذا الإجراء إلى إخفاء المعلم من قوائم المعلمين النشطين.'),
    removeTeacherWarning: t('Are you sure you want to remove this teacher?', 'هل أنت متأكد أنك تريد حذف هذا المعلم؟'),
    cancelRemoveTeacherBtn: t('Cancel', 'إلغاء'),
    confirmRemoveTeacherBtn: t('Remove Teacher', 'حذف المعلم'),
  };

  if (byId('teachersPageTitle')) byId('teachersPageTitle').textContent = labels.title;
  if (byId('teachersPageSubtitle')) byId('teachersPageSubtitle').textContent = labels.subtitle;
  if (byId('addTeacherBtn')) byId('addTeacherBtn').textContent = labels.addTeacherBtn;
  if (byId('approveAllBtn')) byId('approveAllBtn').textContent = labels.approveAllBtn;
  if (byId('refreshTeachersBtn')) byId('refreshTeachersBtn').textContent = labels.refreshTeachersBtn;
  if (byId('summaryPendingLabel')) byId('summaryPendingLabel').textContent = labels.summaryPendingLabel;
  if (byId('summaryApprovedLabel')) byId('summaryApprovedLabel').textContent = labels.summaryApprovedLabel;
  if (byId('summaryTotalLabel')) byId('summaryTotalLabel').textContent = labels.summaryTotalLabel;
  if (byId('tabPendingLabel')) byId('tabPendingLabel').textContent = labels.tabPendingLabel;
  if (byId('tabAllLabel')) byId('tabAllLabel').textContent = labels.tabAllLabel;
  if (byId('teachersSearch')) byId('teachersSearch').placeholder = labels.teachersSearch;
  if (byId('inlineEditNotePending')) byId('inlineEditNotePending').textContent = labels.inlineEditNote;
  if (byId('inlineEditNoteAll')) byId('inlineEditNoteAll').textContent = labels.inlineEditNote;
  if (byId('teacherModalTitle')) byId('teacherModalTitle').textContent = labels.teacherModalTitle;
  if (byId('teacherModalSubtitle')) byId('teacherModalSubtitle').textContent = labels.teacherModalSubtitle;
  if (byId('teacherNameLabel')) byId('teacherNameLabel').textContent = labels.teacherNameLabel;
  if (byId('teacherName')) byId('teacherName').placeholder = labels.teacherName;
  if (byId('teacherEmailLabel')) byId('teacherEmailLabel').textContent = labels.teacherEmailLabel;
  if (byId('teacherEmail')) byId('teacherEmail').placeholder = labels.teacherEmail;
  if (byId('teacherLanguageLabel')) byId('teacherLanguageLabel').textContent = labels.teacherLanguageLabel;
  if (byId('teacherStatusLabel')) byId('teacherStatusLabel').textContent = labels.teacherStatusLabel;
  if (byId('teacherLanguageOptionAr')) byId('teacherLanguageOptionAr').textContent = t('Arabic', 'العربية');
  if (byId('teacherLanguageOptionEn')) byId('teacherLanguageOptionEn').textContent = t('English', 'الإنجليزية');
  if (byId('teacherStatusOptionApproved')) byId('teacherStatusOptionApproved').textContent = t('Approved', 'معتمد');
  if (byId('teacherStatusOptionPending')) byId('teacherStatusOptionPending').textContent = t('Pending', 'قيد الانتظار');
  if (byId('cancelTeacherBtn')) byId('cancelTeacherBtn').textContent = labels.cancelTeacherBtn;
  if (byId('saveTeacherBtn')) byId('saveTeacherBtn').textContent = labels.saveTeacherBtn;
  if (byId('removeTeacherModalTitle')) byId('removeTeacherModalTitle').textContent = labels.removeTeacherModalTitle;
  if (byId('removeTeacherModalText')) byId('removeTeacherModalText').textContent = labels.removeTeacherModalText;
  if (byId('removeTeacherWarning')) byId('removeTeacherWarning').textContent = labels.removeTeacherWarning;
  if (byId('cancelRemoveTeacherBtn')) byId('cancelRemoveTeacherBtn').textContent = labels.cancelRemoveTeacherBtn;
  if (byId('confirmRemoveTeacherBtn')) byId('confirmRemoveTeacherBtn').textContent = labels.confirmRemoveTeacherBtn;
}

function bindEvents() {
  byId('tabPending')?.addEventListener('click', () => showTab('pending'));
  byId('tabAll')?.addEventListener('click', () => showTab('all'));
  byId('teachersSearch')?.addEventListener('input', applySearch);
  byId('refreshTeachersBtn')?.addEventListener('click', loadAll);
  byId('approveAllBtn')?.addEventListener('click', approveAll);
  byId('addTeacherBtn')?.addEventListener('click', openAddTeacherModal);
  byId('cancelTeacherBtn')?.addEventListener('click', closeTeacherModal);
  byId('saveTeacherBtn')?.addEventListener('click', saveTeacher);
  byId('cancelRemoveTeacherBtn')?.addEventListener('click', closeRemoveTeacherModal);
  byId('confirmRemoveTeacherBtn')?.addEventListener('click', confirmRemoveTeacher);

  byId('teacherForm')?.addEventListener('submit', (e) => {
    e.preventDefault();
    saveTeacher();
  });

  byId('teacherModal')?.addEventListener('click', (e) => {
    if (e.target?.id === 'teacherModal') closeTeacherModal();
  });

  byId('removeTeacherModal')?.addEventListener('click', (e) => {
    if (e.target?.id === 'removeTeacherModal') closeRemoveTeacherModal();
  });

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (byId('teacherModal')?.classList.contains('open')) closeTeacherModal();
    if (byId('removeTeacherModal')?.classList.contains('open')) closeRemoveTeacherModal();
    if (editingTeacherId) cancelInlineEdit();
  });
}

async function initTeachersPage() {
  try {
    applyStaticTranslations();
    bindEvents();
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
