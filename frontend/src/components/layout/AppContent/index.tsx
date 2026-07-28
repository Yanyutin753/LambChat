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
import { subscribePersistentToolPanel } from "../../chat/ChatMessage/items/persistentToolPanelState";
import {
  nextTempAutoCollapsed,
  nextUserOverrode,
  notifyRightPanelWidthChanged,
  readDomRightPanelWidthPct,
  RIGHT_PANEL_WIDTH_CHANGED_EVENT,
  WIDE_RIGHT_PANEL_THRESHOLD_PCT,
} from "./rightPanelAutoCollapse";

interface AppContentProps {
  activeTab: TabType;
}

export function AppContent({ activeTab }: AppContentProps) {
  const { versionInfo } = useVersion();
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // Persisted sidebar state — only changes on explicit user action
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    const saved = localStorage.getItem(SIDEBAR_COLLAPSED_STORAGE_KEY);
    return saved !== null ? saved === "true" : false;
  });
  const sidebarCollapsedRef = useRef(sidebarCollapsed);
  sidebarCollapsedRef.current = sidebarCollapsed;

  // Temporary in-memory-only collapse (right panel wide open)
  const [tempAutoCollapsed, setTempAutoCollapsed] = useState(false);
  const userOverrodeRef = useRef(false);

  // Effective collapsed state: persisted OR temporary
  const effectiveCollapsed = sidebarCollapsed || tempAutoCollapsed;

  const [showProfileModal, setShowProfileModal] = useState(false);

  const syncTempAutoCollapse = useCallback(() => {
    const isDesktop = window.matchMedia("(min-width: 640px)").matches;
    const rightPanelWidthPct = readDomRightPanelWidthPct();
    const wideOpen = rightPanelWidthPct >= WIDE_RIGHT_PANEL_THRESHOLD_PCT;

    userOverrodeRef.current = nextUserOverrode({
      userOverrode: userOverrodeRef.current,
      wideOpen,
      userExpanded: false,
    });

    setTempAutoCollapsed(
      nextTempAutoCollapsed({
        isDesktop,
        rightPanelWidthPct,
        userOverrode: userOverrodeRef.current,
      }),
    );
  }, []);

  const handleSetSidebarCollapsed = useCallback(
    (collapsed: boolean | ((prev: boolean) => boolean)) => {
      const prev = sidebarCollapsedRef.current;
      const next =
        typeof collapsed === "function" ? collapsed(prev) : collapsed;

      sidebarCollapsedRef.current = next;
      setSidebarCollapsed(next);

      // User manually expanded while the right panel is wide — stick open
      if (!next) {
        const wideOpen =
          readDomRightPanelWidthPct() >= WIDE_RIGHT_PANEL_THRESHOLD_PCT;
        userOverrodeRef.current = nextUserOverrode({
          userOverrode: userOverrodeRef.current,
          wideOpen,
          userExpanded: true,
        });
        setTempAutoCollapsed(false);
      }

      localStorage.setItem(SIDEBAR_COLLAPSED_STORAGE_KEY, String(next));
      authApi
        .updateMetadata({ sidebarCollapsed: String(next) })
        .catch(() => {});
    },
    [],
  );

  // Temporary auto-collapse: right panel is wide, collapse sidebar visually
  // but do NOT persist — restore automatically when right panel closes/narrows
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 640px)");

    const unsubPanel = subscribePersistentToolPanel(syncTempAutoCollapse);

    const attrObserver = new MutationObserver(syncTempAutoCollapse);
    attrObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-sidebar-preview", "data-editor-sidebar"],
    });

    const handleWidthChanged = () => syncTempAutoCollapse();
    window.addEventListener(
      RIGHT_PANEL_WIDTH_CHANGED_EVENT,
      handleWidthChanged,
    );
    mq.addEventListener("change", handleWidthChanged);

    syncTempAutoCollapse();

    return () => {
      unsubPanel();
      attrObserver.disconnect();
      window.removeEventListener(
        RIGHT_PANEL_WIDTH_CHANGED_EVENT,
        handleWidthChanged,
      );
      mq.removeEventListener("change", handleWidthChanged);
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
        notifyRightPanelWidthChanged();
      });
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
        versionInfo={versionInfo}
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
      versionInfo={versionInfo}
      sidebarCollapsed={effectiveCollapsed}
      setSidebarCollapsed={handleSetSidebarCollapsed}
      mobileSidebarOpen={mobileSidebarOpen}
      setMobileSidebarOpen={setMobileSidebarOpen}
      onShowProfile={handleShowProfile}
    />
  );
}
