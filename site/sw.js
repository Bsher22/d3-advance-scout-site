// Keeps the scouting site usable when the signal drops. Every page and data file that has been opened
// is kept on the device; the network copy is used whenever it answers in time, the kept copy otherwise.
// Sign-in pages are never kept.
const CACHE = "scout-v1";
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (/^\/(login|logout|account|api)(\/|$)/.test(url.pathname)) return;
  const key = url.pathname === "/" ? "/index.html" : url.pathname;
  e.respondWith((async () => {
    const cache = await caches.open(CACHE);
    const kept = await cache.match(key);
    try {
      const ctl = new AbortController();
      const timer = kept ? setTimeout(() => ctl.abort(), 3500) : null;   // only hurry when there is a kept copy to fall back on
      const res = await fetch(req, { signal: ctl.signal });
      if (timer) clearTimeout(timer);
      if (res.ok && !res.redirected && res.type === "basic") cache.put(key, res.clone());
      return res;
    } catch (err) {
      if (kept) return kept;
      throw err;
    }
  })());
});
