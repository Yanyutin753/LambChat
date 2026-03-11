import { useCallback, useEffect, useState, useRef } from "react";

interface NotificationOptions {
  body?: string;
  icon?: string;
  badge?: string;
  tag?: string;
  data?: unknown;
  onClick?: () => void;
  url?: string; // URL to navigate when notification is clicked
}

interface ServiceWorkerNotificationOptions extends NotificationOptions {
  vibrate?: number[];
  requireInteraction?: boolean;
  renotify?: boolean;
}

// Check if running on mobile device
function isMobileDevice(): boolean {
  if (typeof window === "undefined") return false;
  return /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
    navigator.userAgent,
  );
}

// Check if Service Worker is supported
function isServiceWorkerSupported(): boolean {
  return (
    typeof navigator !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window
  );
}

export function useBrowserNotification() {
  const [permission, setPermission] =
    useState<NotificationPermission>("default");
  const [isSupported, setIsSupported] = useState(false);
  const [isMobile, setIsMobile] = useState(false);
  const [swRegistration, setSwRegistration] =
    useState<ServiceWorkerRegistration | null>(null);
  const notificationClickHandlerRef = useRef<(() => void) | null>(null);
  const updateFoundHandlerRef = useRef<(() => void) | null>(null);

  // Register service worker
  const registerServiceWorker = useCallback(async () => {
    try {
      const registration = await navigator.serviceWorker.register("/sw.js", {
        scope: "/",
      });
      console.log(
        "[BrowserNotification] Service Worker registered:",
        registration.scope,
      );
      setSwRegistration(registration);

      // Handle service worker updates
      const handleUpdateFound = () => {
        console.log("[BrowserNotification] Service Worker update found");
      };
      registration.addEventListener("updatefound", handleUpdateFound);
      updateFoundHandlerRef.current = () => {
        registration.removeEventListener("updatefound", handleUpdateFound);
      };
    } catch (error) {
      console.error(
        "[BrowserNotification] Service Worker registration failed:",
        error,
      );
    }
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const supported = "Notification" in window;
      setIsSupported(supported);
      setIsMobile(isMobileDevice());

      if (supported) {
        setPermission(Notification.permission);
      }

      // Register service worker for mobile/background notifications
      if (isServiceWorkerSupported()) {
        registerServiceWorker();
      }
    }

    // Cleanup function
    return () => {
      // Remove updatefound listener
      if (updateFoundHandlerRef.current) {
        updateFoundHandlerRef.current();
        updateFoundHandlerRef.current = null;
      }
    };
  }, [registerServiceWorker]);

  // Listen for messages from service worker
  useEffect(() => {
    if (!isServiceWorkerSupported()) return;

    const handleMessage = (event: MessageEvent) => {
      if (event.data && event.data.type === "NOTIFICATION_CLICKED") {
        if (notificationClickHandlerRef.current) {
          notificationClickHandlerRef.current();
          notificationClickHandlerRef.current = null;
        }
      }
    };

    navigator.serviceWorker.addEventListener("message", handleMessage);
    return () => {
      navigator.serviceWorker.removeEventListener("message", handleMessage);
    };
  }, []);

  const requestPermission = useCallback(async (): Promise<boolean> => {
    if (!("Notification" in window)) {
      console.warn("[BrowserNotification] Not supported");
      return false;
    }

    if (Notification.permission === "granted") {
      return true;
    }

    if (Notification.permission === "denied") {
      console.warn("[BrowserNotification] Permission denied");
      return false;
    }

    try {
      const result = await Notification.requestPermission();
      setPermission(result);
      return result === "granted";
    } catch (e) {
      console.error("[BrowserNotification] Request permission failed:", e);
      return false;
    }
  }, []);

  const notify = useCallback(
    (title: string, options?: NotificationOptions) => {
      if (!("Notification" in window)) {
        console.warn("[BrowserNotification] Not supported");
        return null;
      }

      if (Notification.permission !== "granted") {
        console.warn("[BrowserNotification] Permission not granted");
        return null;
      }

      // Store click handler for later use
      if (options?.onClick) {
        notificationClickHandlerRef.current = options.onClick;
      }

      const notificationOptions: ServiceWorkerNotificationOptions = {
        icon: "/icons/icon-192.png",
        badge: "/icons/icon-192.png",
        tag: "lambchat-notification",
        vibrate: isMobile ? [200, 100, 200] : undefined,
        requireInteraction: false,
        renotify: true,
        ...options,
        // Store URL in data for service worker to use
        data: {
          url: options?.url || "/",
          ...(typeof options?.data === "object" ? options.data : {}),
        },
      };

      try {
        // Use Service Worker notification when:
        // 1. Page is hidden (user switched tabs or minimized)
        // 2. On mobile device with SW support
        // 3. Service Worker is registered
        const shouldUseServiceWorker =
          swRegistration &&
          isServiceWorkerSupported() &&
          (document.hidden || isMobile);

        if (shouldUseServiceWorker && swRegistration) {
          // Show notification via Service Worker (works in background on mobile)
          swRegistration
            .showNotification(title, notificationOptions)
            .then(() => {
              console.log("[BrowserNotification] SW notification shown");
            })
            .catch((err) => {
              console.error(
                "[BrowserNotification] SW notification failed:",
                err,
              );
              // Fallback to regular notification
              showRegularNotification(title, notificationOptions);
            });
          return null; // SW notifications don't return a Notification object
        } else {
          // Use regular notification (works when page is visible)
          return showRegularNotification(title, notificationOptions);
        }
      } catch (e) {
        console.error("[BrowserNotification] Show failed:", e);
        return null;
      }
    },
    [swRegistration, isMobile],
  );

  // Regular notification (for foreground)
  const showRegularNotification = (
    title: string,
    options: ServiceWorkerNotificationOptions,
  ): Notification | null => {
    try {
      const notification = new Notification(title, options);

      const handleClick = options?.onClick;
      if (handleClick) {
        notification.onclick = () => {
          handleClick();
          notification.close();
          window.focus();
        };
      }

      // Auto close after 5 seconds
      setTimeout(() => notification.close(), 5000);

      return notification;
    } catch (e) {
      console.error("[BrowserNotification] Regular notification failed:", e);
      return null;
    }
  };

  // Check if mobile notifications are properly supported
  const isMobileNotificationSupported = useCallback((): boolean => {
    return isMobile && isServiceWorkerSupported() && !!swRegistration;
  }, [isMobile, swRegistration]);

  return {
    isSupported,
    permission,
    requestPermission,
    notify,
    isMobile,
    isMobileNotificationSupported,
    swRegistration,
  };
}
