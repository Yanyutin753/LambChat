import { DialogCloseButton } from "../common/DialogCloseButton";
import { ModalSurface } from "../common/ModalSurface";
import {
  Fragment,
  useCallback,
  useId,
  useRef,
  useEffect,
  useState,
} from "react";
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

import {
  ResourceCardMenu,
  type ResourceCardAction,
} from "../common/ResourceCardMenu";
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
  const menuId = useId();
  const [menuPosition, setMenuPosition] = useState({ x: 0, y: 0 });
  const closeMenu = useCallback((restoreFocus = false) => {
    setShowMenu(false);
    if (restoreFocus) buttonRef.current?.focus({ preventScroll: true });
  }, []);
  const openMenu = () => {
    const rect = buttonRef.current!.getBoundingClientRect();
    setMenuPosition({ x: rect.right - 224, y: rect.bottom + 4 });
    setShowMenu(true);
  };
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
    const handleResize = () => {
      setIsMobile(window.innerWidth < 640);
      setShowMenu(false);
    };
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

  useEffect(() => {
    if (showMenu) {
      setShowMenu(false);
    }
    clearSessionSelectionGuard();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const menuItemClass =
    "flex min-h-11 w-full items-center gap-3 px-4 py-2.5 text-left text-14 transition-colors duration-150 motion-reduce:transition-none rounded-lg text-theme-text-secondary hover:bg-theme-bg-subtle hover:text-theme-text focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]";

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

  const navigationActions = (
    items: typeof adminItems,
    groupLabel: string,
  ): ResourceCardAction[] =>
    items.map((item, index) => ({
      label: item.label,
      icon: <item.icon size={16} strokeWidth={1.8} />,
      onClick: () => navigateTo(item.path),
      current: location.pathname === item.path,
      separatorBefore: index === 0,
      groupLabel: index === 0 ? groupLabel : undefined,
    }));
  const actions: ResourceCardAction[] = [
    {
      label: t("users.user"),
      icon: <User size={16} strokeWidth={1.8} />,
      onClick: () => {
        // Wait for the sheet to unlock its background before the new dialog captures its opener.
        requestAnimationFrame(() => {
          closeMenu(true);
          onShowProfile();
        });
      },
    },
    ...navigationActions(adminItems, t("nav.groupAdmin")),
    ...navigationActions(sysItems, t("nav.groupSystem")),
    {
      label: t("auth.logout"),
      icon: <LogOut size={16} strokeWidth={1.8} />,
      onClick: logout,
      separatorBefore: true,
      danger: true,
    },
  ];

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-label={t("profile.title")}
        aria-haspopup={isMobile ? "dialog" : "menu"}
        aria-expanded={showMenu}
        aria-controls={showMenu ? menuId : undefined}
        onClick={() => (showMenu ? closeMenu() : openMenu())}
        onKeyDown={(event) => {
          if (
            !showMenu &&
            (event.key === "ArrowDown" || event.key === "ArrowUp")
          ) {
            event.preventDefault();
            openMenu();
          }
        }}
        className="flex size-11 sm:size-8 items-center justify-center rounded-lg transition-colors duration-150 motion-reduce:transition-none hover:ring-2 hover:ring-[var(--theme-primary-light)] focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)] overflow-hidden"
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
        (isMobile ? (
          <ModalSurface open onClose={closeMenu} label={t("profile.title")}>
            <div
              id={menuId}
              className="safe-area-bottom max-h-[85dvh] overflow-y-auto bg-theme-bg-card"
            >
              <div className="sticky top-0 z-10 flex items-center justify-between gap-3 bg-theme-bg-card px-4 py-1">
                <span className="min-w-0 truncate text-14 font-medium font-serif text-theme-text">
                  {user?.username || t("common.user")}
                </span>
                <DialogCloseButton onClick={() => closeMenu()} />
              </div>
              <div className="pb-1.5">
                {actions.map((action) => (
                  <Fragment key={action.label}>
                    {action.separatorBefore && (
                      <div
                        role="separator"
                        className="mx-4 my-1.5 border-t border-theme-border"
                      />
                    )}
                    {action.groupLabel && (
                      <div className="px-4 pt-2 pb-1 text-12 font-medium text-theme-text-secondary">
                        {action.groupLabel}
                      </div>
                    )}
                    <button
                      type="button"
                      aria-current={action.current ? "page" : undefined}
                      className={`${menuItemClass} ${action.current ? "bg-theme-bg-subtle font-medium" : ""} ${action.danger ? "!text-theme-error hover:bg-[color-mix(in_srgb,var(--theme-error)_10%,transparent)]" : ""}`}
                      onClick={() => {
                        closeMenu();
                        action.onClick?.();
                      }}
                    >
                      {action.icon}
                      <span className="min-w-0 break-words">
                        {action.label}
                      </span>
                    </button>
                  </Fragment>
                ))}
              </div>
            </div>
          </ModalSurface>
        ) : (
          <ResourceCardMenu
            id={menuId}
            title={t("profile.title")}
            actions={actions}
            position={menuPosition}
            onClose={closeMenu}
          />
        ))}
    </div>
  );
}
