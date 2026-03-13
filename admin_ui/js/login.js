/**
 * login.js — Admin login flow for Firduty.
 *
 * Login endpoint: POST /auth/admin/login/json  (JSON body)
 *   - The Swagger UI uses POST /auth/admin/login (OAuth2 form body)
 *   - The Admin Web UI uses /auth/admin/login/json to keep the request as JSON
 *
 * Token validation: GET /auth/validate
 *   - Called on page load to auto-redirect if a valid token already exists
 *
 * Token storage: localStorage key 'firduty_token'
 */

const API_BASE = window.API_BASE || localStorage.getItem('firduty_api') || 'https://naval-donnamarie-firduty-6e288803.koyeb.app';

// ── Auto-redirect if already authenticated ────────────────────────────────────
(async function () {
  const token = localStorage.getItem('firduty_token');
  if (!token) return;

  try {
    const res = await fetch(`${window.API_BASE}/auth/validate`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (res.ok) {
      window.location.href = 'dashboard.html';
    } else {
      // Token is expired or invalid — clear it so the form is shown clean
      localStorage.removeItem('firduty_token');
    }
  } catch (_) {
    // Network error — just show the login form, don't crash
  }
})();

// ── Language toggle ───────────────────────────────────────────────────────────
function toggleLang() {
  const current = I18N.getLang();
  I18N.load(current === 'ar' ? 'en' : 'ar');
  _updateLangBtn();
}

function _updateLangBtn() {
  const btn = document.getElementById('langBtn');
  if (btn) btn.textContent = (I18N.getLang() === 'ar') ? 'EN' : 'عربي';
}

// ── Login ─────────────────────────────────────────────────────────────────────
async function doLogin() {
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  const errorEl  = document.getElementById('loginError');
  const btn      = document.getElementById('loginBtn');

  if (errorEl) { errorEl.textContent = ''; errorEl.style.display = 'none'; }

  if (!username || !password) {
    _showError(I18N.t('invalid_credentials'));
    return;
  }

  if (btn) { btn.disabled = true; btn.textContent = I18N.t('loading'); }

  try {
    const res = await fetch(`${window.API_BASE}/auth/admin/login/json`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ username, password }),
    });

    if (res.ok) {
      const data = await res.json();
      localStorage.setItem('firduty_token', data.access_token);
      window.location.href = 'dashboard.html';
    } else if (res.status === 401) {
      _showError(I18N.t('invalid_credentials'));
    } else {
      _showError(I18N.t('error_generic'));
    }
  } catch (err) {
    console.error('[login] Network error:', err);
    _showError(I18N.t('error_generic'));
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = I18N.t('sign_in'); }
  }
}

function _showError(msg) {
  const el = document.getElementById('loginError');
  if (el) { el.textContent = msg; el.style.display = 'block'; }
}

// ── Allow Enter key to submit ─────────────────────────────────────────────────
document.addEventListener('keydown', function (e) {
  if (e.key === 'Enter') doLogin();
});

// ── Init ──────────────────────────────────────────────────────────────────────
_updateLangBtn();