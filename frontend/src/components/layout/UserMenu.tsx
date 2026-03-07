import { useRef, useEffect, useState, useCallback } from "react";
import { createPortal } from "react-dom";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  MessageSquare,
  Package,
  LogOut,
  Users,
  Shield,
  Settings,
  Server,
  User,
  Star,
} from "lucide-react";
import { useAuth } from "../../hooks/useAuth";
import { useSettingsContext } from "../../contexts/SettingsContext";
import { Permission } from "../../types";

interface UserMenuProps {
  onShowProfile: () => void;
}

export function UserMenu({ onShowProfile }: UserMenuProps) {
  const { t } = useTranslation();
  const { logout, hasAnyPermission, user } = useAuth();
  const { enableMcp, enableSkills } = useSettingsContext();
  const [showMenu, setShowMenu] = useState(false);
  const [menuPosition, setMenuPosition] = useState({ top: 0, right: 0 });
  const buttonRef = useRef<HTMLButtonElement>(null);
  const navigate = useNavigate();

  const canReadSkills =
    hasAnyPermission([Permission.SKILL_READ]) && enableSkills;
  const canManageUsers = hasAnyPermission([
    Permission.USER_READ,
    Permission.USER_WRITE,
  ]);
  const canManageRoles = hasAnyPermission([Permission.ROLE_MANAGE]);
  const canManageSettings = hasAnyPermission([Permission.SETTINGS_MANAGE]);
  const canReadMCP = hasAnyPermission([Permission.MCP_READ]) && enableMcp;
  const canViewFeedback = hasAnyPermission([Permission.FEEDBACK_READ]);

  // Update menu position
  const updateMenuPosition = useCallback(() => {
    if (buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      setMenuPosition({
        top: rect.bottom + 8, // 8px = mt-2
        right: window.innerWidth - rect.right,
      });
    }
  }, []);

  useEffect(() => {
    const handleClickOutside = () => setShowMenu(false);
    if (showMenu) {
      updateMenuPosition();
      document.addEventListener("click", handleClickOutside);
      window.addEventListener("resize", updateMenuPosition);
      window.addEventListener("scroll", updateMenuPosition, true);
      return () => {
        document.removeEventListener("click", handleClickOutside);
        window.removeEventListener("resize", updateMenuPosition);
        window.removeEventListener("scroll", updateMenuPosition, true);
      };
    }
  }, [showMenu, updateMenuPosition]);

  const handleNavigate = (path: string) => {
    navigate(path);
    setShowMenu(false);
  };

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
  ];

  const systemSettingsItems = [
    {
      path: "/feedback",
      label: t("nav.feedback"),
      icon: Star,
      show: canViewFeedback,
    },
    {
      path: "/settings",
      label: t("nav.systemSettings"),
      icon: Settings,
      show: canManageSettings,
    },
  ];

  const navItems = [
    { path: "/chat", label: t("nav.chat"), icon: MessageSquare, show: true },
    {
      path: "/skills",
      label: t("nav.skills"),
      icon: Package,
      show: canReadSkills,
    },
    { path: "/mcp", label: t("nav.mcp"), icon: Server, show: canReadMCP },
  ];

  return (
    <>
      <div className="relative" onClick={(e) => e.stopPropagation()}>
        <button
          ref={buttonRef}
          onClick={() => setShowMenu(!showMenu)}
          className="flex h-8 w-8 items-center justify-center rounded-full transition-colors overflow-hidden"
        >
          {user?.avatar_url ? (
            <img
              src={user.avatar_url}
              alt={user?.username || "User"}
              className="size-5 object-cover rounded-full"
            />
          ) : (
            <div className="flex size-5 items-center justify-center bg-gradient-to-br from-stone-500 to-stone-700 rounded-full">
              <span className="text-xs font-bold text-white">
                {user?.username?.charAt(0).toUpperCase() || "U"}
              </span>
            </div>
          )}
        </button>

        {showMenu &&
          createPortal(
            <div
              className="fixed z-[100] w-48 sm:w-52 rounded-xl bg-white dark:bg-stone-800 shadow-lg border border-gray-200 dark:border-stone-700 overflow-hidden animate-scale-in"
              style={{
                top: `${menuPosition.top}px`,
                right: `${menuPosition.right}px`,
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <button
                onClick={() => {
                  onShowProfile();
                  setShowMenu(false);
                }}
                className="flex w-full items-center gap-3 px-3 py-1 sm:py-2.5 text-left text-sm text-gray-600 dark:text-stone-300 hover:bg-gray-50 dark:hover:bg-stone-700/50 transition-colors"
              >
                <User size={18} />
                {t("users.user")}
              </button>

              {/* Navigation */}
              <div>
                {navItems
                  .filter((item) => item.show)
                  .map((item) => {
                    const Icon = item.icon;
                    return (
                      <button
                        key={item.path}
                        onClick={() => handleNavigate(item.path)}
                        className="flex w-full items-center gap-3 px-3 py-1 sm:py-2.5 text-left text-sm transition-colors text-gray-600 dark:text-stone-300 hover:bg-gray-50 dark:hover:bg-stone-700/50"
                      >
                        <Icon size={18} />
                        {item.label}
                      </button>
                    );
                  })}
              </div>

              {/* User Management Section */}
              {userSettingsItems.some((item) => item.show) && (
                <div className="border-t border-gray-100 dark:border-stone-700 pt-2 mt-2">
                  <div className="px-3 py-1.5 text-xs font-medium text-gray-400 dark:text-stone-500">
                    {t("nav.userSettings")}
                  </div>
                  {userSettingsItems
                    .filter((item) => item.show)
                    .map((item) => {
                      const Icon = item.icon;
                      return (
                        <button
                          key={item.path}
                          onClick={() => handleNavigate(item.path)}
                          className="flex w-full items-center gap-3 px-3 py-1 sm:py-2.5 text-left text-sm transition-colors text-gray-600 dark:text-stone-300 hover:bg-gray-50 dark:hover:bg-stone-700/50"
                        >
                          <Icon size={18} />
                          {item.label}
                        </button>
                      );
                    })}
                </div>
              )}

              {/* System Settings Section */}
              {systemSettingsItems.some((item) => item.show) && (
                <div className="border-t border-gray-100 dark:border-stone-700 pt-2 mt-2">
                  <div className="px-3 py-1.5 text-xs font-medium text-gray-400 dark:text-stone-500">
                    {t("nav.systemSettings")}
                  </div>
                  {systemSettingsItems
                    .filter((item) => item.show)
                    .map((item) => {
                      const Icon = item.icon;
                      return (
                        <button
                          key={item.path}
                          onClick={() => handleNavigate(item.path)}
                          className="flex w-full items-center gap-3 px-3 py-1 sm:py-2.5 text-left text-sm transition-colors text-gray-600 dark:text-stone-300 hover:bg-gray-50 dark:hover:bg-stone-700/50"
                        >
                          <Icon size={18} />
                          {item.label}
                        </button>
                      );
                    })}
                </div>
              )}

              {/* Logout */}
              <div className="border-t border-gray-100 dark:border-stone-700">
                <button
                  onClick={() => {
                    logout();
                    setShowMenu(false);
                  }}
                  className="flex w-full items-center gap-3 px-3 py-3 text-left text-sm text-gray-600 dark:text-stone-300 hover:bg-gray-50 dark:hover:bg-stone-700/50 transition-colors"
                >
                  <LogOut size={18} />
                  {t("auth.logout")}
                </button>
              </div>
            </div>,
            document.body,
          )}
      </div>
    </>
  );
}
