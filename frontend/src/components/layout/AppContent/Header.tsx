import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";
import {
  Share2,
  MoreHorizontal,
  MessageSquarePlus,
  Bell,
  Languages,
  Sun,
  Moon,
  Check,
  ChevronLeft,
} from "lucide-react";
import { ModelSelector } from "../../agent/ModelSelector";
import { LanguageToggle } from "../../common/LanguageToggle";
import { ThemeToggle } from "../../common/ThemeToggle";
import { UserMenu } from "../UserMenu";
import { ShareDialog } from "../../share/ShareDialog";
import { useAuth } from "../../../hooks/useAuth";
import { useTheme } from "../../../contexts/ThemeContext";
import { authApi } from "../../../services/api";
import { notificationApi } from "../../../services/api/notification";
import { NotificationDialog } from "../../notification/NotificationDialog";
import { Permission } from "../../../types";
import type { TabType } from "./types";
import type { Project } from "../../../types";

interface HeaderProps {
  activeTab: TabType;
  sidebarCollapsed: boolean;
  setSidebarCollapsed: (collapsed: boolean) => void;
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
  sessionName?: string | null;
}

export function Header({
  activeTab,
  sidebarCollapsed,
  setSidebarCollapsed,
  setMobileSidebarOpen,
  currentProjectId,
  projectManager,
  onNewSession,
  onShowProfile,
  availableModels,
  currentModelId,
  onSelectModel,
  sessionId,
  sessionName,
}: HeaderProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const { user } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const [shareDialogOpen, setShareDialogOpen] = useState(false);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [langMenuOpen, setLangMenuOpen] = useState(false);
  const [notifDialogOpen, setNotifDialogOpen] = useState(false);
  const [activeNotifCount, setActiveNotifCount] = useState(0);

  const refreshNotifCount = useCallback(() => {
    notificationApi
      .getActive()
      .then((items) => setActiveNotifCount(items.length));
  }, []);

  useEffect(() => {
    refreshNotifCount();
  }, [refreshNotifCount]);
  const mobileMenuBtnRef = useRef<HTMLButtonElement>(null);
  const mobileMenuPanelRef = useRef<HTMLDivElement>(null);

  // Close mobile menu on outside click
  useEffect(() => {
    if (!mobileMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        mobileMenuPanelRef.current &&
        !mobileMenuPanelRef.current.contains(target) &&
        mobileMenuBtnRef.current &&
        !mobileMenuBtnRef.current.contains(target)
      ) {
        setMobileMenuOpen(false);
      }
    };
    const timer = setTimeout(() => {
      document.addEventListener("click", handleClickOutside);
    }, 0);
    return () => {
      clearTimeout(timer);
      document.removeEventListener("click", handleClickOutside);
    };
  }, [mobileMenuOpen]);

  const hasSharePermission = user?.permissions?.includes(
    Permission.SESSION_SHARE,
  );
  const showShareButton = !!sessionId && hasSharePermission;

  return (
    <>
      <header className="relative z-50 flex items-center px-3 pt-3 sm:px-4 pb-1">
        {/* Left */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {activeTab === "chat" ? (
            <>
              {sidebarCollapsed && (
                <button
                  onClick={() => setSidebarCollapsed(false)}
                  className="hidden sm:flex h-8 w-8 items-center justify-center rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800 transition-colors"
                  title={t("sidebar.expandSidebar")}
                >
                  <svg
                    xmlns="http://www.w3.org/2000/svg"
                    fill="none"
                    viewBox="0 0 24 24"
                    className="w-5 h-5 text-stone-600 dark:text-stone-300"
                  >
                    <path
                      fillRule="evenodd"
                      clipRule="evenodd"
                      d="M8.85719 3H15.1428C16.2266 2.99999 17.1007 2.99998 17.8086 3.05782C18.5375 3.11737 19.1777 3.24318 19.77 3.54497C20.7108 4.02433 21.4757 4.78924 21.955 5.73005C22.2568 6.32234 22.3826 6.96253 22.4422 7.69138C22.5 8.39925 22.5 9.27339 22.5 10.3572V13.6428C22.5 14.7266 22.5 15.6008 22.4422 16.3086C22.3826 17.0375 22.2568 17.6777 21.955 18.27C21.4757 19.2108 20.7108 19.9757 19.77 20.455C19.1777 20.7568 18.5375 20.8826 17.8086 20.9422C17.1008 21 16.2266 21 15.1428 21H8.85717C7.77339 21 6.89925 21 6.19138 20.9422C5.46253 20.8826 4.82234 20.7568 4.23005 20.455C3.28924 19.9757 2.52433 19.2108 2.04497 18.27C1.74318 17.6777 1.61737 17.0375 1.55782 16.3086C1.49998 15.6007 1.49999 14.7266 1.5 13.6428V10.3572C1.49999 9.27341 1.49998 8.39926 1.55782 7.69138C1.61737 6.96253 1.74318 6.32234 2.04497 5.73005C2.52433 4.78924 3.28924 4.02433 4.23005 3.54497C4.82234 3.24318 5.46253 3.11737 6.19138 3.05782C6.89926 2.99998 7.77341 2.99999 8.85719 3ZM6.35424 5.05118C5.74907 5.10062 5.40138 5.19279 5.13803 5.32698C4.57354 5.6146 4.1146 6.07354 3.82698 6.63803C3.69279 6.90138 3.60062 7.24907 3.55118 7.85424C3.50078 8.47108 3.5 9.26339 3.5 10.4V13.6C3.5 14.7366 3.50078 15.5289 3.55118 16.1458C3.60062 16.7509 3.69279 17.0986 3.82698 17.362C4.1146 17.9265 4.57354 18.3854 5.13803 18.673C5.40138 18.8072 5.74907 18.8994 6.35424 18.9488C6.97108 18.9992 7.76339 19 8.9 19H9.5V5H8.9C7.76339 5 6.97108 5.00078 6.35424 5.05118ZM11.5 5V19H15.1C16.2366 19 17.0289 18.9992 17.6458 18.9488C18.2509 18.8994 18.5986 18.8072 18.862 18.673C19.4265 18.3854 19.8854 17.9265 20.173 17.362C20.3072 17.0986 20.3994 16.7509 20.4488 16.1458C20.4992 15.5289 20.5 14.7366 20.5 13.6V10.4C20.5 9.26339 20.4992 8.47108 20.4488 7.85424C20.3994 7.24907 20.3072 6.90138 20.173 6.63803C19.8854 6.57354 19.4265 6.1146 18.862 5.32698C18.5986 5.19279 18.2509 5.10062 17.6458 5.05118C17.0289 5.00078 16.2366 5 15.1 5H11.5ZM5 8.5C5 7.94772 5.44772 7.5 6 7.5H7C7.55229 7.5 8 7.94772 8 8.5C8 9.05229 7.55229 9.5 7 9.5H6C5.44772 9.5 5 9.05229 5 8.5ZM5 12C5 11.4477 5.44772 11 6 11H7C7.55229 11 8 11.4477 8 12C8 12.5523 7.55229 13 7 13H6C5.44772 13 5 12.4477 5 12Z"
                      fill="currentColor"
                    />
                  </svg>
                </button>
              )}
              <button
                onClick={() => setMobileSidebarOpen(true)}
                className={`flex h-8 w-8 items-center justify-center rounded-lg hover:bg-stone-100 dark:hover:bg-stone-800 sm:hidden transition-colors`}
                title={t("sidebar.expandSidebar")}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  className="w-5 h-5 text-stone-600 dark:text-stone-300"
                >
                  <path
                    fillRule="evenodd"
                    clipRule="evenodd"
                    d="M8.85719 3H15.1428C16.2266 2.99999 17.1007 2.99998 17.8086 3.05782C18.5375 3.11737 19.1777 3.24318 19.77 3.54497C20.7108 4.02433 21.4757 4.78924 21.955 5.73005C22.2568 6.32234 22.3826 6.96253 22.4422 7.69138C22.5 8.39925 22.5 9.27339 22.5 10.3572V13.6428C22.5 14.7266 22.5 15.6008 22.4422 16.3086C22.3826 17.0375 22.2568 17.6777 21.955 18.27C21.4757 19.2108 20.7108 19.9757 19.77 20.455C19.1777 20.7568 18.5375 20.8826 17.8086 20.9422C17.1008 21 16.2266 21 15.1428 21H8.85717C7.77339 21 6.89925 21 6.19138 20.9422C5.46253 20.8826 4.82234 20.7568 4.23005 20.455C3.28924 19.9757 2.52433 19.2108 2.04497 18.27C1.74318 17.6777 1.61737 17.0375 1.55782 16.3086C1.49998 15.6007 1.49999 14.7266 1.5 13.6428V10.3572C1.49999 9.27341 1.49998 8.39926 1.55782 7.69138C1.61737 6.96253 1.74318 6.32234 2.04497 5.73005C2.52433 4.78924 3.28924 4.02433 4.23005 3.54497C4.82234 3.24318 5.46253 3.11737 6.19138 3.05782C6.89926 2.99998 7.77341 2.99999 8.85719 3ZM6.35424 5.05118C5.74907 5.10062 5.40138 5.19279 5.13803 5.32698C4.57354 5.6146 4.1146 6.07354 3.82698 6.63803C3.69279 6.90138 3.60062 7.24907 3.55118 7.85424C3.50078 8.47108 3.5 9.26339 3.5 10.4V13.6C3.5 14.7366 3.50078 15.5289 3.55118 16.1458C3.60062 16.7509 3.69279 17.0986 3.82698 17.362C4.1146 17.9265 4.57354 18.3854 5.13803 18.673C5.40138 18.8072 5.74907 18.8994 6.35424 18.9488C6.97108 18.9992 7.76339 19 8.9 19H9.5V5H8.9C7.76339 5 6.97108 5.00078 6.35424 5.05118ZM11.5 5V19H15.1C16.2366 19 17.0289 18.9992 17.6458 18.9488C18.2509 18.8994 18.5986 18.8072 18.862 18.673C19.4265 18.3854 19.8854 17.9265 20.173 17.362C20.3072 17.0986 20.3994 16.7509 20.4488 16.1458C20.4992 15.5289 20.5 14.7366 20.5 13.6V10.4C20.5 9.26339 20.4992 8.47108 20.4488 7.85424C20.3994 7.24907 20.3072 6.90138 20.173 6.63803C19.8854 6.57354 19.4265 6.1146 18.862 5.32698C18.5986 5.19279 18.2509 5.10062 17.6458 5.05118C17.0289 5.00078 16.2366 5 15.1 5H11.5ZM5 8.5C5 7.94772 5.44772 7.5 6 7.5H7C7.55229 7.5 8 7.94772 8 8.5C8 9.05229 7.55229 9.5 7 9.5H6C5.44772 9.5 5 9.05229 5 8.5ZM5 12C5 11.4477 5.44772 11 6 11H7C7.55229 11 8 11.4477 8 12C8 12.5523 7.55229 13 7 13H6C5.44772 13 5 12.4477 5 12Z"
                    fill="currentColor"
                  />
                </svg>
              </button>

              {availableModels &&
                availableModels.length > 0 &&
                onSelectModel && (
                  <ModelSelector
                    models={availableModels}
                    currentModelId={currentModelId || ""}
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
                    <div className="flex items-center gap-1 px-2 py-0.5 rounded-md bg-stone-100 dark:bg-stone-700/50 border border-stone-200 dark:border-stone-600/40">
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                        className="size-3 text-stone-400 dark:text-stone-500"
                      >
                        <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H5V5h14v14z" />
                      </svg>
                      <span className="text-xs text-stone-500 dark:text-stone-400 truncate max-w-[120px]">
                        {project.name}
                      </span>
                    </div>
                  );
                })()}
            </>
          ) : (
            <div className="flex items-center gap-1.5">
              <button
                onClick={() => navigate("/chat")}
                className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
                title={t("common.back")}
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="1.5"
                  stroke="currentColor"
                  className="size-5"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25"
                  />
                </svg>
              </button>
              <div className="flex flex-col justify-center">
                <span className="text-base font-bold text-stone-700 dark:text-stone-200 font-serif leading-tight">
                  {t(`nav.${activeTab}`, { defaultValue: activeTab })}
                </span>
              </div>
            </div>
          )}
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Right */}
        <div className="flex items-center gap-1.5 sm:gap-2 flex-shrink-0">
          {activeTab === "chat" && sidebarCollapsed && (
            <button
              onClick={onNewSession}
              className="hidden sm:flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
              title={t("sidebar.newChat")}
            >
              <MessageSquarePlus size={20} />
            </button>
          )}
          {showShareButton && (
            <button
              onClick={() => setShareDialogOpen(true)}
              className="hidden sm:flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
              title={t("share.title")}
            >
              <Share2 size={20} />
            </button>
          )}

          {/* Mobile overflow menu */}
          <div className="relative sm:hidden">
            <button
              ref={mobileMenuBtnRef}
              onClick={() => setMobileMenuOpen((v) => !v)}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
              title={t("common.menu")}
            >
              <MoreHorizontal size={20} />
            </button>
            {mobileMenuOpen &&
              createPortal(
                <div
                  ref={mobileMenuPanelRef}
                  className="fixed z-[301] right-3 top-[52px] w-56 rounded-xl shadow-xl border overflow-hidden animate-scale-in"
                  style={{
                    backgroundColor: "var(--theme-bg-card)",
                    borderColor: "var(--theme-border)",
                  }}
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="py-1">
                    {activeTab === "chat" && (
                      <button
                        onClick={() => {
                          onNewSession();
                          setMobileMenuOpen(false);
                        }}
                        className="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)]"
                      >
                        <MessageSquarePlus size={16} className="shrink-0" />
                        <span className="truncate">{t("sidebar.newChat")}</span>
                      </button>
                    )}
                    {showShareButton && (
                      <button
                        onClick={() => {
                          setShareDialogOpen(true);
                          setMobileMenuOpen(false);
                        }}
                        className="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)]"
                      >
                        <Share2
                          size={16}
                          strokeWidth={1.8}
                          className="shrink-0"
                        />
                        <span className="truncate">{t("share.title")}</span>
                      </button>
                    )}
                    <button
                      onClick={() => {
                        setNotifDialogOpen(true);
                        setMobileMenuOpen(false);
                      }}
                      className="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)]"
                    >
                      <Bell size={16} className="shrink-0" />
                      <span className="truncate">{t("nav.notifications")}</span>
                      {activeNotifCount > 0 && (
                        <span className="ml-auto flex h-3.5 min-w-[14px] items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white leading-none">
                          {activeNotifCount > 99 ? "99+" : activeNotifCount}
                        </span>
                      )}
                    </button>
                    <button
                      onClick={() => {
                        toggleTheme();
                        setMobileMenuOpen(false);
                      }}
                      className="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)]"
                    >
                      {theme === "light" ? (
                        <>
                          <Moon size={16} className="shrink-0" />
                          <span className="truncate">
                            {t("theme.switchToDark")}
                          </span>
                        </>
                      ) : (
                        <>
                          <Sun size={16} className="shrink-0" />
                          <span className="truncate">
                            {t("theme.switchToLight")}
                          </span>
                        </>
                      )}
                    </button>
                    <button
                      onClick={() => setLangMenuOpen(true)}
                      className="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)]"
                    >
                      <Languages size={16} className="shrink-0" />
                      <span className="truncate">{t("common.language")}</span>
                    </button>
                  </div>
                </div>,
                document.body,
              )}
          </div>

          {langMenuOpen &&
            createPortal(
              <div
                className="fixed z-[302] right-3 top-[52px] w-56 rounded-xl shadow-xl border overflow-hidden animate-scale-in"
                style={{
                  backgroundColor: "var(--theme-bg-card)",
                  borderColor: "var(--theme-border)",
                }}
                onClick={(e) => e.stopPropagation()}
              >
                <button
                  onClick={() => setLangMenuOpen(false)}
                  className="flex w-full items-center gap-2 px-3 py-2.5 text-sm text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)] transition-colors"
                >
                  <ChevronLeft size={16} className="shrink-0" />
                  <span>{t("common.language")}</span>
                </button>
                <div
                  className="h-px mx-2"
                  style={{ backgroundColor: "var(--theme-border)" }}
                />
                <div className="py-1">
                  {[
                    { code: "en", name: "English" },
                    { code: "zh", name: "中文" },
                    { code: "ja", name: "日本語" },
                    { code: "ko", name: "한국어" },
                    { code: "ru", name: "Русский" },
                  ].map((lang) => {
                    const isActive = i18n.language?.split("-")[0] === lang.code;
                    return (
                      <button
                        key={lang.code}
                        onClick={() => {
                          i18n.changeLanguage(lang.code);
                          localStorage.setItem("language", lang.code);
                          authApi
                            .updateMetadata({ language: lang.code })
                            .catch(() => {});
                          setLangMenuOpen(false);
                          setMobileMenuOpen(false);
                        }}
                        className={`flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm transition-colors ${
                          isActive
                            ? "text-[var(--theme-text)] bg-[var(--theme-primary-light)]"
                            : "text-[var(--theme-text-secondary)] hover:text-[var(--theme-text)] hover:bg-[var(--theme-primary-light)]"
                        }`}
                      >
                        <span className="truncate">{lang.name}</span>
                        {isActive && (
                          <Check size={14} className="ml-auto shrink-0" />
                        )}
                      </button>
                    );
                  })}
                </div>
              </div>,
              document.body,
            )}

          <LanguageToggle className="hidden sm:flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors" />
          <ThemeToggle className="hidden sm:flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors" />
          <button
            onClick={() => setNotifDialogOpen(true)}
            className="relative hidden sm:flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
            title={t("nav.notifications")}
          >
            <Bell size={20} />
            {activeNotifCount > 0 && (
              <span className="absolute top-0.5 right-0.5 flex h-3.5 min-w-[14px] items-center justify-center rounded-full bg-red-500 px-1 text-[9px] font-bold text-white leading-none">
                {activeNotifCount > 99 ? "99+" : activeNotifCount}
              </span>
            )}
          </button>
          <UserMenu onShowProfile={onShowProfile} />
        </div>
      </header>

      {sessionId && (
        <ShareDialog
          isOpen={shareDialogOpen}
          onClose={() => setShareDialogOpen(false)}
          sessionId={sessionId}
          sessionName={sessionName || t("sidebar.newChat")}
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
