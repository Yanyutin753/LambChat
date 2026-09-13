/**
 * Hook encapsulating the "More" menu state, feature items, positioning,
 * and side effects (click-outside, pathname-close, swipe-to-close).
 */

import { useState, useEffect, useRef } from "react";
import {
  Server,
  Brain,
  MessageCircle,
  Sparkles,
  UserRound,
  Users,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useStickyDropdownPosition } from "./useStickyDropdownPosition";
import { useLocation } from "react-router-dom";
import { useAuth } from "./useAuth";
import { useSettingsContext } from "../contexts/SettingsContext";
import { Permission } from "../types";
import { useSwipeToClose } from "./useSwipeToClose";

interface UseMoreMenuParams {
  isCollapsed: boolean;
  isMobile: boolean;
}

export function useMoreMenu({ isCollapsed, isMobile }: UseMoreMenuParams) {
  const { t } = useTranslation();
  const { hasAnyPermission } = useAuth();
  const { enableMemory } = useSettingsContext();
  const location = useLocation();

  const canReadMCP = hasAnyPermission([Permission.MCP_READ]);
  const canReadChannels = hasAnyPermission([Permission.CHANNEL_READ]);
  const canReadMemory = enableMemory;
  const canReadSkills = hasAnyPermission([Permission.SKILL_READ]);
  const canReadTeam = hasAnyPermission([Permission.TEAM_READ]);

  const moreMenuFeatureItems = [
    {
      path: "/persona",
      label: t("personaPresets.title", "角色广场"),
      icon: UserRound,
      show: true,
    },
    {
      path: "/team",
      label: t("nav.team", "团队构建"),
      icon: Users,
      show: canReadTeam,
    },
    {
      path: "/skills",
      label: t("nav.skills"),
      icon: Sparkles,
      show: canReadSkills,
    },
    {
      path: "/mcp",
      label: t("nav.mcp"),
      icon: Server,
      show: canReadMCP,
    },
    {
      path: "/channels",
      label: t("nav.channels"),
      icon: MessageCircle,
      show: canReadChannels,
    },
    {
      path: "/memory",
      label: t("nav.memory"),
      icon: Brain,
      show: canReadMemory,
    },
  ];

  const hasMoreMenuItems = moreMenuFeatureItems.some((i) => i.show);

  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState(false);

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
  const moreMenuPosition = useStickyDropdownPosition(
    activeMoreMenuBtnRef,
    isMoreMenuOpen,
    (rect) => {
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
      return { top, left };
    },
  );

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
