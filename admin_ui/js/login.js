/**
 * login.js — Admin login flow for Firduty.
 *
 * Handles:
 *   - Form submission via doLogin()
 *   - POST /auth/admin/login → JWT stored in localStorage as 'firduty_token'
 *   - Redirect to dashboard.html on success
 *   - Inline error display on failure
 *   - Language toggle (AR / EN)
 *   - Auto-redirect if already logged in
 */

const API_BASE = localStorage.getItem('firduty_api') || 'https://naval-donnamarie-firduty-6e288803.koyeb.app/';

// ── Auto-redirect if already authenticated ────────────────────────────────────
(function () {
  const token = localStorage.getItem('firduty_token');
  if (token) {
    window.location.href = 'dashboard.html';
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

  // Clear previous error
  if (errorEl) { errorEl.textContent = ''; errorEl.style.display = 'none'; }

  if (!username || !password) {
    _showError(I18N.t('invalid_credentials'));
    return;
  }

  // Disable button while request is in flight
  if (btn) { btn.disabled = true; btn.textContent = I18N.t('loading'); }

  try {
    const res = await fetch(`${API_BASE}auth/admin/login`, {
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
  if (el) {
    el.textContent = msg;
    el.style.display = 'block';
  }
}

// ── Allow Enter key to submit ─────────────────────────────────────────────────
document.addEventListener('keydown', function (e) {
  if (e.key === 'Enter') doLogin();
});

// ── Init ──────────────────────────────────────────────────────────────────────
_updateLangBtn();