/**
 * login.js — Admin login flow for Firduty.
 *
 * Login endpoint: POST /auth/admin/login/json (JSON body)
 * Token validation: GET /auth/validate
 * Token storage: localStorage key 'firduty_token'
 */

window.API_BASE = window.API_BASE || localStorage.getItem('firduty_api') || 'https://naval-donnamarie-firduty-6e288803.koyeb.app';

function byId(id) {
  return document.getElementById(id);
}

function setLoading(isLoading) {
  const btn = byId('loginBtn');
  const user = byId('username');
  const pass = byId('password');

  if (btn) {
    btn.disabled = isLoading;
    btn.textContent = isLoading ? (I18N?.t('loading') || 'Loading...') : (I18N?.t('sign_in') || 'Sign In');
    btn.classList.toggle('is-loading', isLoading);
  }

  if (user) user.disabled = isLoading;
  if (pass) pass.disabled = isLoading;
}

function showError(msg) {
  const el = byId('loginError');
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'block';
}

function clearError() {
  const el = byId('loginError');
  if (!el) return;
  el.textContent = '';
  el.style.display = 'none';
}

function updateLangBtn() {
  const btn = byId('langBtn');
  if (!btn) return;
  btn.textContent = I18N.getLang() === 'ar' ? 'EN | عربي' : 'عربي | EN';
}

function updateDirFromLang() {
  const lang = (typeof I18N !== 'undefined' && I18N.getLang()) || localStorage.getItem('firduty_lang') || 'ar';
  document.documentElement.lang = lang;
  document.documentElement.dir = lang === 'ar' ? 'rtl' : 'ltr';
}

async function toggleLang() {
  const current = I18N.getLang();
  await I18N.load(current === 'ar' ? 'en' : 'ar');
  updateDirFromLang();
  updateLangBtn();
}

function initPasswordToggle() {
  const passwordInput = byId('password');
  const toggleBtn = byId('togglePasswordBtn');
  if (!passwordInput || !toggleBtn) return;

  toggleBtn.addEventListener('click', () => {
    const isHidden = passwordInput.type === 'password';
    passwordInput.type = isHidden ? 'text' : 'password';
    toggleBtn.textContent = isHidden ? 'Hide' : 'Show';
    toggleBtn.setAttribute('aria-pressed', String(isHidden));
    toggleBtn.setAttribute('aria-label', isHidden ? 'Hide password' : 'Show password');
  });
}

async function doLogin() {
  const username = byId('username')?.value.trim() || '';
  const password = byId('password')?.value || '';

  clearError();

  if (!username || !password) {
    showError(I18N.t('invalid_credentials'));
    return;
  }

  setLoading(true);

  try {
    const res = await fetch(`${window.API_BASE}/auth/admin/login/json`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    if (res.ok) {
      const data = await res.json();
      localStorage.setItem('firduty_token', data.access_token);
      window.location.href = 'dashboard.html';
      return;
    }

    if (res.status === 401) {
      showError(I18N.t('invalid_credentials'));
    } else {
      showError(I18N.t('error_generic'));
    }
  } catch (err) {
    console.error('[login] Network error:', err);
    showError(I18N.t('error_generic'));
  } finally {
    setLoading(false);
  }
}

async function validateExistingToken() {
  const token = localStorage.getItem('firduty_token');
  if (!token) return;

  try {
    const res = await fetch(`${window.API_BASE}/auth/validate`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (res.ok) {
      window.location.href = 'dashboard.html';
    } else {
      localStorage.removeItem('firduty_token');
    }
  } catch (_) {
    // ignore and keep form visible
  }
}

function bindEnterSubmit() {
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') doLogin();
  });
}

async function initLoginPage() {
  updateDirFromLang();
  updateLangBtn();
  initPasswordToggle();
  bindEnterSubmit();
  byId('username')?.focus();
  await validateExistingToken();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initLoginPage);
} else {
  initLoginPage();
}
