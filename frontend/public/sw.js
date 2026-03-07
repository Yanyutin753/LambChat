// LambChat Service Worker for Mobile Notifications
// This enables notifications on mobile browsers even when the app is in background

const NOTIFICATION_TAG = "lambchat-notification";

// Install event - cache static assets if needed
self.addEventListener("install", (event) => {
  console.log("[ServiceWorker] Installing...");
  self.skipWaiting();
});

// Activate event - clean up old caches
self.addEventListener("activate", (event) => {
  console.log("[ServiceWorker] Activated");
  event.waitUntil(self.clients.claim());
});

// Handle notification click
self.addEventListener("notificationclick", (event) => {
  console.log("[ServiceWorker] Notification clicked:", event.notification.tag);

  event.notification.close();

  const notificationData = event.notification.data || {};
  const urlToOpen = notificationData.url || "/";

  // Focus existing window or open new one
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then((clientList) => {
        // Try to find an existing window
        for (const client of clientList) {
          if (client.url.includes(self.location.origin) && "focus" in client) {
            // Navigate to the specific URL if needed
            if (urlToOpen !== "/" && client.navigate) {
              client.navigate(urlToOpen);
            }
            return client.focus();
          }
        }
        // No existing window, open a new one
        if (self.clients.openWindow) {
          return self.clients.openWindow(urlToOpen);
        }
      }),
  );
});

// Handle notification close
self.addEventListener("notificationclose", (event) => {
  console.log("[ServiceWorker] Notification closed");
});

// Handle push events (for future push notification support from server)
self.addEventListener("push", (event) => {
  console.log("[ServiceWorker] Push received");

  let notificationData = {
    title: "LambChat",
    body: "You have a new message",
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    tag: NOTIFICATION_TAG,
    data: { url: "/" },
  };

  // Parse push data if available
  if (event.data) {
    try {
      const pushData = event.data.json();
      notificationData = {
        ...notificationData,
        ...pushData,
        data: {
          url: pushData.url || "/",
        },
      };
    } catch (e) {
      notificationData.body = event.data.text();
    }
  }

  const options = {
    body: notificationData.body,
    icon: notificationData.icon,
    badge: notificationData.badge,
    tag: notificationData.tag,
    data: notificationData.data,
    vibrate: [200, 100, 200], // Vibration pattern for mobile
    requireInteraction: false, // Auto-close on mobile
    renotify: true, // Notify even if tag is the same
  };

  event.waitUntil(
    self.registration.showNotification(notificationData.title, options),
  );
});

// Message from main thread - used to show notifications from app
self.addEventListener("message", (event) => {
  console.log("[ServiceWorker] Message received:", event.data);

  if (event.data && event.data.type === "SHOW_NOTIFICATION") {
    const { title, options } = event.data.payload;

    const notificationOptions = {
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      vibrate: [200, 100, 200],
      requireInteraction: false,
      renotify: true,
      ...options,
    };

    event.waitUntil(
      self.registration.showNotification(title, notificationOptions),
    );
  }
});
