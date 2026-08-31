import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "katex/dist/katex.min.css";
import "./fonts.css";
// CJK 字体异步加载（约 940 条 @font-face 拆独立 chunk，不阻塞首屏，
// 也不占 PWA 预缓存预算），见 src/fonts-cjk.ts。
void import("./fonts-cjk");
import "./i18n";
import App from "./App.tsx";
import "./styles/tailwind.css";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/animations.css";
import "./styles/components.css";
import "./styles/auth.css";
import "./styles/chat.css";
import "./styles/skill.css";
import "./styles/glass.css";
import "./styles/card-base.css";
import "./styles/marketplace.css";
import "./styles/persona.css";
import "./styles/team.css";
import "./styles/welcome.css";
import "./styles/approval.css";
import "./styles/landing.css";
import "./styles/syntax-highlight.css";
import "./styles/markdown.css";
import "./styles/pwa.css";
import "./styles/utilities.css";
import { AuthProvider } from "./hooks/useAuth";
import { SettingsProvider } from "./contexts/SettingsContext";
import { installMobileViewportResetHandlers } from "./utils/mobile";
import { installFontScaleSync } from "./utils/fontScale";
import { registerLambChatPwa } from "./pwa";

// Fix mobile viewport zoom issue after notification interaction
// This prevents the page from staying zoomed in after clicking browser notifications
installMobileViewportResetHandlers();

// 监听登录回灌的字体大小偏好变化
installFontScaleSync();

registerLambChatPwa();

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
