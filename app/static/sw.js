// FreeWise Service Worker — network-first for dynamic content, cache-first for static assets
const CACHE = 'freewise-v4';

// Vendor/font files that never change — served cache-first for offline support
const PRECACHE = [
  '/static/css/fonts.css',
  '/static/vendor/htmx/htmx.min.js',
  '/static/vendor/lucide/lucide.min.js',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE)
      .then(c => c.addAll(PRECACHE))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys()
      .then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', e => {
  if (!e.request.url.startsWith(self.location.origin)) return;
  const url = new URL(e.request.url);

  // tailwind.css is rebuilt frequently — let the browser handle it natively,
  // bypassing the SW cache entirely so updates are always visible immediately.
  if (url.pathname === '/static/css/tailwind.css') return;

  // Other static assets (fonts, vendor libs) — cache-first
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(caches.match(e.request).then(cached => cached || fetch(e.request)));
    return;
  }

  // Navigation — network-first (always fresh server data)
  e.respondWith(fetch(e.request));
});

