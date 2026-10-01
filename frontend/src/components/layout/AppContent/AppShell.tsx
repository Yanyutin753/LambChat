import { useEffect, type ReactNode } from "react";
import "../../../styles/desktop.css";
import { ProfileModal } from "../../profile/ProfileModal";
import { Header } from "./Header";
import { isStandaloneDisplayMode } from "../../../hooks/useAppViewport";
import {
  getBrowserChromeNudgeScrollY,
  shouldNudgeBrowserChrome,
} from "./appBrowserChrome";
import { isMobileDevice } from "../../../utils/mobile";
import type { Project } from "../../../types";
import type { TabType } from "./types";

export interface AppShellProps {
  activeTab: TabType;
  headerActions?: ReactNode;
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  setMobileSidebarOpen: (open: boolean) => void;
  currentProjectId: string | null;
  projectManager: { projects: Project[] };
  onNewSession: () => void;
  onShowProfile: () => void;
  sidebar?: ReactNode;
  children: ReactNode;
  // Model selection
  availableModels?:
    | {
        id: string;
        value: string;
        provider?: string;
        label: string;
        description?: string;
      }[]
    | null;
  currentModelId?: string;
  onSelectModel?: (modelId: string, modelValue: string) => void;
  // Share
  sessionId?: string | null;
  // Outline
  showOutlineButton?: boolean;
  onToggleOutline?: () => void;
}

export function AppShell({
  activeTab,
  headerActions,
  showProfileModal,
  onCloseProfileModal,
  setMobileSidebarOpen,
  currentProjectId,
  projectManager,
  onNewSession,
  onShowProfile,
  sidebar,
  children,
  availableModels,
  currentModelId,
  onSelectModel,
  sessionId,
  showOutlineButton,
  onToggleOutline,
}: AppShellProps) {
  const appSafeAreaTop =
    "var(--app-safe-area-top-active, max(var(--app-safe-area-top, 0px), var(--app-fullscreen-safe-area-top, 0px)))";
  const appSafeAreaBottom =
    "var(--app-safe-area-bottom-active, max(var(--app-safe-area-bottom, 0px), var(--app-fullscreen-safe-area-bottom, 0px)))";

  useEffect(() => {
    if (typeof window === "undefined") return undefined;

    const enabled = shouldNudgeBrowserChrome({
      isMobileDevice: isMobileDevice(),
      isStandaloneDisplayMode: isStandaloneDisplayMode(),
      hasVisualViewport: Boolean(window.visualViewport),
    });

    if (!enabled) return undefined;

    document.documentElement.setAttribute("data-browser-chrome-nudge", "true");

    let raf = 0;
    const nudgeBrowserChrome = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        const top = getBrowserChromeNudgeScrollY({
          scrollHeight: document.documentElement.scrollHeight,
          innerHeight: window.innerHeight,
        });
        if (top > 0 && window.scrollY < top) {
          window.scrollTo(0, top);
        }
      });
    };

    const timers = [120, 420, 900].map((delay) =>
      window.setTimeout(nudgeBrowserChrome, delay),
    );
    nudgeBrowserChrome();
    window.addEventListener("resize", nudgeBrowserChrome);
    window.addEventListener("orientationchange", nudgeBrowserChrome);

    return () => {
      cancelAnimationFrame(raf);
      timers.forEach((timer) => window.clearTimeout(timer));
      window.removeEventListener("resize", nudgeBrowserChrome);
      window.removeEventListener("orientationchange", nudgeBrowserChrome);
      document.documentElement.removeAttribute("data-browser-chrome-nudge");
    };
  }, []);

  return (
    <>
      <ProfileModal
        showProfileModal={showProfileModal}
        onCloseProfileModal={onCloseProfileModal}
      />

      <div
        data-workspace-ui={activeTab === "chat" ? "" : undefined}
        className="flex w-full overflow-hidden"
        style={{
          backgroundColor: "var(--theme-bg)",
          boxSizing: "content-box",
          paddingTop: appSafeAreaTop,
          paddingBottom: appSafeAreaBottom,
          // 桌面自绘标题栏占用的高度（网页/移动端 --titlebar-inset 为 0）
          height: `calc(var(--app-viewport-height, 100dvh) - ${appSafeAreaTop} - ${appSafeAreaBottom} - var(--titlebar-inset, 0px))`,
          transform: "translate3d(0, var(--app-viewport-offset-top, 0px), 0)",
        }}
      >
        {sidebar}

        <div
          data-workspace-content=""
          className="relative z-0 flex flex-1 min-w-0 flex-col overflow-hidden"
          style={
            activeTab !== "chat"
              ? { containerType: "inline-size", containerName: "panel-shell" }
              : undefined
          }
        >
          <Header
            activeTab={activeTab}
            headerActions={headerActions}
            setMobileSidebarOpen={setMobileSidebarOpen}
            currentProjectId={currentProjectId}
            projectManager={projectManager}
            onNewSession={onNewSession}
            onShowProfile={onShowProfile}
            availableModels={availableModels}
            currentModelId={currentModelId}
            onSelectModel={onSelectModel}
            sessionId={sessionId}
            showOutlineButton={showOutlineButton}
            onToggleOutline={onToggleOutline}
          />

          {children}
        </div>
      </div>
    </>
  );
}
