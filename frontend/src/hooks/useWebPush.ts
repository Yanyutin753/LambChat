/**
 * Web Push subscription hook
 * Web Push 订阅钩子
 */

import { useCallback, useEffect, useState } from "react";
import { pushApi, type PushSubscriptionJSON } from "../services/api/push";

export type PushStatus =
  | "idle"
  | "loading"
  | "subscribed"
  | "unavailable"
  | "error";

/**
 * Convert VAPID base64 public key to Uint8Array for pushManager.subscribe()
 */
function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const outputArray = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) {
    outputArray[i] = rawData.charCodeAt(i);
  }
  return outputArray;
}

async function getPushRegistration(): Promise<ServiceWorkerRegistration | null> {
  const registration = await navigator.serviceWorker.getRegistration();
  if (!registration) return null;
  return navigator.serviceWorker.ready;
}

export function useWebPush() {
  const [status, setStatus] = useState<PushStatus>("idle");
  const [vapidKey, setVapidKey] = useState<string | null>(null);

  // Initialize: check support and fetch VAPID key
  useEffect(() => {
    let cancelled = false;

    async function init() {
      // Check if push is supported
      if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
        if (!cancelled) setStatus("unavailable");
        return;
      }

      try {
        // Fetch VAPID public key
        const key = await pushApi.getVapidPublicKey();
        if (!key || cancelled) {
          if (!cancelled) setStatus("unavailable");
          return;
        }
        if (!cancelled) setVapidKey(key);

        // Check existing subscription
        const registration = await getPushRegistration();
        if (!registration) {
          if (!cancelled) setStatus("unavailable");
          return;
        }
        const existing = await registration.pushManager.getSubscription();
        const registered = existing
          ? (await pushApi.getSubscriptionStatus(existing.endpoint)).registered
          : false;
        if (!cancelled) {
          setStatus((current) =>
            current === "loading"
              ? current
              : registered
                ? "subscribed"
                : "idle",
          );
        }
      } catch {
        if (!cancelled) setStatus("unavailable");
      }
    }

    init();
    return () => {
      cancelled = true;
    };
  }, []);

  const subscribe = useCallback(async () => {
    if (!vapidKey || status === "unavailable") return;

    setStatus("loading");
    try {
      // Request notification permission first
      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setStatus("idle");
        return false;
      }

      const registration = await getPushRegistration();
      if (!registration) {
        setStatus("unavailable");
        return false;
      }
      const existing = await registration.pushManager.getSubscription();
      if (
        existing &&
        !(await pushApi.getSubscriptionStatus(existing.endpoint)).registered
      ) {
        await existing.unsubscribe();
      }
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapidKey),
      });

      // Send subscription to backend
      const subscriptionJSON = subscription.toJSON() as PushSubscriptionJSON;
      await pushApi.subscribe(subscriptionJSON, navigator.userAgent);
      setStatus("subscribed");
      return true;
    } catch (err) {
      console.error("[useWebPush] Subscribe failed:", err);
      setStatus("error");
      return false;
    }
  }, [vapidKey, status]);

  const unsubscribe = useCallback(async () => {
    if (status !== "subscribed") return;

    try {
      const registration = await getPushRegistration();
      if (!registration) {
        setStatus("unavailable");
        return false;
      }
      const existing = await registration.pushManager.getSubscription();
      if (existing) {
        const endpoint = existing.endpoint;
        await existing.unsubscribe();
        await pushApi.unsubscribe(endpoint);
      }
      setStatus("idle");
      return true;
    } catch (err) {
      console.error("[useWebPush] Unsubscribe failed:", err);
      setStatus("error");
      return false;
    }
  }, [status]);

  return {
    status,
    vapidKey,
    subscribe,
    unsubscribe,
  };
}
