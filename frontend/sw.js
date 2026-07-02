/* Joy service worker: cache-first app shell, network-first journal reads
   with cache fallback so past entries stay readable offline. */
'use strict';

// Bump BUILD on each frontend deploy so activate() purges the old shell and
// clients pick up new app.js/index.html/styles.css instead of serving stale
// cache-first copies forever.
const BUILD = '2026-07-03';
const SHELL_CACHE = `joy-shell-${BUILD}`;
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

  // Shell: stale-while-revalidate — serve cached instantly, refresh in the
  // background so a redeploy (new BUILD) is picked up without a hard reload.
  event.respondWith(
    caches.open(SHELL_CACHE).then((cache) =>
      cache.match(event.request).then((cached) => {
        const network = fetch(event.request)
          .then((response) => {
            if (response.ok) cache.put(event.request, response.clone());
            return response;
          })
          .catch(() => cached);
        return cached || network;
      })
    )
  );
});
