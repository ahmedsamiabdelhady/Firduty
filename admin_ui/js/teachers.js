let currentTab = 'pending';
let pendingTeachersCache = [];
let allTeachersCache = [];
let searchTerm = '';
let editingTeacherId = null;
let deleteQueue = [];
const selectedTeacherIds = new Set();

function byId(id){ return document.getElementById(id); }
function escHtml(str){ return String(str ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function normalize(str){ return String(str || '').trim().toLowerCase(); }
function formatDate(value){ if(!value) return '—'; try{ return new Date(value).toLocaleDateString(document.documentElement.lang==='ar' ? 'ar-OM':'en-GB'); }catch{return '—';} }

function showAlert(msg, type='success'){
  const el = byId('alertMsg'); if(!el) return;
  el.className = `alert alert-${type}`; el.textContent = msg; el.style.display='';
  clearTimeout(showAlert._timer); showAlert._timer = setTimeout(()=>{ el.style.display='none'; }, 3600);
}
function clearAlert(){ const el = byId('alertMsg'); if(el) el.style.display='none'; }

function statusBadge(status){
  return status === 'pending'
    ? '<span class="badge badge-pending">Pending</span>'
    : '<span class="badge badge-approved">Approved</span>';
}
function languageChip(lang){ return `<span class="lang-chip">${lang === 'ar' ? 'Arabic' : 'English'}</span>`; }

function matchesSearch(teacher){
  if(!searchTerm) return true;
  return [teacher.name, teacher.email, teacher.status, teacher.preferred_language].map(normalize).join(' ').includes(searchTerm);
}
function getFilteredPending(){ return pendingTeachersCache.filter(t => t.active !== false).filter(matchesSearch); }
function getFilteredAll(){ return allTeachersCache.filter(t => t.active !== false).filter(matchesSearch); }
function getCurrentVisibleTeachers(){ return currentTab === 'pending' ? getFilteredPending() : getFilteredAll(); }

function updateStats(){
  const pending = pendingTeachersCache.filter(t => t.active !== false).length;
  const allActive = allTeachersCache.filter(t => t.active !== false);
  const approved = allActive.filter(t => t.status === 'approved').length;
  if(byId('summaryPendingValue')) byId('summaryPendingValue').textContent = pending;
  if(byId('summaryApprovedValue')) byId('summaryApprovedValue').textContent = approved;
  if(byId('summaryTotalValue')) byId('summaryTotalValue').textContent = allActive.length;
  if(byId('pendingCount')) byId('pendingCount').textContent = pending;
  if(byId('allCount')) byId('allCount').textContent = allActive.length;
  if(byId('approveAllBtn')) byId('approveAllBtn').disabled = pending === 0;
}

function syncBulkbar(){
  const bulkbar = byId('teachersBulkbar'); const selectedCount = byId('selectedCount');
  if(!bulkbar || !selectedCount) return;
  const visible = new Set(getCurrentVisibleTeachers().map(t => t.id));
  let count = 0; selectedTeacherIds.forEach(id => { if(visible.has(id)) count += 1; });
  selectedCount.textContent = count;
  bulkbar.style.display = currentTab === 'all' && count > 0 ? '' : 'none';
}
function clearSelection(){ selectedTeacherIds.clear(); syncBulkbar(); renderCurrentTab(); }
function toggleTeacherSelection(id, checked){ checked ? selectedTeacherIds.add(id) : selectedTeacherIds.delete(id); syncBulkbar(); }
function toggleSelectAll(checked){ getCurrentVisibleTeachers().forEach(t => checked ? selectedTeacherIds.add(t.id) : selectedTeacherIds.delete(t.id)); syncBulkbar(); renderCurrentTab(); }

function setTab(tab){
  currentTab = tab;
  byId('pendingSection').style.display = tab === 'pending' ? '' : 'none';
  byId('allSection').style.display = tab === 'all' ? '' : 'none';
  byId('tabPending').classList.toggle('active', tab === 'pending');
  byId('tabAll').classList.toggle('active', tab === 'all');
  byId('tabPending').setAttribute('aria-selected', tab === 'pending' ? 'true' : 'false');
  byId('tabAll').setAttribute('aria-selected', tab === 'all' ? 'true' : 'false');
  syncBulkbar();
  renderCurrentTab();
}

function openAddTeacherModal(){
  const m = byId('teacherModalBackdrop'); if(!m) return;
  byId('teacherFormError').style.display = 'none';
  byId('teacherNameInput').value=''; byId('teacherEmailInput').value=''; byId('teacherLanguageInput').value='ar'; byId('teacherStatusInput').value='approved';
  m.classList.add('open'); m.setAttribute('aria-hidden','false');
  setTimeout(() => byId('teacherNameInput')?.focus(), 30);
}
function closeAddTeacherModal(){ const m = byId('teacherModalBackdrop'); if(m){ m.classList.remove('open'); m.setAttribute('aria-hidden','true'); } }

function openDeleteModal(items){
  deleteQueue = items.slice();
  byId('deleteTeacherName').textContent = items.length === 1 ? (items[0].name || 'Teacher') : `${items.length} teachers selected`;
  byId('deleteTeacherEmail').textContent = items.length === 1 ? (items[0].email || 'No email') : 'The selected teachers will be deactivated.';
  byId('deleteTeacherSubtitle').textContent = items.length === 1
    ? 'This will deactivate the selected teacher and remove them from active lists.'
    : 'This will deactivate the selected teacher records and remove them from active lists.';
  byId('deleteTeacherError').style.display='none';
  const m = byId('deleteTeacherBackdrop'); m.classList.add('open'); m.setAttribute('aria-hidden','false');
}
function closeDeleteModal(){ deleteQueue = []; const m = byId('deleteTeacherBackdrop'); if(m){ m.classList.remove('open'); m.setAttribute('aria-hidden','true'); } }
function confirmBulkDelete(){
  const items = getFilteredAll().filter(t => selectedTeacherIds.has(t.id));
  if(!items.length) return;
  openDeleteModal(items);
}

async function loadAll(){ clearAlert(); await Promise.all([loadPending(), loadAllTeachers()]); updateStats(); renderCurrentTab(); }
async function loadPending(){
  const l = byId('pendingLoading'); if(l) l.style.display='';
  try{ const res = await apiFetch('/teachers/pending'); if(!res.ok) throw new Error('pending'); pendingTeachersCache = await res.json(); }
  catch(err){ console.error(err); showAlert('Failed to load pending teachers.','danger'); }
  finally{ if(l) l.style.display='none'; }
}
async function loadAllTeachers(){
  const l = byId('allLoading'); if(l) l.style.display='';
  try{ const res = await apiFetch('/teachers/all'); if(!res.ok) throw new Error('all'); allTeachersCache = await res.json(); }
  catch(err){ console.error(err); showAlert('Failed to load teachers.','danger'); }
  finally{ if(l) l.style.display='none'; }
}

async function approveTeacher(id){
  const btn = byId(`btn-approve-${id}`); if(btn){ btn.disabled=true; btn.textContent='...'; }
  try{ const res = await apiFetch(`/teachers/${id}/approve`, {method:'POST'}); if(!res.ok) throw new Error('approve'); showAlert('Teacher approved successfully.'); await loadAll(); }
  catch(err){ console.error(err); showAlert('Could not approve this teacher.','danger'); if(btn){ btn.disabled=false; btn.textContent='Approve'; } }
}
async function approveAll(){
  const btn = byId('approveAllBtn'); if(btn) btn.disabled=true;
  try{ const res = await apiFetch('/teachers/approve-all', {method:'POST'}); if(!res.ok) throw new Error('approve-all'); const data = await res.json(); showAlert(data.approved_count ? `Approved ${data.approved_count} teachers.` : 'No pending teachers found.'); await loadAll(); }
  catch(err){ console.error(err); showAlert('Could not approve all pending teachers.','danger'); }
  finally{ if(btn) btn.disabled=false; }
}
async function createTeacher(){
  const name = byId('teacherNameInput').value.trim();
  const email = byId('teacherEmailInput').value.trim();
  const preferred_language = byId('teacherLanguageInput').value || 'ar';
  const status = byId('teacherStatusInput').value || 'approved';
  const error = byId('teacherFormError');
  const btn = byId('saveTeacherModalBtn');
  error.style.display='none';
  if(!name){ error.textContent='Teacher name is required.'; error.style.display='block'; return; }
  btn.disabled=true; btn.textContent='Saving...';
  try{
    const res = await apiFetch('/teachers/', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ name, email: email || null, preferred_language, status, active:true }) });
    if(!res.ok){ let msg='Failed to create teacher.'; try{ const data=await res.json(); msg=data.detail || msg; }catch{} throw new Error(msg); }
    closeAddTeacherModal(); showAlert('Teacher created successfully.'); await loadAll();
  }catch(err){ error.textContent=err.message || 'Failed to create teacher.'; error.style.display='block'; }
  finally{ btn.disabled=false; btn.textContent='Save Teacher'; }
}
function startInlineEdit(id){ editingTeacherId = id; renderCurrentTab(); }
function cancelInlineEdit(){ editingTeacherId = null; renderCurrentTab(); }
async function saveInlineEdit(id){
  const name = byId(`edit-name-${id}`)?.value.trim();
  const preferred_language = byId(`edit-lang-${id}`)?.value || 'ar';
  const status = byId(`edit-status-${id}`)?.value || 'approved';
  const payload = { name, preferred_language, status };
  if(!name){ showAlert('Teacher name is required.','danger'); return; }
  const btn = byId(`btn-save-${id}`); if(btn){ btn.disabled=true; btn.textContent='Saving...'; }
  try{
    const res = await apiFetch(`/teachers/${id}`, { method:'PUT', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    if(!res.ok){ let msg='Failed to update teacher.'; try{ const data=await res.json(); msg=data.detail || msg; }catch{} throw new Error(msg); }
    editingTeacherId = null; showAlert('Teacher updated successfully.'); await loadAll();
  }catch(err){ console.error(err); showAlert(err.message || 'Failed to update teacher.','danger'); if(btn){ btn.disabled=false; btn.textContent='Save'; } }
}
function confirmDeleteTeacher(id){
  const teacher = allTeachersCache.find(t => t.id === id) || pendingTeachersCache.find(t => t.id === id);
  if(teacher) openDeleteModal([teacher]);
}
async function deleteQueuedTeachers(){
  const btn = byId('confirmDeleteBtn'); const error = byId('deleteTeacherError'); error.style.display='none';
  if(!deleteQueue.length) return;
  btn.disabled=true; btn.textContent='Removing...';
  try{
    for(const item of deleteQueue){
      const res = await apiFetch(`/teachers/${item.id}`, { method:'DELETE' });
      if(!res.ok){ let msg='Failed to remove teacher.'; try{ const data=await res.json(); msg=data.detail || msg; }catch{} throw new Error(msg); }
      selectedTeacherIds.delete(item.id);
    }
    closeDeleteModal(); showAlert(deleteQueue.length === 1 ? 'Teacher removed.' : 'Selected teachers removed.','success');
    deleteQueue = []; await loadAll();
  }catch(err){ error.textContent = err.message || 'Failed to remove teacher.'; error.style.display='block'; }
  finally{ btn.disabled=false; btn.textContent='Remove'; }
}

function exportTeachersCSV(){
  const teachers = getCurrentVisibleTeachers();
  const header = ['id','name','email','status','language','created_at'];
  const rows = teachers.map(t => [t.id, t.name || '', t.email || '', t.status || '', t.preferred_language || '', t.created_at || '']);
  const csv = [header, ...rows].map(r => r.map(v => `"${String(v).replace(/"/g,'""')}"`).join(',')).join('\n');
  const blob = new Blob([csv], {type:'text/csv;charset=utf-8;'});
  const url = URL.createObjectURL(blob); const a = document.createElement('a'); a.href=url; a.download=`teachers-${currentTab}.csv`; document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
}

function buildDesktopTable(teachers, pendingTab=false){
  const allSelected = teachers.length > 0 && teachers.every(t => selectedTeacherIds.has(t.id));
  const rows = teachers.map((t, idx) => {
    const selected = selectedTeacherIds.has(t.id);
    const editing = editingTeacherId === t.id;
    if(editing){
      return `<tr>
        <td data-label="Select"><input type="checkbox" class="teacher-row-check" ${selected ? 'checked':''} onchange="toggleTeacherSelection(${t.id}, this.checked)"></td>
        <td data-label="#">${idx + 1}</td>
        <td data-label="Name"><input class="table-inline-input" id="edit-name-${t.id}" value="${escHtml(t.name || '')}"></td>
        <td data-label="Email">${escHtml(t.email || '—')}</td>
        <td data-label="Status"><select class="table-inline-select" id="edit-status-${t.id}"><option value="approved" ${t.status==='approved'?'selected':''}>Approved</option><option value="pending" ${t.status==='pending'?'selected':''}>Pending</option></select></td>
        <td data-label="Language"><select class="table-inline-select" id="edit-lang-${t.id}"><option value="ar" ${t.preferred_language==='ar'?'selected':''}>Arabic</option><option value="en" ${t.preferred_language==='en'?'selected':''}>English</option></select></td>
        <td data-label="Date">${formatDate(t.created_at)}</td>
        <td class="teacher-actions-cell" data-label="Actions"><div class="teacher-actions-inline"><button class="btn btn-success btn-sm" id="btn-save-${t.id}" onclick="saveInlineEdit(${t.id})">Save</button><button class="btn btn-secondary btn-sm" onclick="cancelInlineEdit()">Cancel</button></div></td>
      </tr>`;
    }
    return `<tr>
      <td data-label="Select"><input type="checkbox" class="teacher-row-check" ${selected ? 'checked':''} onchange="toggleTeacherSelection(${t.id}, this.checked)"></td>
      <td data-label="#">${idx + 1}</td>
      <td data-label="Name"><strong>${escHtml(t.name || '—')}</strong></td>
      <td data-label="Email">${escHtml(t.email || '—')}</td>
      <td data-label="Status">${statusBadge(t.status)}</td>
      <td data-label="Language">${languageChip(t.preferred_language)}</td>
      <td data-label="Date">${formatDate(t.created_at)}</td>
      <td class="teacher-actions-cell" data-label="Actions"><div class="teacher-actions-inline">${pendingTab ? `<button class="btn btn-success btn-sm" id="btn-approve-${t.id}" onclick="approveTeacher(${t.id})">Approve</button>` : `<button class="btn btn-secondary btn-sm" onclick="startInlineEdit(${t.id})">Edit</button><button class="btn btn-danger btn-sm" onclick="confirmDeleteTeacher(${t.id})">Remove</button>`}</div></td>
    </tr>`;
  }).join('');
  return `<div class="table-responsive"><table class="teacher-table"><thead><tr><th><input type="checkbox" ${allSelected ? 'checked':''} onchange="toggleSelectAll(this.checked)"></th><th>#</th><th>Name</th><th>Email</th><th>Status</th><th>Language</th><th>Date</th><th>Actions</th></tr></thead><tbody>${rows}</tbody></table></div>`;
}

function buildMobileCards(teachers, pendingTab=false){
  return `<div class="teacher-cards">${teachers.map((t, idx) => {
    const selected = selectedTeacherIds.has(t.id);
    const editing = editingTeacherId === t.id;
    if(editing){
      return `<article class="teacher-card"><div class="teacher-card-top"><label class="teacher-select-wrap"><input type="checkbox" ${selected ? 'checked':''} onchange="toggleTeacherSelection(${t.id}, this.checked)"><span>#${idx + 1}</span></label></div><div class="teacher-card-grid"><label><span>Name</span><input class="table-inline-input" id="edit-name-${t.id}" value="${escHtml(t.name || '')}"></label><div><span>Email</span><strong>${escHtml(t.email || '—')}</strong></div><label><span>Status</span><select class="table-inline-select" id="edit-status-${t.id}"><option value="approved" ${t.status==='approved'?'selected':''}>Approved</option><option value="pending" ${t.status==='pending'?'selected':''}>Pending</option></select></label><label><span>Language</span><select class="table-inline-select" id="edit-lang-${t.id}"><option value="ar" ${t.preferred_language==='ar'?'selected':''}>Arabic</option><option value="en" ${t.preferred_language==='en'?'selected':''}>English</option></select></label><div><span>Date</span><strong>${formatDate(t.created_at)}</strong></div></div><div class="teacher-card-actions"><button class="btn btn-success btn-sm" id="btn-save-${t.id}" onclick="saveInlineEdit(${t.id})">Save</button><button class="btn btn-secondary btn-sm" onclick="cancelInlineEdit()">Cancel</button></div></article>`;
    }
    return `<article class="teacher-card"><div class="teacher-card-top"><label class="teacher-select-wrap"><input type="checkbox" ${selected ? 'checked':''} onchange="toggleTeacherSelection(${t.id}, this.checked)"><span>#${idx + 1}</span></label>${pendingTab ? statusBadge(t.status) : ''}</div><div class="teacher-card-grid"><div><span>Name</span><strong>${escHtml(t.name || '—')}</strong></div><div><span>Email</span><strong>${escHtml(t.email || '—')}</strong></div><div><span>Language</span>${languageChip(t.preferred_language)}</div><div><span>Date</span><strong>${formatDate(t.created_at)}</strong></div></div><div class="teacher-card-actions">${pendingTab ? `<button class="btn btn-success btn-sm" id="btn-approve-${t.id}" onclick="approveTeacher(${t.id})">Approve</button>` : `<button class="btn btn-secondary btn-sm" onclick="startInlineEdit(${t.id})">Edit</button><button class="btn btn-danger btn-sm" onclick="confirmDeleteTeacher(${t.id})">Remove</button>`}</div></article>`;
  }).join('')}</div>`;
}

function emptyState(message, buttonLabel=''){
  return `<div class="empty-state"><div class="empty-icon">👥</div><p>${message}</p>${buttonLabel ? `<button class="btn btn-secondary btn-sm" type="button" onclick="setTab('all')">${buttonLabel}</button>` : ''}</div>`;
}

function renderCurrentTab(){
  const pendingWrap = byId('pendingTableWrap'); const allWrap = byId('allTableWrap');
  const pending = getFilteredPending(); const all = getFilteredAll();
  const mobile = window.innerWidth <= 768;
  if(pendingWrap){ pendingWrap.innerHTML = pending.length ? (mobile ? buildMobileCards(pending, true) : buildDesktopTable(pending, true)) : emptyState('No teachers awaiting approval.', 'View All Teachers'); }
  if(allWrap){ allWrap.innerHTML = all.length ? (mobile ? buildMobileCards(all, false) : buildDesktopTable(all, false)) : emptyState('No teachers yet.'); }
  updateStats(); syncBulkbar();
}

function bindPageEvents(){
  byId('teacherSearchInput')?.addEventListener('input', e => { searchTerm = normalize(e.target.value); renderCurrentTab(); });
  byId('teacherModalBackdrop')?.addEventListener('click', e => { if(e.target.id === 'teacherModalBackdrop') closeAddTeacherModal(); });
  byId('deleteTeacherBackdrop')?.addEventListener('click', e => { if(e.target.id === 'deleteTeacherBackdrop') closeDeleteModal(); });
  window.addEventListener('resize', () => renderCurrentTab());
}

async function initTeachersPage(){
  try{ bindPageEvents(); setTab('pending'); await loadAll(); }
  catch(err){ console.error('initTeachersPage failed:', err); }
}

if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initTeachersPage); else initTeachersPage();