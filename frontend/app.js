/* Joy PWA — vanilla JS client for the Joy API (same-origin via the gateway).
   Offline-first: the service worker caches the shell; entries composed while
   offline are queued in localStorage and flushed on reconnect. */
'use strict';

const TOKEN_KEY = 'joy.token';
const QUEUE_KEY = 'joy.pendingEntries';

const $ = (id) => document.getElementById(id);

// ---- tiny API client ----------------------------------------------------

function token() { return localStorage.getItem(TOKEN_KEY); }

async function api(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}) };
  const t = token();
  if (t) headers.Authorization = `Bearer ${t}`;
  const res = await fetch(path, { ...options, headers });
  if (res.status === 401 && t) { logout(); throw new Error('Session expired'); }
  let body = null;
  try { body = await res.json(); } catch { /* 204s etc. */ }
  if (!res.ok) throw new Error((body && body.error) || `Request failed (${res.status})`);
  return body;
}

// ---- auth ----------------------------------------------------------------

async function login(email, password) {
  const body = await api('/auth/login', {
    method: 'POST', body: JSON.stringify({ email, password }),
  });
  localStorage.setItem(TOKEN_KEY, body.token);
  return body.user;
}

async function register(email, password) {
  await api('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) });
  return login(email, password);
}

function logout() {
  localStorage.removeItem(TOKEN_KEY);
  // Never leak one account's data or drafts into the next session
  localStorage.removeItem(QUEUE_KEY);
  if (window.caches) caches.delete('joy-data-v1').catch(() => {});
  showAuth();
}

// ---- offline queue --------------------------------------------------------

function readQueue() {
  try { return JSON.parse(localStorage.getItem(QUEUE_KEY)) || []; }
  catch { return []; }
}

function writeQueue(queue) { localStorage.setItem(QUEUE_KEY, JSON.stringify(queue)); }

async function flushQueue() {
  const queue = readQueue();
  if (!queue.length || !token()) return;
  const remaining = [];
  for (const entry of queue) {
    try {
      await api('/api/journals', { method: 'POST', body: JSON.stringify(entry) });
    } catch (err) {
      if (err instanceof TypeError) {
        remaining.push(entry); // network failure: retry on next reconnect
      } else {
        // Server rejected it (4xx): keep it out of the queue or it would
        // poison every future flush
        console.warn('Dropped rejected offline entry:', err.message, entry);
      }
    }
  }
  writeQueue(remaining);
  if (remaining.length < queue.length) await renderEntries();
}

// ---- views ----------------------------------------------------------------

function showAuth() {
  $('auth-view').hidden = false;
  $('journal-view').hidden = true;
  $('session').hidden = true;
}

async function showJournal() {
  $('auth-view').hidden = true;
  $('journal-view').hidden = false;
  $('session').hidden = false;
  try {
    const me = await api('/auth/me');
    $('whoami').textContent = me.email;
  } catch { return; }
  await flushQueue();
  await renderEntries();
}

function entryItem(entry) {
  const li = document.createElement('li');
  const sentiment = entry.ai && entry.ai.sentiment && entry.ai.sentiment.label;
  const mood = entry.mood ? ` · mood ${entry.mood}` : '';
  const tags = (entry.tags || []).map((t) => `#${t}`).join(' ');
  const title = document.createElement('strong');
  title.textContent = entry.title;
  const meta = document.createElement('small');
  meta.textContent = `${(entry.date || '').slice(0, 10)}${mood} ${tags}`;
  const body = document.createElement('p');
  body.textContent = entry.content || '';
  li.append(title);
  if (sentiment) {
    const badge = document.createElement('span');
    badge.className = `badge ${sentiment}`;
    badge.textContent = sentiment;
    li.append(' ', badge);
  }
  li.append(meta, body);
  return li;
}

async function renderEntries(entries) {
  const list = $('entries');
  if (!entries) {
    try { entries = await api('/api/journals'); }
    catch { return; }
    entries.sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  }
  list.replaceChildren(...entries.map(entryItem));
}

// ---- events ----------------------------------------------------------------

$('auth-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const mode = event.submitter && event.submitter.dataset.mode;
  $('auth-error').textContent = '';
  try {
    const action = mode === 'register' ? register : login;
    await action($('email').value, $('password').value);
    await showJournal();
  } catch (err) {
    $('auth-error').textContent = err.message;
  }
});

$('logout').addEventListener('click', () => {
  api('/auth/logout', { method: 'POST' }).catch(() => {});
  logout();
});

$('compose').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('compose-error').textContent = '';
  const entry = {
    title: $('title').value.trim(),
    content: $('content').value,
    mood: $('mood').value ? Number($('mood').value) : undefined,
    tags: $('tags').value.split(',').map((t) => t.trim()).filter(Boolean),
  };
  let saved = false;
  try {
    if (!navigator.onLine) throw new TypeError('offline');
    await api('/api/journals', { method: 'POST', body: JSON.stringify(entry) });
    saved = true;
  } catch (err) {
    if (err instanceof TypeError) { // fetch-level network failure: queue for later
      writeQueue([...readQueue(), entry]);
      $('offline-banner').hidden = false;
    } else {
      $('compose-error').textContent = err.message;
      return;
    }
  }
  event.target.reset();
  // Outside the try: a render bug must never re-queue an already-saved entry
  if (saved) renderEntries().catch(() => {});
});

let searchTimer;
$('search').addEventListener('input', (event) => {
  clearTimeout(searchTimer);
  const q = event.target.value.trim();
  searchTimer = setTimeout(async () => {
    if (!q) return renderEntries();
    try {
      renderEntries(await api(`/api/journals/search?q=${encodeURIComponent(q)}`));
    } catch { /* search backend down: keep current list */ }
  }, 300);
});

window.addEventListener('online', () => {
  $('offline-banner').hidden = true;
  flushQueue();
});
window.addEventListener('offline', () => { $('offline-banner').hidden = false; });

// ---- boot -------------------------------------------------------------------

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {});
}

if (token()) showJournal(); else showAuth();
if (!navigator.onLine) $('offline-banner').hidden = false;
