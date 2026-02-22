// FreeWise Service Worker — network-first for dynamic content, cache-first for static assets
const CACHE = 'freewise-v1';
const STATIC = [
  '/static/css/tailwind.css',
  '/static/css/fonts.css',
  '/static/vendor/htmx/htmx.min.js',
  '/static/vendor/lucide/lucide.min.js',
];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(STATIC)));
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (!e.request.url.startsWith(self.location.origin)) return;
  const url = new URL(e.request.url);
  // Static assets: cache-first
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(caches.match(e.request).then(cached => cached || fetch(e.request)));
    return;
  }
  // Navigation: network-first (always fresh server data)
  e.respondWith(fetch(e.request));
});
