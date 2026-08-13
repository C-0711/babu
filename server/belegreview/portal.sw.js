// babu-Portal — App-Shell network-first, /api/* niemals cachen.
const CACHE = "babu-portal-v1";
self.addEventListener("install", e => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(clients.claim()));
self.addEventListener("fetch", e => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.pathname.startsWith("/api/") || url.pathname === "/chat") return;
  e.respondWith(
    fetch(e.request).then(r => {
      const kopie = r.clone();
      caches.open(CACHE).then(c => c.put(e.request, kopie)).catch(() => {});
      return r;
    }).catch(() => caches.match(e.request))
  );
});
