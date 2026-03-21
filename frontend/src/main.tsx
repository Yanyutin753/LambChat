import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import "katex/dist/katex.min.css";
import "./i18n";
import App from "./App.tsx";
import { AuthProvider } from "./hooks/useAuth";
import { SettingsProvider } from "./contexts/SettingsContext";
import { isMobileDevice, resetMobileViewport } from "./utils/mobile";

// Fix mobile viewport zoom issue after notification interaction
// This prevents the page from staying zoomed in after clicking browser notifications
if (typeof window !== "undefined" && isMobileDevice()) {
  // Reset viewport on visibility change (when app comes back from background)
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      resetMobileViewport();
    }
  });

  // Also handle focus event as a fallback
  window.addEventListener("focus", () => {
    window.scrollTo(0, 0);
  });
}

// Register Service Worker for PWA support (production only)
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    navigator.serviceWorker
      .register("/sw.js")
      .then((registration) => {
        console.log("[SW] Registered:", registration.scope);

        // Check for updates periodically
        setInterval(
          () => {
            registration.update();
          },
          60 * 60 * 1000,
        ); // every hour
      })
      .catch((error) => {
        console.warn("[SW] Registration failed:", error);
      });
  });
}

// 开发时临时禁用 StrictMode 避免 SSE 双重连接问题
// 生产环境可以重新启用
createRoot(document.getElementById("root")!).render(
  <BrowserRouter>
    <AuthProvider>
      <SettingsProvider>
        <App />
      </SettingsProvider>
    </AuthProvider>
  </BrowserRouter>,
);
