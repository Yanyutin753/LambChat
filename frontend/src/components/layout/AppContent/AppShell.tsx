import { lazy, Suspense, type ReactNode } from "react";
import "../../../styles/desktop.css";
import { Header } from "./Header";
import type { TabType } from "./types";

const ProfileModal = lazy(() =>
  import("../../profile/ProfileModal").then((module) => ({
    default: module.ProfileModal,
  })),
);

export interface AppShellProps {
  activeTab: TabType;
  headerActions?: ReactNode;
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  setMobileSidebarOpen: (open: boolean) => void;
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

  return (
    <>
      {showProfileModal && (
        <Suspense fallback={null}>
          <ProfileModal
            showProfileModal={showProfileModal}
            onCloseProfileModal={onCloseProfileModal}
          />
        </Suspense>
      )}

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
