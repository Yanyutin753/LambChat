// LambChat Service Worker
// Provides: offline caching, mobile notifications, periodic background updates

const CACHE_NAME = "lambchat-v1";
const STATIC_ASSETS = [
  "/",
  "/icons/icon.svg",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
];
const NOTIFICATION_TAG = "lambchat-notification";

// Install - pre-cache critical static assets
self.addEventListener("install", (event) => {
  console.log("[SW] Installing...");
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)),
  );
});

// Activate - clean up old caches
self.addEventListener("activate", (event) => {
  console.log("[SW] Activated");
  event.waitUntil(
    caches
      .keys()
      .then((keys) =>
        Promise.all(
          keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)),
        ),
      )
      .then(() => self.clients.claim()),
  );
});

// Fetch - network first for API, cache first for static assets
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET requests
  if (request.method !== "GET") return;

  // Skip cross-origin requests (except our own API)
  if (url.origin !== self.location.origin) return;

  // API & SSE requests: network only
  if (url.pathname.startsWith("/api") || url.pathname.startsWith("/ws")) return;

  // Static assets (js, css, images, fonts): cache first, fallback to network
  if (
    url.pathname.match(/\.(js|css|svg|png|ico|woff2?|ttf|eot)$/) ||
    url.pathname.startsWith("/icons/") ||
    url.pathname.startsWith("/images/")
  ) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          // Cache successful responses for static assets
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
          }
          return response;
        });
      }),
    );
    return;
  }

  // HTML pages: network first, fallback to cache
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, clone));
        }
        return response;
      })
      .catch(() => caches.match(request)),
  );
});

// Handle notification click
self.addEventListener("notificationclick", (event) => {
  console.log("[SW] Notification clicked:", event.notification.tag);
  event.notification.close();

  const notificationData = event.notification.data || {};
  const urlToOpen = notificationData.url || "/";

  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        for (const client of clientList) {
          if (client.url.includes(self.location.origin) && "focus" in client) {
            if (urlToOpen !== "/" && client.navigate) {
              client.navigate(urlToOpen);
            }
            return client.focus();
          }
        }
        if (self.clients.openWindow) {
          return self.clients.openWindow(urlToOpen);
        }
      }),
  );
});

self.addEventListener("notificationclose", () => {
  console.log("[SW] Notification closed");
});

// Push events
self.addEventListener("push", (event) => {
  console.log("[SW] Push received");

  let notificationData = {
    title: "LambChat",
    body: "You have a new message",
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    tag: NOTIFICATION_TAG,
    data: { url: "/" },
  };

  if (event.data) {
    try {
      const pushData = event.data.json();
      notificationData = {
        ...notificationData,
        ...pushData,
        data: { url: pushData.url || "/" },
      };
    } catch {
      notificationData.body = event.data.text();
    }
  }

  event.waitUntil(
    self.registration.showNotification(notificationData.title, {
      body: notificationData.body,
      icon: notificationData.icon,
      badge: notificationData.badge,
      tag: notificationData.tag,
      data: notificationData.data,
      vibrate: [200, 100, 200],
      requireInteraction: false,
      renotify: true,
    }),
  );
});

// Message from main thread
self.addEventListener("message", (event) => {
  if (event.data?.type === "SHOW_NOTIFICATION") {
    const { title, options } = event.data.payload;
    event.waitUntil(
      self.registration.showNotification(title, {
        icon: "/icons/icon-192.png",
        badge: "/icons/icon-192.png",
        vibrate: [200, 100, 200],
        requireInteraction: false,
        renotify: true,
        ...options,
      }),
    );
  }
});
