import { useRef, useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  MessageSquare,
  Package,
  LogOut,
  Users,
  Shield,
  Settings,
  Server,
  Star,
  MessageCircle,
  Bot,
  User,
  ShoppingBag,
  Cpu,
  Bell,
  Brain,
} from "lucide-react";
import { useAuth } from "../../hooks/useAuth";
import { useSettingsContext } from "../../contexts/SettingsContext";
import { Permission } from "../../types";
import {
  beginSessionSelectionGuard,
  clearSessionSelectionGuard,
} from "../../utils/sessionSelectionGuard";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";

interface UserMenuProps {
  onShowProfile: () => void;
}

export function UserMenu({ onShowProfile }: UserMenuProps) {
  const { t } = useTranslation();
  const { logout, hasAnyPermission, user } = useAuth();
  const { enableSkills, enableMemory } = useSettingsContext();
  const navigate = useNavigate();
  const [showMenu, setShowMenu] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ top: 0, right: 0 });
  const [imgError, setImgError] = useState(false);
  const [isMobile, setIsMobile] = useState(
    () => typeof window !== "undefined" && window.innerWidth < 640,
  );
  const buttonRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const location = useLocation();
  const swipeRef = useSwipeToClose({
    onClose: () => setShowMenu(false),
    enabled: showMenu && isMobile,
  });

  const canReadSkills =
    hasAnyPermission([Permission.SKILL_READ]) && enableSkills;
  const canReadMarketplace =
    hasAnyPermission([Permission.MARKETPLACE_READ]) && enableSkills;
  const canManageUsers = hasAnyPermission([
    Permission.USER_READ,
    Permission.USER_WRITE,
  ]);
  const canManageRoles = hasAnyPermission([Permission.ROLE_MANAGE]);
  const canManageSettings = hasAnyPermission([Permission.SETTINGS_MANAGE]);
  const canReadMCP = hasAnyPermission([Permission.MCP_READ]);
  const canViewFeedback = hasAnyPermission([Permission.FEEDBACK_READ]);
  const canReadChannels = hasAnyPermission([Permission.CHANNEL_READ]);
  const canManageAgents = hasAnyPermission([Permission.AGENT_READ]);
  const canManageModels = hasAnyPermission([Permission.MODEL_ADMIN]);
  const canManageNotifications = hasAnyPermission([
    Permission.NOTIFICATION_MANAGE,
  ]);

  // Reactive mobile detection
  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth < 640);
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  // Update menu position (desktop only)
  const updateMenuPosition = useCallback(() => {
    if (buttonRef.current && !isMobile) {
      const rect = buttonRef.current.getBoundingClientRect();
      setMenuPosition({
        top: rect.bottom + 8,
        right: window.innerWidth - rect.right,
      });
    }
  }, [isMobile]);

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
      updateMenuPosition();
      const timer = setTimeout(() => {
        document.addEventListener("click", handleClickOutside);
      }, 0);
      window.addEventListener("resize", updateMenuPosition);
      window.addEventListener("scroll", updateMenuPosition, true);
      return () => {
        clearTimeout(timer);
        document.removeEventListener("click", handleClickOutside);
        window.removeEventListener("resize", updateMenuPosition);
        window.removeEventListener("scroll", updateMenuPosition, true);
      };
    }
  }, [showMenu, updateMenuPosition]);

  // Lock body scroll on mobile when menu is open
  useEffect(() => {
    if (showMenu && isMobile) {
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = "";
      };
    }
  }, [showMenu, isMobile]);

  useEffect(() => {
    if (showMenu) {
      setShowMenu(false);
    }
    clearSessionSelectionGuard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const navItems = [
    { path: "/chat", label: t("nav.chat"), icon: MessageSquare, show: true },
    {
      path: "/skills",
      label: t("nav.skills"),
      icon: Package,
      show: canReadSkills,
    },
    {
      path: "/marketplace",
      label: t("nav.marketplace"),
      icon: ShoppingBag,
      show: canReadMarketplace,
    },
    { path: "/mcp", label: t("nav.mcp"), icon: Server, show: canReadMCP },
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
      show: enableMemory,
    },
  ];

  const userSettingsItems = [
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
      icon: Bot,
      show: canManageAgents,
    },
    {
      path: "/models",
      label: t("nav.models"),
      icon: Cpu,
      show: canManageModels,
    },
  ];

  const systemSettingsItems = [
    {
      path: "/feedback",
      label: t("nav.feedback"),
      icon: Star,
      show: canViewFeedback,
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
  ];

  const visibleNav = navItems.filter((i) => i.show);
  const visibleUser = userSettingsItems.filter((i) => i.show);
  const visibleSys = systemSettingsItems.filter((i) => i.show);

  const menuItemClass =
    "flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)] active:scale-[0.98]";

  const dividerClass = "mx-3 my-1 border-t border-[var(--theme-border)]";

  const renderNavItem = (item: {
    path: string;
    label: string;
    icon: React.ElementType;
  }) => (
    <button
      key={item.path}
      type="button"
      className={`${menuItemClass} ${
        location.pathname === item.path
          ? "bg-[var(--theme-primary-light)] text-[var(--theme-text)]"
          : ""
      }`}
      onMouseDown={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (item.path !== "/chat") {
          beginSessionSelectionGuard(item.path);
        }
      }}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        if (item.path !== "/chat") {
          beginSessionSelectionGuard(item.path);
        }
        setShowMenu(false);
        requestAnimationFrame(() => {
          navigate(item.path);
        });
      }}
    >
      <item.icon size={16} strokeWidth={1.8} />
      <span>{item.label}</span>
    </button>
  );

  const renderMenuContent = () => (
    <>
      {/* Navigation */}
      {visibleNav.length > 0 && <div>{visibleNav.map(renderNavItem)}</div>}

      {/* User Management */}
      {visibleUser.length > 0 && (
        <div>
          {visibleNav.length > 0 && <div className={dividerClass} />}
          {visibleUser.map(renderNavItem)}
        </div>
      )}

      {/* System */}
      {visibleSys.length > 0 && (
        <div>
          {(visibleNav.length > 0 || visibleUser.length > 0) && (
            <div className={dividerClass} />
          )}
          {visibleSys.map(renderNavItem)}
        </div>
      )}

      {/* Bottom actions */}
      <div className="border-t border-[var(--theme-border)] mt-1">
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
        <button
          onClick={() => {
            logout();
            setShowMenu(false);
          }}
          className={`${menuItemClass} text-red-500/70 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-500/10`}
        >
          <LogOut size={16} strokeWidth={1.8} />
          <span className="flex-1">{t("auth.logout")}</span>
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
          className="flex h-8 w-8 items-center justify-center rounded-lg transition-all hover:ring-2 hover:ring-[var(--theme-primary-light)] active:scale-95 overflow-hidden"
        >
          {user?.avatar_url && !imgError ? (
            <img
              src={user.avatar_url}
              alt={user?.username || "User"}
              className="size-5 object-cover rounded-full"
              onError={() => setImgError(true)}
            />
          ) : (
            <div className="flex size-5 items-center justify-center bg-gradient-to-br from-stone-500 to-stone-700 rounded-full">
              <span className="text-xs font-semibold text-white">
                {user?.username?.charAt(0).toUpperCase() || "U"}
              </span>
            </div>
          )}
        </button>

        {showMenu &&
          createPortal(
            isMobile ? (
              // Mobile: bottom sheet with backdrop
              <div
                className="fixed inset-0 z-[100] sm:hidden"
                onClick={() => setShowMenu(false)}
              >
                <div className="fixed inset-0 bg-black/40 animate-fade-in" />
                <div
                  ref={(el) => {
                    menuRef.current = el;
                    swipeRef.current = el;
                  }}
                  className="fixed inset-x-0 bottom-0 z-[101] rounded-t-2xl shadow-2xl max-h-[85vh] overflow-y-auto animate-slide-up-sheet"
                  style={{ backgroundColor: "var(--theme-bg-card)" }}
                  onClick={(e) => e.stopPropagation()}
                >
                  {/* Drag handle */}
                  <div className="flex justify-center pt-3 pb-1">
                    <div className="w-9 h-1 rounded-full bg-[var(--theme-text-secondary)] opacity-25" />
                  </div>
                  {renderMenuContent()}
                  {/* Safe area for iOS */}
                  <div className="h-[env(safe-area-inset-bottom)]" />
                </div>
              </div>
            ) : (
              // Desktop: positioned dropdown
              <>
                <div
                  className="fixed inset-0 z-[300]"
                  onClick={() => setShowMenu(false)}
                />
                <div
                  ref={menuRef}
                  className="fixed z-[301] w-52 rounded-xl shadow-xl border overflow-hidden animate-scale-in"
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
