import "../../../styles/app-content.css";
import { useCallback, useEffect, useRef, useState } from "react";
import type { RightPanelLayoutSnapshot } from "../../../hooks/rightPanelLayout";
import { getRightPanelLayoutSnapshot } from "../../../hooks/rightPanelWidthEvents";
import { SIDEBAR_COLLAPSED_STORAGE_KEY } from "../../../hooks/useAuth";
import { authApi } from "../../../services/api";
import { ChatAppContent } from "./ChatAppContent";
import { NonChatAppContent } from "./NonChatAppContent";
import {
  APP_TOAST_SIDEBAR_OFFSET_VAR,
  getAppToastSidebarOffset,
} from "./appToastLayout";
import type { TabType } from "./types";
import {
  RIGHT_PANEL_WIDTH_CHANGED_EVENT,
  shouldTemporarilyCollapseNavigation,
} from "./rightPanelAutoCollapse";

import {
  NAVIGATION_WIDTH_CHANGED_EVENT,
  readStoredWidth,
} from "../DesktopSidebarShell/sidebarWidth";

// Reserve 480px for chat plus the persistent 52px activity rail.
const MINIMUM_CHAT_WITH_RAIL_PX = 532;

interface AppContentProps {
  activeTab: TabType;
}

export function AppContent({ activeTab }: AppContentProps) {
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // Persisted sidebar state — only changes on explicit user action
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
    return saved !== null ? saved === "true" : false;
  });
  const sidebarCollapsedRef = useRef(sidebarCollapsed);
  sidebarCollapsedRef.current = sidebarCollapsed;

  const navigationWidthRef = useRef(readStoredWidth());

  // Automatic layout changes never overwrite the saved sidebar preference.
  const [tempAutoCollapsed, setTempAutoCollapsed] = useState(() =>
    shouldTemporarilyCollapseNavigation({
      layout: getRightPanelLayoutSnapshot(),
      viewportWidth: window.innerWidth,
      minimumWorkspaceWithNavigationPx:
        navigationWidthRef.current + MINIMUM_CHAT_WITH_RAIL_PX,
      userOverrode: false,
    }),
  );
  const userOverrodeRef = useRef(false);
  const activeRightPanelLayoutRef = useRef<RightPanelLayoutSnapshot | null>(
    getRightPanelLayoutSnapshot(),
  );

  // Effective collapsed state: persisted OR temporary
  const effectiveCollapsed = sidebarCollapsed || tempAutoCollapsed;

  const [showProfileModal, setShowProfileModal] = useState(false);

  const syncTempAutoCollapse = useCallback(
    (layout: RightPanelLayoutSnapshot | null) => {
      activeRightPanelLayoutRef.current = layout;
      const needsCollapse = shouldTemporarilyCollapseNavigation({
        layout,
        viewportWidth: window.innerWidth,
        minimumWorkspaceWithNavigationPx:
          navigationWidthRef.current + MINIMUM_CHAT_WITH_RAIL_PX,
        userOverrode: false,
      });
      if (!needsCollapse) userOverrodeRef.current = false;

      setTempAutoCollapsed(needsCollapse && !userOverrodeRef.current);
    },
    [],
  );

  const handleSetSidebarCollapsed = useCallback(
    (collapsed: boolean | ((prev: boolean) => boolean)) => {
      const prev = sidebarCollapsedRef.current;
      const next =
        typeof collapsed === "function" ? collapsed(prev) : collapsed;

      sidebarCollapsedRef.current = next;
      setSidebarCollapsed(next);

      // Keep an explicit expansion until enough workspace is available again.
      if (!next) {
        const wouldAutoCollapse = shouldTemporarilyCollapseNavigation({
          layout: activeRightPanelLayoutRef.current,
          viewportWidth: window.innerWidth,
          minimumWorkspaceWithNavigationPx:
            navigationWidthRef.current + MINIMUM_CHAT_WITH_RAIL_PX,
          userOverrode: false,
        });
        if (wouldAutoCollapse) userOverrodeRef.current = true;
        setTempAutoCollapsed(false);
      }

      localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(next));
      authApi
        .updateMetadata({ sidebarCollapsed: String(next) })
        .catch(() => {});
    },
    [],
  );

  // Re-evaluate both window resizes and right-panel layout changes.
  useEffect(() => {
    const handleWidthChanged = (event: Event) => {
      syncTempAutoCollapse(
        (event as CustomEvent<RightPanelLayoutSnapshot | null>).detail,
      );
    };
    const handleResize = () => {
      navigationWidthRef.current = readStoredWidth();
      syncTempAutoCollapse(activeRightPanelLayoutRef.current);
    };
    const handleNavigationWidth = (event: Event) => {
      navigationWidthRef.current = (event as CustomEvent<number>).detail;
      syncTempAutoCollapse(activeRightPanelLayoutRef.current);
    };
    window.addEventListener(NAVIGATION_WIDTH_CHANGED_EVENT, handleNavigationWidth);
    window.addEventListener("resize", handleResize);
    window.addEventListener(
      RIGHT_PANEL_WIDTH_CHANGED_EVENT,
      handleWidthChanged,
    );
    syncTempAutoCollapse(getRightPanelLayoutSnapshot());

    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener(NAVIGATION_WIDTH_CHANGED_EVENT, handleNavigationWidth);
      window.removeEventListener(
        RIGHT_PANEL_WIDTH_CHANGED_EVENT,
        handleWidthChanged,
      );
    };
  }, [syncTempAutoCollapse]);

  // Cross-tab / login metadata sync — only update if value actually differs
  useEffect(() => {
    const handler = (e: Event) => {
      const collapsed = (e as CustomEvent).detail as boolean;
      sidebarCollapsedRef.current = collapsed;
      setSidebarCollapsed((prev) => {
        if (prev === collapsed) return prev;
        return collapsed;
      });
      // Metadata sync should not leave a stale temp collapse / override around
      userOverrodeRef.current = false;
      setTempAutoCollapsed(false);
      // Re-evaluate after metadata restore in case a wide panel is open
      queueMicrotask(() => {
        syncTempAutoCollapse(activeRightPanelLayoutRef.current);
      });
    };
    window.addEventListener("sidebar-collapsed-changed", handler);
    return () =>
      window.removeEventListener("sidebar-collapsed-changed", handler);
  }, [syncTempAutoCollapse]);

  useEffect(() => {
    if (typeof document === "undefined") return undefined;

    const rootStyle = document.documentElement.style;
    rootStyle.setProperty(
      APP_TOAST_SIDEBAR_OFFSET_VAR,
      getAppToastSidebarOffset({ sidebarCollapsed: effectiveCollapsed }),
    );

    return () => {
      rootStyle.removeProperty(APP_TOAST_SIDEBAR_OFFSET_VAR);
    };
  }, [effectiveCollapsed]);

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
        sidebarCollapsed={effectiveCollapsed}
        setSidebarCollapsed={handleSetSidebarCollapsed}
        mobileSidebarOpen={mobileSidebarOpen}
        setMobileSidebarOpen={setMobileSidebarOpen}
        onShowProfile={handleShowProfile}
      />
    );
  }

  return (
    <NonChatAppContent
      activeTab={activeTab}
      showProfileModal={showProfileModal}
      onCloseProfileModal={handleCloseProfileModal}
      sidebarCollapsed={effectiveCollapsed}
      setSidebarCollapsed={handleSetSidebarCollapsed}
      mobileSidebarOpen={mobileSidebarOpen}
      setMobileSidebarOpen={setMobileSidebarOpen}
      onShowProfile={handleShowProfile}
    />
  );
}
