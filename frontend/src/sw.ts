/// <reference lib="webworker" />

import { CacheableResponsePlugin } from "workbox-cacheable-response";
import { clientsClaim } from "workbox-core";
import { ExpirationPlugin } from "workbox-expiration";
import { cleanupOutdatedCaches, precacheAndRoute } from "workbox-precaching";
import { registerRoute } from "workbox-routing";
import { CacheFirst, StaleWhileRevalidate } from "workbox-strategies";
import { isPwaSkipWaitingMessage } from "./pwaGuards";
import {
  getPwaRequestKind,
  isBackendPath,
  isStaticAssetPath,
} from "./pwaRouting";

declare const self: ServiceWorkerGlobalScope & {
  __WB_MANIFEST: Array<unknown>;
};

const STATIC_CACHE = "lambchat-static-v7";
const FONT_STYLES_CACHE = "lambchat-font-styles-v2";
const FONT_FILES_CACHE = "lambchat-font-files-v2";
const OFFLINE_URL = "/offline.html";
const RETIRED_RUNTIME_CACHES = [
  "lambchat-app-shell-v1",
  "lambchat-app-shell-v2",
  "lambchat-static-v2",
  "lambchat-static-v3",
  "lambchat-static-v4",
  "lambchat-static-v5",
  "lambchat-static-v6",
];

cleanupOutdatedCaches();
precacheAndRoute(self.__WB_MANIFEST);
clientsClaim();

self.addEventListener("install", (event) => {
  event.waitUntil(self.skipWaiting());
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      await Promise.all(RETIRED_RUNTIME_CACHES.map((name) => caches.delete(name)));
      await self.clients.claim();

      const clients = await self.clients.matchAll({
        includeUncontrolled: true,
        type: "window",
      });

      await Promise.all(
        clients.map(async (client) => {
          try {
            const url = new URL(client.url);
            if (
              url.origin !== self.location.origin ||
              isBackendPath(url.pathname) ||
              isStaticAssetPath(url.pathname)
            ) {
              return;
            }
            if ("navigate" in client && typeof client.navigate === "function") {
              await client.navigate(client.url);
            }
          } catch {
            // A failed refresh should not prevent the new service worker from activating.
          }
        }),
      );
    })(),
  );
});

self.addEventListener("message", (event) => {
  if (!isPwaSkipWaitingMessage(event.data)) return;

  event.waitUntil(self.skipWaiting());
});

async function getOfflineFallback(): Promise<Response> {
  const cachedFallback =
    (await caches.match(OFFLINE_URL)) || (await caches.match("/index.html"));

  return (
    cachedFallback ||
    new Response("LambChat is offline.", {
      status: 503,
      statusText: "Service Unavailable",
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    })
  );
}

registerRoute(
  ({ request }) =>
    getPwaRequestKind({
      method: request.method,
      mode: request.mode,
      url: request.url,
      scopeOrigin: self.location.origin,
      accept: request.headers.get("accept"),
    }) === "navigation",
  async (options) => {
    try {
      return await fetch(options.request);
    } catch {
      return getOfflineFallback();
    }
  },
);

registerRoute(
  ({ request }) =>
    getPwaRequestKind({
      method: request.method,
      mode: request.mode,
      url: request.url,
      scopeOrigin: self.location.origin,
      accept: request.headers.get("accept"),
    }) === "static-asset",
  new StaleWhileRevalidate({
    cacheName: STATIC_CACHE,
    plugins: [
      new CacheableResponsePlugin({
        statuses: [0, 200],
      }),
      new ExpirationPlugin({
        maxEntries: 220,
        maxAgeSeconds: 60 * 60 * 24 * 30,
      }),
    ],
  }),
);

registerRoute(
  ({ url }) => url.origin === "https://fonts.googleapis.com",
  new StaleWhileRevalidate({
    cacheName: FONT_STYLES_CACHE,
    plugins: [
      new CacheableResponsePlugin({
        statuses: [0, 200],
      }),
      new ExpirationPlugin({
        maxEntries: 12,
        maxAgeSeconds: 60 * 60 * 24 * 30,
      }),
    ],
  }),
);

registerRoute(
  ({ url }) => url.origin === "https://fonts.gstatic.com",
  new CacheFirst({
    cacheName: FONT_FILES_CACHE,
    plugins: [
      new CacheableResponsePlugin({
        statuses: [0, 200],
      }),
      new ExpirationPlugin({
        maxEntries: 24,
        maxAgeSeconds: 60 * 60 * 24 * 365,
      }),
    ],
  }),
);

self.addEventListener("push", (event) => {
  if (!self.registration?.showNotification) return;

  let payload: {
    title?: string;
    body?: string;
    message?: string;
    icon?: string;
    badge?: string;
    url?: string;
  } = {};

  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = { body: event.data?.text() };
  }

  const title = payload.title || "LambChat";
  const options: NotificationOptions = {
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
          (client): client is WindowClient =>
            "focus" in client &&
            "navigate" in client &&
            new URL(client.url).origin === targetUrl.origin,
        );

        if (existingClient) {
          existingClient.focus();
          return existingClient.navigate(targetUrl.href);
        }

        return self.clients.openWindow(targetUrl.href);
      }),
  );
});
