// Market Heat Dashboard — service worker
// Caches the app shell only. data.json is ALWAYS fetched from the network
// (never served from cache) so the dashboard never silently shows stale
// market data while offline/online detection is ambiguous.

const CACHE_NAME = "market-heat-shell-v5";
const SHELL_FILES = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icon.svg",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(SHELL_FILES))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never cache data.json — always go to network so the dashboard reflects
  // the latest committed data, falling back to nothing (not stale data) if offline.
  if (url.pathname.endsWith("data.json")) {
    event.respondWith(fetch(event.request));
    return;
  }

  // App shell: cache-first, falling back to network.
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
