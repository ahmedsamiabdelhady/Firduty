/**
 * auth.js — Shared authentication utilities for all Admin UI pages.
 *
 * Include this script on every admin page that requires authentication
 * (dashboard.html, planner.html, reports.html, teachers.html).
 *
 * Features:
 *  - authHeaders()         Returns Authorization + Content-Type headers
 *  - logout()              Clears token and redirects to login
 *  - guardPage()           Redirects to login if no token stored (call on page load)
 *  - apiFetch(url, opts)   fetch() wrapper that auto-attaches auth header
 *                          and redirects to login on 401
 */

console.log('AUTH VERSION TEST 99');

window.API_BASE = localStorage.getItem('firduty_api') || 'https://naval-donnamarie-firduty-6e288803.koyeb.app';

/** Return headers object with Authorization and Content-Type set. */
function authHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${localStorage.getItem('firduty_token') || ''}`,
  };
}

/** Clear token and redirect to login page. */
function logout() {
  localStorage.removeItem('firduty_token');
  window.location.href = 'login.html';
}

/**
 * Call on every protected page's load.
 * Redirects immediately to login if no token is present.
 * Optionally validates the token against GET /auth/validate.
 *
 * @param {boolean} [validate=false] - Set true to make a network call to validate the token.
 */
async function guardPage(validate = false) {
  const token = localStorage.getItem('firduty_token');
  if (!token) {
    window.location.href = 'login.html';
    return;
  }

  if (!validate) return;

  try {
    const res = await fetch(`${window.API_BASE}/auth/validate`, {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    if (!res.ok) logout();
  } catch (_) {
    // Network error — let the page load; individual API calls will catch 401
  }
}

/**
 * fetch() wrapper with automatic auth header and 401 redirect.
 *
 * Usage (replaces raw fetch calls in dashboard.js, planner.js, etc.):
 *   const res = await apiFetch('admin/dashboard');
 *   const res = await apiFetch('teachers/', { method: 'POST', body: JSON.stringify(data) });
 *
 * @param {string} path   - URL path relative to API_BASE (no leading slash needed)
 * @param {object} [opts] - Standard fetch options (method, body, etc.)
 * @returns {Response}
 */
async function apiFetch(path, opts = {}) {
  const url = path.startsWith('http') ? path : `${window.API_BASE}${path}`;
  const res = await fetch(url, {
    ...opts,
    headers: {
      ...authHeaders(),
      ...(opts.headers || {}),
    },
  });
  if (res.status === 401) {
    logout();
  }
  return res;
}