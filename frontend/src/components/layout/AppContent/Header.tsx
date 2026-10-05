import { SceneIllustration } from "../../common/SceneIllustration";
import { useState, useRef, useEffect, useCallback, useId } from "react";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ResourceCardMenu,
  type ResourceCardAction,
} from "../../common/ResourceCardMenu";
import {
  Share2,
  MoreHorizontal,
  SquarePen,
  Bell,
  Languages,
  Sun,
  Moon,
  Coffee,
  Check,
  ChevronLeft,
  ListTree,
  RefreshCw,
  AlertCircle,
} from "lucide-react";
import { ToolbarIconButton } from "../../common/ui/ToolbarIconButton";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { ModelSelector } from "../../agent/ModelSelector";
import { UserMenu } from "../UserMenu";
import { ShareDialog } from "../../share/ShareDialog";
import { useAuth } from "../../../hooks/useAuth";
import { useTheme } from "../../../contexts/ThemeContext";
import { useSettingsContext } from "../../../contexts/SettingsContext";
import { useLanguagePreference } from "../../../hooks/useLanguagePreference";
import { notificationApi } from "../../../services/api/notification";
import { useSessionTitle } from "../../../hooks/useSessionTitle";
import { NotificationDialog } from "../../notification/NotificationDialog";
import {
  OPEN_NOTIFICATIONS_EVENT,
  NOTIFICATION_COUNT_EVENT,
} from "../DesktopSidebarShell/desktopShellPlatform";
import { Permission } from "../../../types";
import type { TabType } from "./types";
import type { Project } from "../../../types";

interface HeaderProps {
  activeTab: TabType;
  headerActions?: ReactNode;
  setMobileSidebarOpen: (open: boolean) => void;
  currentProjectId: string | null;
  projectManager: { projects: Project[] };
  onNewSession: () => void;
  onShowProfile: () => void;
  availableModels?:
    | {
        id: string;
        value: string;
        provider?: string;
        label: string;
        description?: string;
      }[]
    | null;
  currentModelId?: string;
  onSelectModel?: (modelId: string, modelValue: string) => void;
  sessionId?: string | null;
  onToggleOutline?: () => void;
  showOutlineButton?: boolean;
}

