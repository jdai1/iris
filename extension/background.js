import { IRIS_CONFIG } from './config.js';

const AUTH_KEYS = ['authToken', 'authRefreshToken', 'authExpiresAt', 'firebaseApiKey'];

chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === 'install') {
    chrome.storage.sync.set({ onboardingComplete: false });
    chrome.storage.local.remove(AUTH_KEYS);
    chrome.tabs.create({ url: chrome.runtime.getURL('onboarding.html') });
  }
});

async function clearAuth() {
  await Promise.all([chrome.storage.local.remove(AUTH_KEYS), chrome.storage.sync.set({ onboardingComplete: false })]);
}

async function refreshAuthToken(secrets) {
  if (!secrets.authRefreshToken || !secrets.firebaseApiKey) return '';
  const response = await fetch(`https://securetoken.googleapis.com/v1/token?key=${encodeURIComponent(secrets.firebaseApiKey)}`, {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({ grant_type: 'refresh_token', refresh_token: secrets.authRefreshToken }),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok || !payload?.id_token) { await clearAuth(); throw new Error(payload?.error?.message || 'Your Iris session expired'); }
  const next = {
    authToken: payload.id_token,
    authRefreshToken: payload.refresh_token || secrets.authRefreshToken,
    authExpiresAt: Date.now() + (Number(payload.expires_in) || 3600) * 1000,
    firebaseApiKey: secrets.firebaseApiKey,
  };
  await chrome.storage.local.set(next);
  return next.authToken;
}

async function validAuthToken(forceRefresh = false) {
  const secrets = await chrome.storage.local.get({ authToken: '', authRefreshToken: '', authExpiresAt: 0, firebaseApiKey: '' });
  if (!forceRefresh && secrets.authToken && Number(secrets.authExpiresAt) > Date.now() + 60_000) return secrets.authToken;
  if (secrets.authRefreshToken && secrets.firebaseApiKey) return refreshAuthToken(secrets);
  return secrets.authToken || '';
}

async function irisFetch(message, forceRefresh = false) {
  if (typeof message.path !== 'string' || !message.path.startsWith('/api/')) {
    throw new Error('Invalid Iris API path');
  }
  const token = await validAuthToken(forceRefresh);
  const headers = { 'Content-Type': 'application/json', ...(message.options?.headers || {}) };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(`${IRIS_CONFIG.apiBase.replace(/\/+$/, '')}${message.path}`, { ...message.options, headers });
}

async function apiError(response) {
  const payload = await response.json().catch(() => null);
  if (response.status === 401) return new Error('Iris could not verify this login. Please sign in again.');
  if (response.status === 503) return new Error(payload?.detail || 'Iris authentication is temporarily unavailable. Please try again.');
  return new Error(payload?.detail || `Iris returned HTTP ${response.status}`);
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === 'iris-config') {
    sendResponse(IRIS_CONFIG);
    return false;
  }
  if (message?.type === 'iris-session-status') {
    chrome.storage.local.get({ authToken: '', authRefreshToken: '' })
      .then(({ authToken, authRefreshToken }) => sendResponse({ connected: Boolean(authToken || authRefreshToken) }));
    return true;
  }
  if (message?.type === 'iris-disconnect') {
    clearAuth().then(() => sendResponse({ ok: true })).catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type !== 'iris-request') return false;
  (async () => {
    try {
      let response = await irisFetch(message);
      if (response.status === 401) response = await irisFetch(message, true);
      const payload = response.status === 204 ? null : await response.json().catch(() => null);
      if (response.status === 401) await clearAuth();
      sendResponse({ ok: response.ok, status: response.status, payload });
    } catch (error) { sendResponse({ ok: false, error: error.message }); }
  })();
  return true;
});

chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  let origin = '';
  try { origin = new URL(sender.url).origin; } catch { return false; }
  const validMessage = message?.type === 'iris-auth' && typeof message.token === 'string' && message.token
    && typeof message.refreshToken === 'string' && message.refreshToken && typeof message.apiKey === 'string' && message.apiKey;
  if (origin !== new URL(IRIS_CONFIG.appBase).origin || !validMessage) return false;
  fetch(`${IRIS_CONFIG.apiBase}/api/me`, { headers: { Authorization: `Bearer ${message.token}` } })
    .then(async (response) => { if (!response.ok) throw await apiError(response); return Promise.all([
      chrome.storage.sync.set({ onboardingComplete: true }),
      chrome.storage.local.set({ authToken: message.token, authRefreshToken: message.refreshToken, authExpiresAt: Number(message.expiresAt) || Date.now() + 55 * 60 * 1000, firebaseApiKey: message.apiKey }),
    ]); })
    .then(() => sendResponse({ ok: true })).catch((error) => sendResponse({ ok: false, error: error.message }));
  return true;
});
