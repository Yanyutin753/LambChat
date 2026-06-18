/**
 * Hook encapsulating the "More" menu state, feature items, positioning,
 * and side effects (click-outside, pathname-close, swipe-to-close).
 */

import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { useAuth } from "./useAuth";
import { useSettingsContext } from "../contexts/SettingsContext";
import {
  buildSidebarMoreNavContributions,
  type PluginRuntimeContributionStates,
} from "../extensions/coreContributions";
import { useSwipeToClose } from "./useSwipeToClose";

interface UseMoreMenuParams {
  isCollapsed: boolean;
  isMobile: boolean;
  runtimePlugins?: PluginRuntimeContributionStates;
}

export function useMoreMenu({
  isCollapsed,
  isMobile,
  runtimePlugins,
}: UseMoreMenuParams) {
  const { t } = useTranslation();
  const { hasAnyPermission } = useAuth();
  const { enableMemory } = useSettingsContext();
  const location = useLocation();

  const moreMenuFeatureItems = buildSidebarMoreNavContributions(runtimePlugins).map((item) => ({
    path: item.path,
    label: item.fallbackLabel
      ? t(item.labelKey, item.fallbackLabel)
      : t(item.labelKey),
    icon: item.icon,
    show:
      item.requiresSetting === "memory"
        ? enableMemory
        : !item.requiredAnyPermissions ||
          hasAnyPermission([...item.requiredAnyPermissions]),
  }));

  const hasMoreMenuItems = moreMenuFeatureItems.some((i) => i.show);

  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState(false);
  const [moreMenuPosition, setMoreMenuPosition] = useState<{
    top: number;
    left: number;
  } | null>(null);

  const moreMenuRef = useRef<HTMLDivElement>(null);
  const moreMenuBtnRef = useRef<HTMLButtonElement>(null);
  const expandedMoreMenuBtnRef = useRef<HTMLButtonElement>(null);
  const moreMenuDragHandleRef = useRef<HTMLDivElement>(null);

  const activeMoreMenuBtnRef = isCollapsed
    ? moreMenuBtnRef
    : expandedMoreMenuBtnRef;

  const moreMenuSwipeRef = useSwipeToClose({
    onClose: () => setIsMoreMenuOpen(false),
    enabled: isMoreMenuOpen && isMobile,
    dragHandleRef: moreMenuDragHandleRef,
  });

  // Close menu on pathname change
  useEffect(() => {
    if (isMoreMenuOpen) setIsMoreMenuOpen(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  // Click outside to close
  useEffect(() => {
    if (!isMoreMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (activeMoreMenuBtnRef.current?.contains(e.target as Node)) return;
      if (moreMenuRef.current?.contains(e.target as Node)) return;
      setIsMoreMenuOpen(false);
    };
    // Defer by one frame so the opening click event has finished bubbling
    // and the menu DOM is mounted.
    const id = requestAnimationFrame(() => {
      document.addEventListener("click", handleClickOutside);
    });
    return () => {
      cancelAnimationFrame(id);
      document.removeEventListener("click", handleClickOutside);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isMoreMenuOpen]);

  // Position calculation
  useEffect(() => {
    if (!isMoreMenuOpen) {
      setMoreMenuPosition(null);
      return;
    }
    if (!activeMoreMenuBtnRef.current) return;
    const rect = activeMoreMenuBtnRef.current.getBoundingClientRect();
    const panelWidth = 208;
    const panelMaxHeight = 480;
    let top = rect.top;
    let left = rect.right + 2;
    if (left + panelWidth > window.innerWidth)
      left = window.innerWidth - panelWidth - 8;
    if (left < 8) left = 8;
    if (top + panelMaxHeight > window.innerHeight)
      top = window.innerHeight - panelMaxHeight - 8;
    if (top < 8) top = 8;
    setMoreMenuPosition({ top, left });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isMoreMenuOpen, isCollapsed]);

  return {
    moreMenuFeatureItems,
    hasMoreMenuItems,
    isMoreMenuOpen,
    setIsMoreMenuOpen,
    moreMenuRef,
    moreMenuBtnRef,
    expandedMoreMenuBtnRef,
    moreMenuSwipeRef,
    moreMenuDragHandleRef,
    moreMenuPosition,
  };
}
