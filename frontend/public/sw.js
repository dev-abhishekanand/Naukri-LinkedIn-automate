// Progressive Web App Service Worker
const CACHE_NAME = 'job-command-v1';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(clients.claim());
});

self.addEventListener('fetch', (event) => {
  // Let network handle all API calls dynamically
  if (event.request.url.includes('/api/')) {
    return;
  }
  // Network first with cache fallback for static assets
  event.respondWith(
    fetch(event.request).catch(() => caches.match(event.request))
  );
});
