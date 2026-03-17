/**
 * login.js — Admin login  v2.5
 * Improvements: eye-toggle, login-error div, proper lang button update, Enter key.
 */

const _API = window.API_BASE || localStorage.getItem('firduty_api') ||
  'https://naval-donnamarie-firduty-6e288803.koyeb.app';

/* ── Auto-redirect if already logged in ──────────────────────────────────── */
(async function () {
  const token = localStorage.getItem('firduty_token');
  if (!token) return;
  try {
    const res = await fetch(`${_API}/auth/validate`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) window.location.replace('dashboard.html');
    else localStorage.removeItem('firduty_token');
  } catch (_) { /* network error – show form */ }
})();

/* ── Language toggle ─────────────────────────────────────────────────────── */
function toggleLang() {
  const next = I18N.getLang() === 'ar' ? 'en' : 'ar';
  I18N.load(next).then(_updateLangBtn);
}

function _updateLangBtn() {
  const btn = document.getElementById('langToggle');
  if (btn) btn.textContent = I18N.getLang() === 'ar' ? 'EN | عربي' : 'عربي | EN';
}
// Run once on load
document.addEventListener('DOMContentLoaded', _updateLangBtn);

/* ── Password eye toggle ─────────────────────────────────────────────────── */
function togglePassword() {
  const pw  = document.getElementById('password');
  const btn = document.getElementById('eyeBtn');
  if (!pw) return;
  const isHidden = pw.type === 'password';
  pw.type = isHidden ? 'text' : 'password';
  if (btn) btn.textContent = isHidden ? '🙈' : '👁';
}

/* ── Error display ───────────────────────────────────────────────────────── */
function _showError(msg) {
  const el = document.getElementById('loginError');
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'block';
}
function _clearError() {
  const el = document.getElementById('loginError');
  if (el) el.style.display = 'none';
}

/* ── Login ───────────────────────────────────────────────────────────────── */
async function doLogin() {
  _clearError();

  const usernameEl = document.getElementById('username');
  const passwordEl = document.getElementById('password');
  const btnEl      = document.getElementById('loginBtn');

  const username = usernameEl?.value.trim() ?? '';
  const password = passwordEl?.value ?? '';

  if (!username || !password) {
    _showError(I18N.t('invalid_credentials'));
    (username ? passwordEl : usernameEl)?.focus();
    return;
  }

  if (btnEl) {
    btnEl.disabled = true;
    btnEl.innerHTML = `<span style="display:inline-block;width:16px;height:16px;border:2px solid rgba(255,255,255,0.4);border-top-color:#fff;border-radius:50%;animation:spin 0.6s linear infinite"></span>`;
  }

  try {
    const res = await fetch(`${_API}/auth/admin/login/json`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ username, password }),
    });

    if (res.ok) {
      const data = await res.json();
      localStorage.setItem('firduty_token', data.access_token);
      window.location.replace('dashboard.html');
      return;
    }

    _showError(res.status === 401
      ? I18N.t('invalid_credentials')
      : I18N.t('error_generic'));
  } catch (_) {
    _showError(I18N.t('error_generic'));
  } finally {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.innerHTML = `<span data-i18n="sign_in">${I18N.t('sign_in')}</span>`;
    }
  }
}
