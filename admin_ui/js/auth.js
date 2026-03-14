/**
 * auth.js — Shared authentication utilities for all Admin UI pages.
 * Uses the hosted Koyeb backend by default.
 */

const DEFAULT_API_BASE = 'https://naval-donnamarie-firduty-6e288803.koyeb.app';

function normalizeBase(base) {
  return String(base || '').trim().replace(/\/+$/, '');
}

function getPreferredApiBase() {
  const stored = normalizeBase(localStorage.getItem('firduty_api'));
  return stored || DEFAULT_API_BASE;
}

window.API_BASE = getPreferredApiBase();

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

function logout() {
  localStorage.removeItem('firduty_token');
  window.location.href = 'login.html';
}

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
    // Ignore transient network issues here.
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
  add(DEFAULT_API_BASE);

  return candidates;
}

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
      ? setTimeout(() => controller.abort(), timeoutMs)
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

      const isRetryable = (err?.name === 'AbortError' || err instanceof TypeError) && i < candidates.length - 1;

      // Never retry mutating requests against another backend candidate.
      if (method !== 'GET' && method !== 'HEAD') {
        break;
      }

      if (!isRetryable) {
        break;
      }
    }
  }

  throw lastError || new Error('Failed to fetch');
}
