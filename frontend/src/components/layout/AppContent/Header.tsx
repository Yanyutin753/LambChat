import { SidebarToggleIcon } from "../../common/SidebarToggleIcon";
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
  DESKTOP_SIDEBAR_TOGGLE_EVENT,
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
            onClick={() => {
              if (window.innerWidth >= 640) {
                window.dispatchEvent(new Event(DESKTOP_SIDEBAR_TOGGLE_EVENT));
              } else {
                setMobileSidebarOpen(true);
              }
            }}
            className={`chat-header__sidebar-expand flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-[var(--color-background-muted)] dark:text-stone-300 sm:hidden transition-colors`}
            title={t("sidebar.expandSidebar")}
            aria-label={t("sidebar.expandSidebar")}
          >
            <SidebarToggleIcon mobileFilled className="w-5 h-5" />
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
              className="flex size-11 sm:size-8 items-center justify-center rounded-lg text-theme-text-secondary hover:bg-theme-bg-subtle aria-expanded:bg-theme-bg-subtle aria-expanded:text-theme-text focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
              title={t("common.menu")}
            >
              <MoreHorizontal size={18} />
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
