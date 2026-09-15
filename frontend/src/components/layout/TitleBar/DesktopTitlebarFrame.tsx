import { lazy, Suspense, useEffect, type ReactNode } from "react";
import { NavigationHistoryProvider } from "../../../hooks/useNavigationHistory";
import type { UpdateState } from "../../../types";
import type { DesktopOs } from "./titlebarPlatform";

// 懒加载进同一 chunk：不占网页/PWA 的 eager JS 预算。
const TitleBar = lazy(() =>
  import("./TitleBar").then((m) => ({ default: m.TitleBar })),
);

/**
 * 桌面壳（Tauri）专属框架：自绘标题栏 + 浏览器式前进/后退导航。
 * 挂载时向 :root 写入 --titlebar-inset（全屏页/Toaster 据此让位）。
 */
export function DesktopTitlebarFrame({
  os,
  updateState,
  onInstallUpdate,
  onSkipVersion,
  children,
}: {
  os: DesktopOs;
  updateState: UpdateState;
  onInstallUpdate: () => void;
  onSkipVersion: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    document.documentElement.style.setProperty("--titlebar-inset", "40px");
    return () => {
      document.documentElement.style.removeProperty("--titlebar-inset");
    };
  }, []);

  return (
    <NavigationHistoryProvider>
      <div className="flex h-full min-h-0 flex-col">
        <Suspense fallback={<div className="h-10 shrink-0" />}>
          <TitleBar
            os={os}
            updateState={updateState}
            onInstallUpdate={onInstallUpdate}
            onSkipVersion={onSkipVersion}
          />
        </Suspense>
        <div className="min-h-0 flex-1">{children}</div>
      </div>
    </NavigationHistoryProvider>
  );
}
