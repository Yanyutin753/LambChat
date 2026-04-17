import { useCallback, useEffect, useState } from "react";
import { isMobileDevice, resetMobileViewport } from "../utils/mobile";

interface NotificationOptions {
  body?: string;
  icon?: string;
  badge?: string;
  tag?: string;
  data?: unknown;
  onClick?: () => void;
  url?: string; // URL to navigate when notification is clicked
}

export function useBrowserNotification() {
  const [permission, setPermission] =
    useState<NotificationPermission>("default");
  const [isSupported, setIsSupported] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    if (typeof window !== "undefined") {
      const supported = "Notification" in window;
      setIsSupported(supported);
      setIsMobile(isMobileDevice());

      if (supported) {
        setPermission(Notification.permission);
      }
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

      // Fix mobile viewport zoom after permission dialog dismissal
      // Mobile browsers (especially iOS Safari) may zoom in when showing system dialogs
      resetMobileViewport();

      return result === "granted";
    } catch (e) {
      console.error("[BrowserNotification] Request permission failed:", e);
      return false;
    }
  }, []);

  const notify = useCallback(
    (title: string, options?: NotificationOptions): Notification | null => {
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
          icon: "/icons/icon.svg",
          badge: "/icons/icon.svg",
          tag: "lambchat-notification",
          ...options,
        });

        if (options?.onClick) {
          notification.onclick = () => {
            options.onClick!();
            notification.close();
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
    },
    [],
  );

  return {
    isSupported,
    permission,
    requestPermission,
    notify,
    isMobile,
  };
}
