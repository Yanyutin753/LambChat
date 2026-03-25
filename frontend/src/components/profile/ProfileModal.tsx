import { createPortal } from "react-dom";
import { useState, useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useVersion } from "../../hooks/useVersion";
import { APP_NAME } from "../../constants";
import { ProfileInfoTab } from "./tabs/ProfileInfoTab";
import { ProfilePasswordTab } from "./tabs/ProfilePasswordTab";
import { ProfileNotificationTab } from "./tabs/ProfileNotificationTab";
import { UserAgentPreferencePanel } from "./UserAgentPreferencePanel";
import { ProfilePreferencesTab } from "./tabs/ProfilePreferencesTab";

interface ProfileModalProps {
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
  versionInfo: ReturnType<typeof useVersion>["versionInfo"];
}

export function ProfileModal({
  showProfileModal,
  onCloseProfileModal,
  versionInfo,
}: ProfileModalProps) {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<
    "info" | "password" | "notification" | "agent" | "preferences"
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
    { key: "password", label: t("profile.changePassword") },
    { key: "notification", label: t("profile.notifications") },
    { key: "agent", label: t("agentConfig.defaultAgent") },
    { key: "preferences", label: t("profile.preferences") },
  ];

  const tabContent = (
    <>
      {activeTab === "info" && <ProfileInfoTab />}
      {activeTab === "password" && <ProfilePasswordTab />}
      {activeTab === "notification" && <ProfileNotificationTab />}
      {activeTab === "agent" && <UserAgentPreferencePanel />}
      {activeTab === "preferences" && <ProfilePreferencesTab />}
    </>
  );

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-end sm:items-center sm:justify-center"
      onClick={() => onCloseProfileModal()}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 animate-fade-in" />

      {/* Dialog - Mobile: bottom sheet with top tabs */}
      <div
        className="sm:hidden relative z-10 w-full bg-white dark:bg-stone-800 rounded-t-2xl shadow-xl border border-stone-200 dark:border-stone-700 overflow-hidden max-h-[90dvh] flex flex-col animate-slide-up-sheet"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Drag handle */}
        <div className="flex justify-center pt-3 pb-1">
          <div className="w-9 h-1 bg-stone-300 dark:bg-stone-600 rounded-full" />
        </div>

        {/* Header */}
        <div className="px-4 py-3 flex items-center justify-between">
          <h3 className="text-base font-semibold text-stone-900 dark:text-stone-100">
            {t("profile.title")}
          </h3>
          <button
            onClick={onCloseProfileModal}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
          >
            <X size={18} className="text-stone-500 dark:text-stone-400" />
          </button>
        </div>

        {/* Mobile Tabs - scrollable, no visible scrollbar */}
        <div className="border-b border-stone-100 dark:border-stone-700/80">
          <div
            ref={mobileTabsRef}
            className="flex overflow-x-auto scrollbar-none -mb-px scroll-smooth"
            style={{ scrollSnapType: "x mandatory" }}
          >
            {tabs.map((tab) => (
              <button
                key={tab.key}
                ref={activeTab === tab.key ? activeTabRef : undefined}
                onClick={() => setActiveTab(tab.key)}
                style={{ scrollSnapAlign: "start" }}
                className={`relative shrink-0 px-4 py-2.5 text-xs font-medium transition-colors whitespace-nowrap ${
                  activeTab === tab.key
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-stone-500 dark:text-stone-400"
                }`}
              >
                {tab.label}
                {activeTab === tab.key && (
                  <span className="absolute bottom-0 inset-x-2 h-0.5 bg-amber-500 dark:bg-amber-400 rounded-full" />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-4">{tabContent}</div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-stone-100 dark:border-stone-700/60 flex items-center justify-between safe-area-bottom">
          <div className="text-xs text-stone-400 dark:text-stone-500">
            <span className="font-semibold text-stone-500 dark:text-stone-400 font-serif">
              {APP_NAME}
            </span>
            {versionInfo?.app_version && (
              <span className="ml-1.5">v{versionInfo.app_version}</span>
            )}
          </div>
          <button
            onClick={onCloseProfileModal}
            className="text-xs text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 transition-colors"
          >
            {t("common.close")}
          </button>
        </div>
      </div>

      {/* Dialog - Desktop: wider with left sidebar tabs */}
      <div
        className="hidden sm:flex relative z-10 w-[560px] h-[520px] bg-white dark:bg-stone-800 rounded-xl shadow-xl border border-stone-200 dark:border-stone-700 overflow-hidden flex-col animate-in fade-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-3 flex items-center justify-between border-b border-stone-100 dark:border-stone-700/80">
          <h3 className="text-base font-semibold text-stone-900 dark:text-stone-100">
            {t("profile.title")}
          </h3>
          <button
            onClick={onCloseProfileModal}
            className="p-1.5 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
          >
            <X size={18} className="text-stone-500 dark:text-stone-400" />
          </button>
        </div>

        {/* Body: left tabs + right content */}
        <div className="flex flex-1 min-h-0">
          {/* Left sidebar tabs */}
          <div className="w-32 shrink-0 border-r border-stone-100 dark:border-stone-700/80 py-2">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`w-full text-left px-4 py-2 text-xs font-medium transition-colors ${
                  activeTab === tab.key
                    ? "text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border-r-2 border-amber-500 dark:border-amber-400"
                    : "text-stone-500 dark:text-stone-400 hover:text-stone-700 dark:hover:text-stone-200 hover:bg-stone-50 dark:hover:bg-stone-700/50"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Right content */}
          <div className="flex-1 overflow-y-auto p-5">{tabContent}</div>
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-stone-100 dark:border-stone-700/60 flex items-center justify-between">
          <div className="text-xs text-stone-400 dark:text-stone-500">
            <span className="font-semibold text-stone-500 dark:text-stone-400 font-serif">
              {APP_NAME}
            </span>
            {versionInfo?.app_version && (
              <span className="ml-1.5">v{versionInfo.app_version}</span>
            )}
          </div>
          <button
            onClick={onCloseProfileModal}
            className="text-xs text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300 transition-colors"
          >
            {t("common.close")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
