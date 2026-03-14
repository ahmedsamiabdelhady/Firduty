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
 *  - apiFetch(url, opts)   fetch() wrapper that auto-attaches auth header,
 *                          retries smart fallbacks on network failure,
 *                          and redirects to login on 401
 */

const LEGACY_API_BASE = 'https://naval-donnamarie-firduty-6e288803.koyeb.app';

function normalizeBase(base) {
  return String(base || '').trim().replace(/\/+$/, '');
}

function getPreferredApiBase() {
  const stored = normalizeBase(localStorage.getItem('firduty_api'));
  if (stored) return stored;

  const sameOriginApi = normalizeBase(`${window.location.origin}/api`);
  return sameOriginApi;
}

window.API_BASE = getPreferredApiBase();

/** Return headers object with Authorization set and JSON content-type when needed. */
function authHeaders(opts = {}) {
  const headers = {
    'Authorization': `Bearer ${localStorage.getItem('firduty_token') || ''}`,
    ...(opts.headers || {}),
  };

  const isFormData = typeof FormData !== 'undefined' && opts.body instanceof FormData;
  if (!isFormData && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  return headers;
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
    const res = await apiFetch('/auth/validate', {
      headers: { 'Authorization': `Bearer ${token}` },
      timeoutMs: 15000,
    });
    if (!res.ok) logout();
  } catch (_) {
    // Network error — let the page load; individual API calls will handle it.
  }
}

function buildApiUrl(base, path) {
  if (path.startsWith('http')) return path;
  const normalizedBase = normalizeBase(base);
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${normalizedBase}${normalizedPath}`;
}

function getApiBaseCandidates() {
  const candidates = [];
  const add = (value) => {
    const normalized = normalizeBase(value);
    if (normalized && !candidates.includes(normalized)) {
      candidates.push(normalized);
    }
  };

  add(localStorage.getItem('firduty_api'));
  add(`${window.location.origin}/api`);
  add(LEGACY_API_BASE);

  return candidates;
}

/**
 * fetch() wrapper with automatic auth header, timeout, fallback base retry,
 * and 401 redirect.
 *
 * Usage:
 *   const res = await apiFetch('/admin/dashboard');
 *   const res = await apiFetch('/teachers/', { method: 'POST', body: JSON.stringify(data) });
 *
 * @param {string} path   - URL path relative to API_BASE (leading slash optional)
 * @param {object} [opts] - Standard fetch options (method, body, etc.)
 * @returns {Promise<Response>}
 */
async function apiFetch(path, opts = {}) {
  if (path.startsWith('http')) {
    const directRes = await fetch(path, {
      ...opts,
      headers: authHeaders(opts),
    });
    if (directRes.status === 401) logout();
    return directRes;
  }

  const { timeoutMs = 30000, ...fetchOpts } = opts;
  const method = String(fetchOpts.method || 'GET').toUpperCase();
  const candidates = getApiBaseCandidates();
  let lastError = null;

  for (let i = 0; i < candidates.length; i++) {
    const base = candidates[i];
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timer = controller
      ? setTimeout(() => controller.abort(new DOMException('Request timed out', 'AbortError')), timeoutMs)
      : null;

    try {
      const res = await fetch(buildApiUrl(base, path), {
        ...fetchOpts,
        headers: authHeaders(fetchOpts),
        signal: controller ? controller.signal : undefined,
      });

      if (timer) clearTimeout(timer);

      if (res.status === 401) {
        logout();
        return res;
      }

      window.API_BASE = base;
      localStorage.setItem('firduty_api', base);
      return res;
    } catch (err) {
      if (timer) clearTimeout(timer);
      lastError = err;

      const isNetworkStyleError = err?.name === 'AbortError' || err instanceof TypeError;
      const shouldRetry = isNetworkStyleError && i < candidates.length - 1;

      if (!shouldRetry) {
        throw err;
      }

      // Retry the next candidate only on network/cors/timeout style failures.
      if (method !== 'GET' && method !== 'HEAD') {
        // For mutating requests, only retry if we are moving away from a dead/unreachable base.
        continue;
      }
    }
  }

  throw lastError || new Error('Failed to fetch');
}
