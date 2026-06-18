import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { SessionSidebar } from "../../panels/SessionSidebar";
import { AppShell } from "./AppShell";
import { TabContent } from "./TabContent";
import type { TabType } from "./types";
import type { PluginRuntimeContributionStates } from "../../../extensions/coreContributions";

export interface NonChatAppContentProps {
  activeTab: Exclude<TabType, "chat">;
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: import("../../../types").VersionInfo | null;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;
  onShowProfile: () => void;
  runtimePlugins?: PluginRuntimeContributionStates;
}

export function NonChatAppContent({
  activeTab,
  showProfileModal,
  onCloseProfileModal,
  versionInfo,
  sidebarCollapsed,
  setSidebarCollapsed,
  mobileSidebarOpen,
  setMobileSidebarOpen,
  onShowProfile,
  runtimePlugins,
}: NonChatAppContentProps) {
  const navigate = useNavigate();

  const handleSelectSession = useCallback(
    (id: string) => {
      setMobileSidebarOpen(false);
      navigate(`/chat/${id}`);
    },
    [navigate, setMobileSidebarOpen],
  );
  const handleNewSession = useCallback(() => {
    setMobileSidebarOpen(false);
    navigate("/chat");
  }, [navigate, setMobileSidebarOpen]);
  const handleMobileClose = useCallback(
    () => setMobileSidebarOpen(false),
    [setMobileSidebarOpen],
  );

  return (
    <AppShell
      activeTab={activeTab}
      showProfileModal={showProfileModal}
      onCloseProfileModal={onCloseProfileModal}
      versionInfo={versionInfo}
      setMobileSidebarOpen={setMobileSidebarOpen}
      currentProjectId={null}
      projectManager={{ projects: [] }}
      onNewSession={handleNewSession}
      onShowProfile={onShowProfile}
      runtimePlugins={runtimePlugins}
      sidebar={
        <SessionSidebar
          currentSessionId={null}
          onSelectSession={handleSelectSession}
          onNewSession={handleNewSession}
          mobileOpen={mobileSidebarOpen}
          onMobileClose={handleMobileClose}
          isCollapsed={sidebarCollapsed}
          onToggleCollapsed={setSidebarCollapsed}
          onShowProfile={onShowProfile}
        />
      }
    >
      <TabContent activeTab={activeTab} runtimePlugins={runtimePlugins} />
    </AppShell>
  );
}
