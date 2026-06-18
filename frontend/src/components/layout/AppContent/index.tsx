import { useCallback, useEffect, useRef, useState } from "react";
import { useVersion } from "../../../hooks/useVersion";
import { SIDEBAR_COLLAPSED_STORAGE_KEY } from "../../../hooks/useAuth";
import { authApi } from "../../../services/api";
import { ChatAppContent } from "./ChatAppContent";
import { NonChatAppContent } from "./NonChatAppContent";
import {
  APP_TOAST_SIDEBAR_OFFSET_VAR,
  getAppToastSidebarOffset,
} from "./appToastLayout";
import type { TabType } from "./types";
import type { PluginRuntimeContributionStates } from "../../../extensions/coreContributions";
import { useRightPanelAutoCollapse } from "./useRightPanelAutoCollapse";

interface AppContentProps {
  activeTab: TabType;
  runtimePlugins?: PluginRuntimeContributionStates;
}

export function AppContent({ activeTab, runtimePlugins }: AppContentProps) {
  const { versionInfo } = useVersion();
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
    return saved !== null ? saved === "true" : true;
  });
  const [showProfileModal, setShowProfileModal] = useState(false);
  const autoCollapsePendingRef = useRef(false);

  const handleSetSidebarCollapsed = useCallback(
    (collapsed: boolean | ((prev: boolean) => boolean)) => {
      setSidebarCollapsed((prev) => {
        const next =
          typeof collapsed === "function" ? collapsed(prev) : collapsed;

        // Detect user override: user expanded left sidebar while right panel
        // is wide and this wasn't triggered by our auto-collapse logic.
        if (
          !autoCollapsePendingRef.current &&
          typeof collapsed !== "function" &&
          next === false &&
          prev === true
        ) {
          const html = document.documentElement;
          let rightWidth = 0;
          if (html.getAttribute("data-sidebar-preview") === "open") {
            rightWidth += parseInt(
              localStorage.getItem("sidebar-preview-width") || "60",
              10,
            );
          }
          if (html.getAttribute("data-editor-sidebar") === "open") {
            rightWidth += parseInt(
              localStorage.getItem("editor-sidebar-width") || "30",
              10,
            );
          }
          if (rightWidth >= 50) {
            window.dispatchEvent(
              new CustomEvent("right-panel-auto-collapse:override"),
            );
          }
        }

        localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(next));
        authApi
          .updateMetadata({ sidebarCollapsed: String(next) })
          .catch(() => {});
        return next;
      });
    },
    [],
  );

  useRightPanelAutoCollapse((collapsed) => {
    autoCollapsePendingRef.current = true;
    handleSetSidebarCollapsed(collapsed);
  });

  useEffect(() => {
    if (autoCollapsePendingRef.current) {
      queueMicrotask(() => {
        autoCollapsePendingRef.current = false;
      });
    }
  });

  useEffect(() => {
    const handler = (e: Event) => {
      const collapsed = (e as CustomEvent).detail as boolean;
      setSidebarCollapsed(collapsed);
    };
    window.addEventListener("sidebar-collapsed-changed", handler);
    return () =>
      window.removeEventListener("sidebar-collapsed-changed", handler);
  }, []);

  useEffect(() => {
    if (typeof document === "undefined") return undefined;

    const rootStyle = document.documentElement.style;
    rootStyle.setProperty(
      APP_TOAST_SIDEBAR_OFFSET_VAR,
      getAppToastSidebarOffset({ sidebarCollapsed }),
    );

    return () => {
      rootStyle.removeProperty(APP_TOAST_SIDEBAR_OFFSET_VAR);
    };
  }, [sidebarCollapsed]);

  const handleCloseProfileModal = useCallback(
    () => setShowProfileModal(false),
    [],
  );
  const handleShowProfile = useCallback(() => setShowProfileModal(true), []);

  if (activeTab === "chat") {
    return (
      <ChatAppContent
        showProfileModal={showProfileModal}
        onCloseProfileModal={handleCloseProfileModal}
        versionInfo={versionInfo}
        sidebarCollapsed={sidebarCollapsed}
        setSidebarCollapsed={handleSetSidebarCollapsed}
        mobileSidebarOpen={mobileSidebarOpen}
        setMobileSidebarOpen={setMobileSidebarOpen}
        onShowProfile={handleShowProfile}
        runtimePlugins={runtimePlugins}
      />
    );
  }

  return (
    <NonChatAppContent
      activeTab={activeTab}
      showProfileModal={showProfileModal}
      onCloseProfileModal={handleCloseProfileModal}
      versionInfo={versionInfo}
      sidebarCollapsed={sidebarCollapsed}
      setSidebarCollapsed={handleSetSidebarCollapsed}
      mobileSidebarOpen={mobileSidebarOpen}
      setMobileSidebarOpen={setMobileSidebarOpen}
      onShowProfile={handleShowProfile}
      runtimePlugins={runtimePlugins}
    />
  );
}
