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
  Star,
  MessageCircle,
  Bot,
  User,
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
  const [imgError, setImgError] = useState(false);
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
  const canManageAgents = hasAnyPermission([Permission.AGENT_ADMIN]);

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
    {
      path: "/agents",
      label: t("nav.agents"),
      icon: Bot,
      show: canManageAgents,
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
    {
      path: "/channels",
      label: t("nav.channels"),
      icon: MessageCircle,
      show: true,
    },
  ];

  const visibleNav = navItems.filter((i) => i.show);
  const visibleUser = userSettingsItems.filter((i) => i.show);
  const visibleSys = systemSettingsItems.filter((i) => i.show);
  const allItems = [...visibleNav, ...visibleUser, ...visibleSys];

  const menuItems = (
    <div>
      {allItems.map((item, idx) => {
        const needDivider =
          idx > 0 &&
          (visibleNav.length === idx ||
            visibleNav.length + visibleUser.length === idx);
        return (
          <div key={item.path}>
            {needDivider && (
              <div
                className="mx-2 border-t"
                style={{ borderColor: "var(--theme-border)" }}
              />
            )}
            <button
              onClick={() => handleNavigate(item.path)}
              className="flex w-full items-center gap-2.5 px-3 text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)]"
            >
              <item.icon size={16} />
              {item.label}
            </button>
          </div>
        );
      })}
    </div>
  );

  return (
    <>
      <div className="relative" onClick={(e) => e.stopPropagation()}>
        <button
          ref={buttonRef}
          onClick={() => setShowMenu(!showMenu)}
          className="flex h-8 w-8 items-center justify-center rounded-lg transition-colors overflow-hidden"
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
            <div
              className="fixed z-[100] w-52 rounded-xl shadow-lg border overflow-hidden animate-scale-in"
              style={{
                top: `${menuPosition.top}px`,
                right: `${menuPosition.right}px`,
                backgroundColor: "var(--theme-bg-card)",
                borderColor: "var(--theme-border)",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {menuItems}

              {/* Bottom: Profile + Logout */}
              <div
                className="border-t pt-1"
                style={{ borderColor: "var(--theme-border)" }}
              >
                <button
                  onClick={() => {
                    onShowProfile();
                    setShowMenu(false);
                  }}
                  className="flex w-full items-center gap-2.5 px-3 text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)]"
                >
                  <User size={16} />
                  {t("users.user")}
                </button>
                <button
                  onClick={() => {
                    logout();
                    setShowMenu(false);
                  }}
                  className="flex w-full items-center gap-2.5 px-3 text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)]"
                >
                  <LogOut size={16} />
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
