import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "katex/dist/katex.min.css";
import "./i18n";
import App from "./App.tsx";
import "./styles/tailwind.css";
import "./styles/base.css";
import "./styles/animations.css";
import "./styles/components.css";
import "./styles/auth.css";
import "./styles/chat.css";
import "./styles/skill.css";
import "./styles/glass.css";
import "./styles/marketplace.css";
import "./styles/welcome.css";
import "./styles/approval.css";
import "./styles/landing.css";
import "./styles/syntax-highlight.css";
import "./styles/markdown.css";
import "./styles/utilities.css";
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
