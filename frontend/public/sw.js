const CACHE_VERSION = "lambchat-pwa-v1";
const APP_SHELL_CACHE = `${CACHE_VERSION}-shell`;
const STATIC_CACHE = `${CACHE_VERSION}-static`;

const APP_SHELL_URLS = [
  "/",
  "/manifest.json",
  "/icons/icon.svg",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];

const BACKEND_PREFIXES = [
  "/api",
  "/ws",
  "/health",
  "/tools",
  "/human",
  "/services",
  "/default",
  "/data_pipeline",
  "/simple_workflow",
];

const STATIC_ASSET_PATTERN =
  /\.(?:css|js|mjs|png|jpg|jpeg|svg|webp|ico|woff|woff2|ttf|otf|json)$/i;

function isSameOrigin(url) {
  return url.origin === self.location.origin;
}

function isBackendRequest(url) {
  return BACKEND_PREFIXES.some(
    (prefix) =>
      url.pathname === prefix || url.pathname.startsWith(`${prefix}/`),
  );
}

function isEventStreamRequest(request, url) {
  const accept = request.headers.get("accept") || "";
  return (
    accept.includes("text/event-stream") || url.pathname.includes("stream")
  );
}

function isNavigationRequest(request) {
  const accept = request.headers.get("accept") || "";
  return request.mode === "navigate" || accept.includes("text/html");
}

async function cacheAppShell() {
  const cache = await caches.open(APP_SHELL_CACHE);
  await cache.addAll(APP_SHELL_URLS);
}

self.addEventListener("install", (event) => {
  event.waitUntil(cacheAppShell().then(() => self.skipWaiting()));
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys
            .filter((key) => ![APP_SHELL_CACHE, STATIC_CACHE].includes(key))
            .map((key) => caches.delete(key)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

async function networkFirstAppShell(request) {
  const cache = await caches.open(APP_SHELL_CACHE);

  try {
    const response = await fetch(request);
    if (response.ok && response.type === "basic") {
      cache.put("/", response.clone());
    }
    return response;
  } catch (_error) {
    const cachedShell =
      (await cache.match("/")) || (await cache.match("/index.html"));
    return (
      cachedShell ||
      new Response("LambChat is offline.", {
        status: 503,
        statusText: "Service Unavailable",
        headers: { "Content-Type": "text/plain; charset=utf-8" },
      })
    );
  }
}

async function cacheFirstStatic(request) {
  const cached = await caches.match(request);
  if (cached) return cached;

  const response = await fetch(request);
  if (response.ok && response.type === "basic") {
    const cache = await caches.open(STATIC_CACHE);
    cache.put(request, response.clone());
  }
  return response;
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  if (
    request.method !== "GET" ||
    !isSameOrigin(url) ||
    isBackendRequest(url) ||
    isEventStreamRequest(request, url)
  ) {
    return;
  }

  if (isNavigationRequest(request)) {
    event.respondWith(networkFirstAppShell(request));
    return;
  }

  if (STATIC_ASSET_PATTERN.test(url.pathname)) {
    event.respondWith(cacheFirstStatic(request));
  }
});

self.addEventListener("push", (event) => {
  if (!self.registration?.showNotification) return;

  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (_error) {
    payload = { body: event.data?.text() };
  }

  const title = payload.title || "LambChat";
  const options = {
    body: payload.body || payload.message || "You have a new LambChat update.",
    icon: payload.icon || "/icons/icon-192.png",
    badge: payload.badge || "/icons/icon-192.png",
    data: {
      url: payload.url || "/chat",
    },
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();

  const targetUrl = new URL(
    event.notification.data?.url || "/chat",
    self.location.origin,
  );

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clients) => {
        const existingClient = clients.find(
          (client) => new URL(client.url).origin === targetUrl.origin,
        );
        if (existingClient) {
          existingClient.focus();
          return existingClient.navigate(targetUrl.href);
        }
        return self.clients.openWindow(targetUrl.href);
      }),
  );
});
