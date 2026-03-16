/**
 * login.js — Admin login flow for Firduty.
 *
 * Login endpoint: POST /auth/admin/login/json (JSON body)
 * Token validation: GET /auth/validate
 * Token storage: localStorage key 'firduty_token'
 */

window.API_BASE = window.API_BASE || localStorage.getItem('firduty_api') || 'https://naval-donnamarie-firduty-6e288803.koyeb.app';

const LOGIN_REMEMBER_KEY = 'firduty_remember_username';
const LOGIN_REMEMBER_FLAG = 'firduty_remember_enabled';

function byId(id) {
  return document.getElementById(id);
}

function setLoading(isLoading) {
  const btn = byId('loginBtn');
  const user = byId('username');
  const pass = byId('password');
  const remember = byId('rememberMe');
  const btnText = btn?.querySelector('.login-btn-text');

  if (btn) {
    btn.disabled = isLoading;
    btn.classList.toggle('is-loading', isLoading);
    btn.setAttribute('aria-busy', String(isLoading));
  }

  if (btnText) {
    btnText.textContent = isLoading ? (I18N?.t('loading') || 'Loading...') : (I18N?.t('sign_in') || 'Sign In');
  } else if (btn) {
    btn.textContent = isLoading ? (I18N?.t('loading') || 'Loading...') : (I18N?.t('sign_in') || 'Sign In');
  }

  if (user) user.disabled = isLoading;
  if (pass) pass.disabled = isLoading;
  if (remember) remember.disabled = isLoading;
}

function showError(msg) {
  const live = byId('loginError');
  if (live) {
    live.textContent = msg;
  }
  showToast(msg, 'danger');
}

function clearError() {
  const live = byId('loginError');
  if (live) {
    live.textContent = '';
  }
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
    toggleBtn.setAttribute('aria-pressed', String(isHidden));
    toggleBtn.setAttribute('aria-label', isHidden ? 'Hide password' : 'Show password');
    toggleBtn.setAttribute('title', isHidden ? 'Hide password' : 'Show password');
    toggleBtn.classList.toggle('is-visible', isHidden);
  });
}

function showToast(message, type = 'danger') {
  const container = byId('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);

  window.setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(8px)';
    window.setTimeout(() => toast.remove(), 220);
  }, 2800);
}

function persistRememberedUser() {
  const remember = byId('rememberMe');
  const username = byId('username')?.value.trim() || '';

  if (remember?.checked && username) {
    localStorage.setItem(LOGIN_REMEMBER_KEY, username);
    localStorage.setItem(LOGIN_REMEMBER_FLAG, '1');
    return;
  }

  localStorage.removeItem(LOGIN_REMEMBER_KEY);
  localStorage.removeItem(LOGIN_REMEMBER_FLAG);
}

function loadRememberedUser() {
  const remembered = localStorage.getItem(LOGIN_REMEMBER_KEY) || '';
  const enabled = localStorage.getItem(LOGIN_REMEMBER_FLAG) === '1';
  const username = byId('username');
  const remember = byId('rememberMe');

  if (remember) remember.checked = enabled;
  if (username && enabled && remembered) {
    username.value = remembered;
  }
}

async function doLogin() {
  const username = byId('username')?.value.trim() || '';
  const password = byId('password')?.value || '';

  clearError();

  if (!username || !password) {
    showError(I18N?.t('invalid_credentials') || 'Invalid credentials');
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
      persistRememberedUser();
      showToast('Login successful', 'success');
      window.setTimeout(() => {
        window.location.href = 'dashboard.html';
      }, 120);
      return;
    }

    if (res.status === 401) {
      showError(I18N?.t('invalid_credentials') || 'Invalid credentials');
    } else {
      showError(I18N?.t('error_generic') || 'Something went wrong');
    }
  } catch (err) {
    console.error('[login] Network error:', err);
    showError(I18N?.t('error_generic') || 'Something went wrong');
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
  const form = document.querySelector('.login-form');
  if (!form) return;
  form.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !(e.target instanceof HTMLButtonElement)) {
      e.preventDefault();
      doLogin();
    }
  });
}

function bindRememberToggle() {
  const remember = byId('rememberMe');
  if (!remember) return;
  remember.addEventListener('change', () => {
    if (!remember.checked) {
      localStorage.removeItem(LOGIN_REMEMBER_KEY);
      localStorage.removeItem(LOGIN_REMEMBER_FLAG);
    }
  });
}

async function initLoginPage() {
  updateDirFromLang();
  updateLangBtn();
  loadRememberedUser();
  initPasswordToggle();
  bindEnterSubmit();
  bindRememberToggle();
  if (byId('username')?.value) {
    byId('password')?.focus();
  } else {
    byId('username')?.focus();
  }
  await validateExistingToken();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initLoginPage);
} else {
  initLoginPage();
}
