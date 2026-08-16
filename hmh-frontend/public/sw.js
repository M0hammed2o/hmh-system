const VERSION = "2026-08-02-1";
const SHELL_CACHE = `hmh-shell-${VERSION}`;
const ASSET_CACHE = `hmh-assets-${VERSION}`;
const SHELL_KEY = "/__hmh_app_shell__";
const INSTALL_ASSETS = [
  "/offline.html",
  "/manifest.json",
  "/icon-192.png",
  "/icon-512.png",
  "/icon-maskable-512.png",
  "/apple-touch-icon.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil((async () => {
    const assetCache = await caches.open(ASSET_CACHE);
    await Promise.all(INSTALL_ASSETS.map(async (url) => {
      try {
        const response = await fetch(url, { cache: "no-store" });
        if (response.ok) await assetCache.put(url, response);
      } catch {
        // One optional icon must not prevent the worker from installing.
      }
    }));

    try {
      const shell = await fetch("/", { cache: "no-store" });
      if (shell.ok) await (await caches.open(SHELL_CACHE)).put(SHELL_KEY, shell);
    } catch {
      // The dedicated offline document remains available as a final fallback.
    }
  })());
});

self.addEventListener("activate", (event) => {
  event.waitUntil((async () => {
    const current = new Set([SHELL_CACHE, ASSET_CACHE]);
    await Promise.all((await caches.keys()).filter((key) => key.startsWith("hmh-") && !current.has(key)).map((key) => caches.delete(key)));
    await self.clients.claim();
  })());
});

self.addEventListener("message", (event) => {
  if (event.data?.type === "SKIP_WAITING") self.skipWaiting();
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith((async () => {
      try {
        const response = await fetch(request);
        if (response.ok && response.headers.get("content-type")?.includes("text/html")) {
          await (await caches.open(SHELL_CACHE)).put(SHELL_KEY, response.clone());
        }
        return response;
      } catch {
        return (await caches.match(SHELL_KEY)) || (await caches.match("/offline.html")) || Response.error();
      }
    })());
    return;
  }

  if (url.pathname.startsWith("/assets/")) {
    event.respondWith((async () => {
      const cached = await caches.match(request);
      if (cached) return cached;
      const response = await fetch(request);
      if (response.ok) await (await caches.open(ASSET_CACHE)).put(request, response.clone());
      return response;
    })());
  }
});
