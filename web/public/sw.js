const CACHE_NAME = "miloco-static-v1";
const HASHED_ASSET = /^\/assets\/.+-[A-Za-z0-9_-]{8,}\.(js|css)$/;

function isImmutablePublicAsset(request, url) {
  if (request.method !== "GET" || url.origin !== self.location.origin || url.search) {
    return false;
  }
  return (
    HASHED_ASSET.test(url.pathname) ||
    url.pathname.startsWith("/fonts/") ||
    url.pathname.startsWith("/icons/")
  );
}

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);
  if (!isImmutablePublicAsset(event.request, url)) {
    return;
  }
  event.respondWith(
    caches.open(CACHE_NAME).then(async (cache) => {
      const cached = await cache.match(event.request);
      if (cached) {
        return cached;
      }
      const response = await fetch(event.request);
      if (response.ok) {
        await cache.put(event.request, response.clone());
      }
      return response;
    }),
  );
});
