import { ModalSurface } from "../common/ModalSurface";
import { useRef, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  LogOut,
  User,
  Users,
  Shield,
  Settings2,
  Star,
  Bell,
  Settings,
  BarChart3,
} from "lucide-react";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import { clearSessionSelectionGuard } from "../../utils/sessionSelectionGuard";

import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import { getFullUrl } from "../../services/api";
import { ImageWithSkeleton } from "../chat/ChatMessage/ImageWithSkeleton";

interface UserMenuProps {
  onShowProfile: () => void;
}

export function UserMenu({ onShowProfile }: UserMenuProps) {
  const { t } = useTranslation();
  const { logout, hasAnyPermission, user } = useAuth();
  const navigate = useNavigate();
  const [showMenu, setShowMenu] = useState(false);
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && window.innerWidth < 640,
  );
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const location = useLocation();

  const canManageUsers = hasAnyPermission([
    Permission.USER_READ,
    Permission.USER_WRITE,
  ]);
  const canManageRoles = hasAnyPermission([Permission.ROLE_MANAGE]);
  const canManageAgents = hasAnyPermission([Permission.AGENT_ADMIN]);
  const canManageModels = hasAnyPermission([Permission.MODEL_ADMIN]);
  const canViewFeedback = hasAnyPermission([Permission.FEEDBACK_READ]);
  const canViewUsage = hasAnyPermission([Permission.USAGE_READ]);
  const canManageNotifications = hasAnyPermission([
    Permission.NOTIFICATION_MANAGE,
  ]);
  const canManageSettings = hasAnyPermission([Permission.SETTINGS_MANAGE]);

  // Reactive mobile detection
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 640);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Position dropdown once on open, never recalculate (desktop only)
  const menuPosition = useStickyDropdownPosition(
    buttonRef,
    showMenu && !isMobile,
    (rect) => ({
      top: rect.bottom + 8,
      right: window.innerWidth - rect.right,
    }),
  );

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        menuRef.current &&
        !menuRef.current.contains(target) &&
        buttonRef.current &&
        !buttonRef.current.contains(target)
      ) {
        setShowMenu(false);
      }
    };
    if (showMenu) {
      const timer = setTimeout(() => {
        document.addEventListener("click", handleClickOutside);
      }, 0);
      return () => {
        clearTimeout(timer);
        document.removeEventListener("click", handleClickOutside);
      };
    }
  }, [showMenu, isMobile]);

  // Lock body scroll on mobile when menu is open

  useEffect(() => {
    if (showMenu) {
      setShowMenu(false);
    }
    clearSessionSelectionGuard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const menuItemClass =
    "flex w-full items-center gap-3 px-4 py-2.5 text-left text-14 transition-all duration-150 rounded-lg text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] active:scale-[0.98]";

  const navigateTo = (path: string) => {
    setShowMenu(false);
    requestAnimationFrame(() => {
      navigate(path);
    });
  };

  const adminItems = [
    {
      path: "/users",
      label: t("nav.users"),
      icon: Users,
      show: canManageUsers,
    },
    {
      path: "/roles",
      label: t("nav.roles"),
      icon: Shield,
      show: canManageRoles,
    },
    {
      path: "/agents",
      label: t("nav.agents"),
      icon: Settings2,
      show: canManageAgents || canManageModels,
    },
  ].filter((i) => i.show);

  const sysItems = [
    {
      path: "/feedback",
      label: t("nav.feedback"),
      icon: Star,
      show: canViewFeedback,
    },
    {
      path: "/usage",
      label: t("nav.usage"),
      icon: BarChart3,
      show: canViewUsage,
    },
    {
      path: "/notifications",
      label: t("nav.notifications"),
      icon: Bell,
      show: canManageNotifications,
    },
    {
      path: "/settings",
      label: t("nav.systemSettings"),
      icon: Settings,
      show: canManageSettings,
    },
  ].filter((i) => i.show);

  const hasAdminSection = adminItems.length > 0;
  const hasSysSection = sysItems.length > 0;

  const renderMenuContent = () => (
    <>
      <div className="py-1.5">
        {/* Personal section */}
        <button
          onClick={() => {
            onShowProfile();
            setShowMenu(false);
          }}
          className={menuItemClass}
        >
          <User size={16} strokeWidth={1.8} />
          <span>{t("users.user")}</span>
        </button>

        {/* Admin section */}
        {hasAdminSection && (
          <>
            <div className="mx-4 my-1.5 border-t border-[var(--theme-border)]" />
            <div className="px-4 pt-1 pb-1">
              <span className="text-10 font-semibold uppercase tracking-widest text-[var(--theme-text-secondary)] opacity-40">
                {t("nav.groupAdmin")}
              </span>
            </div>
            {adminItems.map((item) => (
              <button
                key={item.path}
                onClick={() => navigateTo(item.path)}
                className={`${menuItemClass} ${
                  location.pathname === item.path
                    ? "text-[var(--theme-text)] font-medium"
                    : ""
                }`}
              >
                <item.icon size={16} strokeWidth={1.8} />
                <span>{item.label}</span>
              </button>
            ))}
          </>
        )}

        {/* System section */}
        {hasSysSection && (
          <>
            <div className="mx-4 my-1.5 border-t border-[var(--theme-border)]" />
            <div className="px-4 pt-1 pb-1">
              <span className="text-10 font-semibold uppercase tracking-widest text-[var(--theme-text-secondary)] opacity-40">
                {t("nav.groupSystem")}
              </span>
            </div>
            {sysItems.map((item) => (
              <button
                key={item.path}
                onClick={() => navigateTo(item.path)}
                className={`${menuItemClass} ${
                  location.pathname === item.path
                    ? "text-[var(--theme-text)] font-medium"
                    : ""
                }`}
              >
                <item.icon size={16} strokeWidth={1.8} />
                <span>{item.label}</span>
              </button>
            ))}
          </>
        )}

        <div className="mx-4 my-1.5 border-t border-[var(--theme-border)]" />
        <button
          onClick={() => {
            logout();
            setShowMenu(false);
          }}
          className={`${menuItemClass} text-red-500/70 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10`}
        >
          <LogOut size={16} strokeWidth={1.8} />
          <span>{t("auth.logout")}</span>
        </button>
      </div>
    </>
  );

  return (
    <>
      <div className="relative">
        <button
          ref={buttonRef}
          onClick={() => setShowMenu(!showMenu)}
          className="flex size-11 sm:size-8 items-center justify-center rounded-lg transition-all hover:ring-2 hover:ring-[var(--theme-primary-light)] active:scale-95 overflow-hidden"
        >
          {user?.avatar_url ? (
            <ImageWithSkeleton
              src={getFullUrl(user.avatar_url) ?? user.avatar_url}
              alt={user?.username || t("common.user")}
              skipUrlResolve
              inline
              className="size-5 rounded-full"
              errorFallback={
                <div className="flex size-5 items-center justify-center bg-gradient-to-br from-amber-400 to-orange-500 rounded-full">
                  <span className="text-12 font-semibold text-white font-serif">
                    {user?.username?.charAt(0).toUpperCase() || "U"}
                  </span>
                </div>
              }
            />
          ) : (
            <div className="flex size-5 items-center justify-center bg-gradient-to-br from-amber-400 to-orange-500 rounded-full">
              <span className="text-12 font-semibold text-white font-serif">
                {user?.username?.charAt(0).toUpperCase() || "U"}
              </span>
            </div>
          )}
        </button>

        {showMenu &&
          createPortal(
            isMobile ? (
              <ModalSurface
                open
                onClose={() => setShowMenu(false)}
                label={t("profile.title")}
              >
                <div
                  ref={menuRef}
                  className="safe-area-bottom rounded-t-2xl shadow-2xl max-h-[85dvh] overflow-y-auto animate-slide-up-sheet"
                  style={{ backgroundColor: "var(--theme-bg-card)" }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {renderMenuContent()}
                </div>
              </ModalSurface>
            ) : (
              // Desktop: positioned dropdown
              <>
                <div
                  className="fixed inset-0 z-[300]"
                  onClick={() => setShowMenu(false)}
                />
                <div
                  ref={menuRef}
                  className="fixed z-[301] w-56 rounded-xl shadow-xl border overflow-hidden animate-scale-in"
                  style={{
                    top: `${menuPosition.top}px`,
                    right: `${menuPosition.right}px`,
                    backgroundColor: "var(--theme-bg-card)",
                    borderColor: "var(--theme-border)",
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {renderMenuContent()}
                </div>
              </>
            ),
            document.body,
          )}
      </div>
    </>
  );
}
