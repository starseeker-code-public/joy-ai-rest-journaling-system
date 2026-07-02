/* Joy service worker: cache-first app shell, network-first journal reads
   with cache fallback so past entries stay readable offline. */
'use strict';

const SHELL_CACHE = 'joy-shell-v1';
const DATA_CACHE = 'joy-data-v1';
const SHELL = ['/', '/index.html', '/app.js', '/styles.css', '/manifest.webmanifest', '/icon.svg'];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(
      keys.filter((k) => ![SHELL_CACHE, DATA_CACHE].includes(k)).map((k) => caches.delete(k))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;

  // Journal reads: network first, fall back to the last good response
  if (url.pathname === '/api/journals') {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          const copy = response.clone();
          caches.open(DATA_CACHE).then((cache) => cache.put(event.request, copy));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/auth/')) return;

  // Shell: cache first
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
