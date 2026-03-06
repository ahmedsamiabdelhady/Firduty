/** login.js — handles admin login */

const API = localStorage.getItem('firduty_api') || 'http://localhost:8000';

async function doLogin() {
  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value;
  const errEl = document.getElementById('errorMsg');
  errEl.style.display = 'none';

  if (!username || !password) return;

  try {
    const res = await fetch(`${API}/auth/admin/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    if (!res.ok) {
      errEl.textContent = I18N.t('invalid_credentials');
      errEl.style.display = 'block';
      return;
    }

    const data = await res.json();
    localStorage.setItem('firduty_token', data.access_token);
    localStorage.setItem('firduty_api', API);
    window.location.href = 'planner.html';
  } catch (e) {
    errEl.textContent = I18N.t('error_generic');
    errEl.style.display = 'block';
  }
}

// Allow Enter key to submit
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('password').addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
  });
});

async function toggleLang() {
  await I18N.toggle();
}