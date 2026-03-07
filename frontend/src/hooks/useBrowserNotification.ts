import { useCallback, useEffect, useState } from "react";

interface NotificationOptions {
  body?: string;
  icon?: string;
  tag?: string;
  data?: unknown;
  onClick?: () => void;
}

export function useBrowserNotification() {
  const [permission, setPermission] =
    useState<NotificationPermission>("default");
  const [isSupported, setIsSupported] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window) {
      setIsSupported(true);
      setPermission(Notification.permission);
    }
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

  const notify = useCallback((title: string, options?: NotificationOptions) => {
    if (!("Notification" in window)) {
      console.warn("[BrowserNotification] Not supported");
      return null;
    }

    if (Notification.permission !== "granted") {
      console.warn("[BrowserNotification] Permission not granted");
      return null;
    }

    try {
      const notification = new Notification(title, {
        icon: "/icons/icon-192.png",
        badge: "/icons/icon-192.png",
        ...options,
      });

      // Handle click
      const handleClick = options?.onClick;
      if (handleClick) {
        notification.onclick = () => {
          handleClick();
          notification.close();
          // Focus the window
          window.focus();
        };
      }

      // Auto close after 5 seconds
      setTimeout(() => notification.close(), 5000);

      return notification;
    } catch (e) {
      console.error("[BrowserNotification] Show failed:", e);
      return null;
    }
  }, []);

  return {
    isSupported,
    permission,
    requestPermission,
    notify,
  };
}
