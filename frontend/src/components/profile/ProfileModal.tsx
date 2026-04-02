import { createPortal } from "react-dom";
import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { X, User, Bell, Settings, Braces } from "lucide-react";
import { useVersion } from "../../hooks/useVersion";
import { APP_NAME } from "../../constants";
import { ProfileInfoTab } from "./tabs/ProfileInfoTab";
import { ProfileNotificationTab } from "./tabs/ProfileNotificationTab";
import { ProfilePreferencesTab } from "./tabs/ProfilePreferencesTab";
import { ProfileEnvVarsTab } from "./tabs/ProfileEnvVarsTab";

interface ProfileModalProps {
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: ReturnType<typeof useVersion>["versionInfo"];
}

const TAB_ICONS: Record<
  string,
  React.FC<{ size?: number; className?: string }>
> = {
  info: User,
  notification: Bell,
  preferences: Settings,
  envvars: Braces,
};

export function ProfileModal({
  showProfileModal,
  onCloseProfileModal,
  versionInfo,
}: ProfileModalProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<
    "info" | "notification" | "preferences" | "envvars"
  >("info");

  const mobileTabsRef = useRef<HTMLDivElement>(null);
  const activeTabRef = useRef<HTMLButtonElement>(null);

  // Auto-scroll to active tab on mobile
  useEffect(() => {
    activeTabRef.current?.scrollIntoView({
      behavior: "smooth",
      inline: "center",
      block: "nearest",
    });
  }, [activeTab]);

  // Reset tab when modal opens
  useEffect(() => {
    if (showProfileModal) setActiveTab("info");
  }, [showProfileModal]);

  // Body scroll lock
  useEffect(() => {
    if (showProfileModal) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
    };
  }, [showProfileModal]);

  // ESC key to close
  useEffect(() => {
    if (!showProfileModal) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseProfileModal();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [showProfileModal, onCloseProfileModal]);

  if (!showProfileModal) return null;

  const tabs: { key: typeof activeTab; label: string }[] = [
    { key: "info", label: t("profile.title") },
    { key: "notification", label: t("profile.notifications") },
    { key: "preferences", label: t("profile.preferences") },
    { key: "envvars", label: t("envVars.title") },
  ];

  const renderTabContent = () => (
    <div className="animate-fade-in">
      {activeTab === "info" && <ProfileInfoTab />}
      {activeTab === "notification" && <ProfileNotificationTab />}
      {activeTab === "preferences" && <ProfilePreferencesTab />}
      {activeTab === "envvars" && <ProfileEnvVarsTab />}
    </div>
  );

  const renderCloseButton = (className?: string) => (
    <button
      onClick={onCloseProfileModal}
      className={`p-1.5 rounded-lg text-stone-400 hover:text-stone-600 hover:bg-stone-100 dark:text-stone-500 dark:hover:text-stone-300 dark:hover:bg-stone-700/60 transition-all ${
        className ?? ""
      }`}
    >
      <X size={18} />
    </button>
  );

  const renderFooter = (className?: string) => (
    <div
      className={`px-5 py-3 border-t border-stone-100 dark:border-stone-700/50 flex items-center justify-between bg-stone-50/50 dark:bg-stone-900/30 ${
        className ?? ""
      }`}
    >
      <div className="text-[11px] text-stone-400 dark:text-stone-500 tabular-nums">
        <span className="font-semibold text-stone-500 dark:text-stone-400 font-serif tracking-tight">
          {APP_NAME}
        </span>
        {versionInfo?.app_version && (
          <span className="ml-1.5 opacity-70">v{versionInfo.app_version}</span>
        )}
      </div>
      <button
        onClick={onCloseProfileModal}
        className="text-[11px] font-medium text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 transition-colors py-1 rounded-md hover:bg-stone-100 dark:hover:bg-stone-700/60"
      >
        {t("common.poweredBy")}
      </button>
    </div>
  );

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-end sm:items-center sm:justify-center"
      onClick={() => onCloseProfileModal()}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50 animate-fade-in" />

      {/* ===== Mobile: bottom sheet ===== */}
      <div
        className="sm:hidden relative z-10 w-full bg-white dark:bg-stone-800 rounded-t-2xl shadow-2xl shadow-black/20 dark:shadow-black/50 border-x border-t border-stone-200/80 dark:border-stone-700/60 overflow-hidden max-h-[90dvh] flex flex-col animate-slide-up-sheet"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drag handle */}
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-9 h-1 bg-stone-300 dark:bg-stone-600 rounded-full" />
        </div>

        {/* Header */}
        <div className="px-4 py-2.5 flex items-center justify-between">
          <h3 className="text-[15px] font-semibold text-stone-900 dark:text-stone-100 tracking-tight">
            {t("profile.title")}
          </h3>
          {renderCloseButton()}
        </div>

        {/* Mobile Tabs */}
        <div className="px-3 pb-1">
          <div
            ref={mobileTabsRef}
            className="flex gap-1 overflow-x-auto scrollbar-none scroll-smooth"
            style={{ scrollSnapType: "x mandatory" }}
          >
            {tabs.map((tab) => {
              const Icon = TAB_ICONS[tab.key];
              const isActive = activeTab === tab.key;
              return (
                <button
                  key={tab.key}
                  ref={isActive ? activeTabRef : undefined}
                  onClick={() => setActiveTab(tab.key)}
                  style={{ scrollSnapAlign: "start" }}
                  className={`relative shrink-0 flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-medium transition-all whitespace-nowrap ${
                    isActive
                      ? "bg-stone-900 text-white dark:bg-stone-100 dark:text-stone-900"
                      : "text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-700/50"
                  }`}
                >
                  {Icon && <Icon size={14} />}
                  {tab.label}
                </button>
              );
            })}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">{renderTabContent()}</div>

        {/* Footer */}
        {renderFooter("safe-area-bottom")}
      </div>

      {/* ===== Desktop: centered with sidebar ===== */}
      <div
        className="hidden sm:flex relative z-10 w-[580px] sm:w-[680px] h-[540px] bg-white dark:bg-stone-800 rounded-2xl shadow-2xl shadow-stone-900/10 dark:shadow-black/40 border border-stone-200/80 dark:border-stone-700/50 overflow-hidden flex-col animate-scale-in"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 flex items-center justify-between border-b border-stone-100 dark:border-stone-700/50">
          <div>
            <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 tracking-tight">
              {t("profile.title")}
            </h3>
            <p className="text-[11px] text-stone-400 dark:text-stone-500 mt-0.5">
              {t("profile.title")}
            </p>
          </div>
          {renderCloseButton()}
        </div>

        {/* Body: left sidebar tabs + right content */}
        <div className="flex flex-1 min-h-0">
          {/* Left sidebar tabs */}
          <div className="w-[152px] shrink-0 border-r border-stone-100 dark:border-stone-700/50 py-2 px-2 space-y-0.5 bg-stone-50/50 dark:bg-stone-900/20">
            {tabs.map((tab) => {
              const Icon = TAB_ICONS[tab.key];
              const isActive = activeTab === tab.key;
              return (
                <button
                  key={tab.key}
                  onClick={() => setActiveTab(tab.key)}
                  className={`w-full text-left flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-xs font-medium transition-all ${
                    isActive
                      ? "bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100 shadow-sm border border-stone-200/80 dark:border-stone-700/60"
                      : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-white/60 dark:hover:bg-stone-800/60 border border-transparent"
                  }`}
                >
                  {Icon && (
                    <Icon
                      size={15}
                      className={
                        isActive
                          ? "text-amber-500 dark:text-amber-400"
                          : "opacity-60"
                      }
                    />
                  )}
                  {tab.label}
                </button>
              );
            })}
          </div>

          {/* Right content */}
          <div className="flex-1 overflow-y-auto p-5">{renderTabContent()}</div>
        </div>

        {/* Footer */}
        {renderFooter()}
      </div>
    </div>,
    document.body,
  );
}