export function Header({
  activeTab,
  headerActions,
  setMobileSidebarOpen,
  currentProjectId,
  projectManager,
  onNewSession,
  onShowProfile,
  availableModels,
  currentModelId,
  onSelectModel,
  sessionId,
  onToggleOutline,
  showOutlineButton,
}: HeaderProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { languageState, selectLanguage, retryLanguage } =
    useLanguagePreference();
  const { theme, toggleTheme, appearanceState, retryAppearance } = useTheme();
  const {
    pinnedModelIds,
    togglePinnedModel,
    modelsLoading,
    modelsError,
    reloadModels,
  } = useSettingsContext();
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [notifDialogOpen, setNotifDialogOpen] = useState(false);
  const [activeNotifCount, setActiveNotifCount] = useState(0);
  const mobileMenuBtnRef = useRef<HTMLButtonElement>(null);
  const menuId = useId();
  const [menu, setMenu] = useState<{
    mode: "main" | "language";
    position: { x: number; y: number };
    returningFromLanguage: boolean;
  } | null>(null);
  const closeMenu = useCallback((restoreFocus = false) => {
    setMenu(null);
    if (restoreFocus) mobileMenuBtnRef.current?.focus();
  }, []);
  const openMenu = (
    mode: "main" | "language",
    returningFromLanguage = false,
  ) => {
    const rect = mobileMenuBtnRef.current!.getBoundingClientRect();
    setMenu({
      mode,
      position: { x: rect.right - 224, y: rect.bottom + 4 },
      returningFromLanguage,
    });
  };

  const refreshNotifCount = () => {
    notificationApi
      .getActive()
      .then((items) => {
        setActiveNotifCount(items.length);
        window.dispatchEvent(
          new CustomEvent(NOTIFICATION_COUNT_EVENT, { detail: items.length }),
        );
      })
      .catch(() => {});
  };

  useEffect(() => {
    refreshNotifCount();
    const open = () => {
      closeMenu();
      setNotifDialogOpen(true);
    };
    window.addEventListener(OPEN_NOTIFICATIONS_EVENT, open);
    return () => window.removeEventListener(OPEN_NOTIFICATIONS_EVENT, open);
  }, [closeMenu]);

  const hasSharePermission = user?.permissions?.includes(
    Permission.SESSION_SHARE,
  );
  const showShareButton = !!sessionId && hasSharePermission;
  const sessionTitle = useSessionTitle(sessionId, {
    enabled: showShareButton,
  });

  const mainActions: ResourceCardAction[] = [
    ...(showOutlineButton && onToggleOutline
      ? [
          {
            label: t("chat.outline"),
            icon: <ListTree size={16} />,
            onClick: onToggleOutline,
          },
        ]
      : []),
    ...(activeTab === "chat"
      ? [
          {
            label: t("sidebar.newChat"),
            icon: <SquarePen size={16} />,
            onClick: onNewSession,
          },
        ]
      : []),
    ...(showShareButton
      ? [
          {
            label: t("share.title"),
            icon: <Share2 size={16} strokeWidth={1.8} />,
            onClick: () => setShareDialogOpen(true),
          },
        ]
      : []),
    {
      label:
        t("nav.notifications") +
        (activeNotifCount > 0
          ? ` (${activeNotifCount > 99 ? "99+" : activeNotifCount})`
          : ""),
      icon: <Bell size={16} />,
      onClick: () => setNotifDialogOpen(true),
    },
    {
      label:
        appearanceState === "error"
          ? `${t("common.retry")}: ${t("profile.theme")}`
          : appearanceState === "saving"
            ? t("common.saving")
            : theme === "light"
              ? t("theme.switchToDark")
              : theme === "dark"
                ? t("theme.switchToSepia")
                : t("theme.switchToLight"),
      icon:
        appearanceState === "error" ? (
          <AlertCircle size={16} className="text-theme-error" />
        ) : appearanceState === "saving" ? (
          <LoadingSpinner size="sm" />
        ) : theme === "light" ? (
          <Moon size={16} />
        ) : theme === "dark" ? (
          <Coffee size={16} />
        ) : (
          <Sun size={16} />
        ),
      disabled: appearanceState === "saving",
      onClick: appearanceState === "error" ? retryAppearance : toggleTheme,
    },
    {
      label:
        languageState === "error"
          ? `${t("common.retry")}: ${t("common.language")}`
          : languageState === "saving"
            ? `${t("common.language")} · ${t("common.saving")}`
            : t("common.language"),
      groupLabel:
        languageState === "error"
          ? t("profile.preferenceSyncFailed")
          : undefined,
      icon:
        languageState === "saving" ? (
          <LoadingSpinner size="sm" />
        ) : languageState === "error" ? (
          <AlertCircle size={16} className="text-theme-error" />
        ) : (
          <Languages size={16} />
        ),
      disabled: languageState === "saving",
      onClick:
        languageState === "error" ? retryLanguage : () => openMenu("language"),
    },
  ];
  const languageActions: ResourceCardAction[] = [
    {
      label: t("common.back"),
      icon: <ChevronLeft size={16} />,
      onClick: () => openMenu("main", true),
    },
    ...[
      { code: "en", name: "English" },
      { code: "zh", name: "中文" },
      { code: "ja", name: "日本語" },
      { code: "ko", name: "한국어" },
      { code: "ru", name: "Русский" },
    ].map((lang) => {
      const checked = i18n.language?.split("-")[0] === lang.code;
      return {
        label: lang.name,
        checked,
        disabled: languageState === "saving",
        icon: (
          <Check
            size={16}
            aria-hidden="true"
            className={checked ? "" : "invisible"}
          />
        ),
        onClick: () => {
          selectLanguage(lang.code);
        },
      };
    }),
  ];

  return (
    <>
      <header className="chat-header relative z-50 flex items-center px-3 sm:px-5 py-3 -mb-2 max-sm:h-12 max-sm:py-0 max-sm:mb-0 shrink-0 rounded-bl-xl after:pointer-events-none after:absolute after:inset-x-0 after:bottom-0 after:h-2 after:bg-[linear-gradient(to_bottom,var(--theme-bg),transparent)]">
        <div className="chat-header__identity flex min-w-0 items-center gap-2 flex-shrink">
          <button
            type="button"
            onClick={() => setMobileSidebarOpen(true)}
            className={`flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-[var(--color-background-muted)] dark:text-stone-300 sm:hidden transition-colors`}
            title={t("sidebar.expandSidebar")}
            aria-label={t("sidebar.expandSidebar")}
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
              className="w-5 h-5"
            >
              <path
                fillRule="evenodd"
                clipRule="evenodd"
                d="M8.85719 3H15.1428C16.2266 2.99999 17.1007 2.99998 17.8086 3.05782C18.5375 3.11737 19.1777 3.24318 19.77 3.54497C20.7108 4.02433 21.4757 4.78924 21.955 5.73005C22.2568 6.32234 22.3826 6.96253 22.4422 7.69138C22.5 8.39925 22.5 9.27339 22.5 10.3572V13.6428C22.5 14.7266 22.5 15.6008 22.4422 16.3086C22.3826 17.0375 22.2568 17.6777 21.955 18.27C21.4757 19.2108 20.7108 19.9757 19.77 20.455C19.1777 20.7568 18.5375 20.8826 17.8086 20.9422C17.1008 21 16.2266 21 15.1428 21H8.85717C7.77339 21 6.89925 21 6.19138 20.9422C5.46253 20.8826 4.82234 20.7568 4.23005 20.455C3.28924 19.9757 2.52433 19.2108 2.04497 18.27C1.74318 17.6777 1.61737 17.0375 1.55782 16.3086C1.49998 15.6007 1.49999 14.7266 1.5 13.6428V10.3572C1.49999 9.27341 1.49998 8.39926 1.55782 7.69138C1.61737 6.96253 1.74318 6.32234 2.04497 5.73005C2.52433 4.78924 3.28924 4.02433 4.23005 3.54497C4.82234 3.24318 5.46253 3.11737 6.19138 3.05782C6.89926 2.99998 7.77341 2.99999 8.85719 3ZM6.35424 5.05118C5.74907 5.10062 5.40138 5.19279 5.13803 5.32698C4.57354 5.6146 4.1146 6.07354 3.82698 6.63803C3.69279 6.90138 3.60062 7.24907 3.55118 7.85424C3.50078 8.47108 3.5 9.26339 3.5 10.4V13.6C3.5 14.7366 3.50078 15.5289 3.55118 16.1458C3.60062 16.7509 3.69279 17.0986 3.82698 17.362C4.1146 17.9265 4.57354 18.3854 5.13803 18.673C5.40138 18.8072 5.74907 18.8994 6.35424 18.9488C6.97108 18.9992 7.76339 19 8.9 19H9.5V5H8.9C7.76339 5 6.97108 5.00078 6.35424 5.05118ZM11.5 5V19H15.1C16.2366 19 17.0289 18.9992 17.6458 18.9488C18.2509 18.8994 18.5986 18.8072 18.862 18.673C19.4265 18.3854 19.8854 17.9265 20.173 17.362C20.3072 17.0986 20.3994 16.7509 20.4488 16.1458C20.4992 15.5289 20.5 14.7366 20.5 13.6V10.4C20.5 9.26339 20.4992 8.47108 20.4488 7.85424C20.3994 7.24907 20.3072 6.90138 20.173 6.63803C19.8854 6.57354 19.4265 6.1146 18.862 5.32698C18.5986 5.19279 18.2509 5.10062 17.6458 5.05118C17.0289 5.00078 16.2366 5 15.1 5H11.5ZM5 8.5C5 7.94772 5.44772 7.5 6 7.5H7C7.55229 7.5 8 7.94772 8 8.5C8 9.05229 7.55229 9.5 7 9.5H6C5.44772 9.5 5 9.05229 5 8.5ZM5 12C5 11.4477 5.44772 11 6 11H7C7.55229 11 8 11.4477 8 12C8 12.5523 7.55229 13 7 13H6C5.44772 13 5 12.4477 5 12Z"
                fill="currentColor"
              />
            </svg>
          </button>
          {activeTab === "chat" ? (
            <>
              {onSelectModel && (modelsLoading || modelsError) && (
                <ToolbarIconButton
                  disabled={modelsLoading}
                  aria-label={`${t("nav.models")} · ${t(modelsLoading ? "common.loading" : "common.loadFailed")}${modelsLoading ? "" : ` · ${t("common.retry")}`}`}
                  title={`${t("nav.models")} · ${t(modelsLoading ? "common.loading" : "common.loadFailed")}`}
                  onClick={() => {
                    mobileMenuBtnRef.current?.focus({ preventScroll: true });
                    reloadModels();
                  }}
                  icon={
                    modelsLoading ? (
                      <LoadingSpinner size="sm" />
                    ) : (
                      <RefreshCw size={16} aria-hidden="true" />
                    )
                  }
                />
              )}
              {availableModels &&
                availableModels.length > 0 &&
                onSelectModel && (
                  <ModelSelector
                    models={availableModels}
                    currentModelId={currentModelId || ""}
                    pinnedModelIds={pinnedModelIds}
                    onTogglePinnedModel={togglePinnedModel}
                    onSelectModel={onSelectModel}
                  />
                )}

              {currentProjectId &&
                (() => {
                  const project = projectManager.projects.find(
                    (p) => p.id === currentProjectId,
                  );
                  if (!project) return null;
                  return (
                    <div className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-[var(--color-background-muted)] border border-[var(--color-border)]">
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                        className="size-3 text-[var(--color-text-tertiary)]"
                      >
                        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14z" />
                      </svg>
                      <span className="text-12 text-[var(--color-text-secondary)] truncate max-w-[120px]">
                        {project.name}
                      </span>
                    </div>
                  );
                })()}
            </>
          ) : (
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => navigate(-1)}
                className="hidden sm:flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-secondary)] hover:bg-[var(--color-background-muted)] transition-colors"
                title={t("common.back")}
              >
                <ChevronLeft size={20} />
              </button>
              <SceneIllustration
                scene={`panel-${
                  activeTab === "scheduled-tasks" ? "schedule" : activeTab
                }`}
                className="panel-nav-avatar"
              />
              <div className="flex flex-col justify-center">
                <span className="text-16 font-bold text-[var(--color-text-primary)] font-serif leading-tight">
                  {t(`nav.${activeTab}`, { defaultValue: activeTab })}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Right */}
        <div className="chat-header__actions flex items-center gap-0 sm:gap-1 flex-shrink-0">
          {/* Overflow menu (unified for all screen sizes) */}
          <div className="relative">
            <button
              ref={mobileMenuBtnRef}
              type="button"
              aria-label={t("common.menu")}
              aria-haspopup="menu"
              aria-expanded={!!menu}
              aria-controls={menu ? `${menuId}-${menu.mode}` : undefined}
              onClick={() => {
                if (menu) closeMenu();
                else openMenu("main");
              }}
              className="flex size-11 sm:size-8 items-center justify-center rounded-lg text-stone-600 hover:bg-[var(--color-background-muted)] dark:text-stone-300 transition-colors"
              title={t("common.menu")}
            >
              <MoreHorizontal size={20} />
            </button>
            {menu && (
              <ResourceCardMenu
                id={`${menuId}-${menu.mode}`}
                title={t(
                  menu.mode === "language" ? "common.language" : "common.menu",
                )}
                position={menu.position}
                onClose={closeMenu}
                actions={
                  menu.mode === "language" ? languageActions : mainActions
                }
                initialFocusIndex={
                  menu.returningFromLanguage ? mainActions.length - 1 : 0
                }
              />
            )}
          </div>

          {headerActions}
          <UserMenu onShowProfile={onShowProfile} />
        </div>
      </header>

      {sessionId && (
        <ShareDialog
          isOpen={shareDialogOpen}
          onClose={() => setShareDialogOpen(false)}
          sessionId={sessionId}
          sessionName={sessionTitle || t("sidebar.newChat")}
        />
      )}

      <NotificationDialog
        isOpen={notifDialogOpen}
        onClose={() => setNotifDialogOpen(false)}
        onDismissed={refreshNotifCount}
      />
    </>
  );
}
