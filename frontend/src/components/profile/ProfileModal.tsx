import { createPortal } from "react-dom";
import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useVersion } from "../../hooks/useVersion";
import { ProfileInfoTab } from "./tabs/ProfileInfoTab";
import { ProfilePasswordTab } from "./tabs/ProfilePasswordTab";
import { ProfileNotificationTab } from "./tabs/ProfileNotificationTab";
import { UserAgentPreferencePanel } from "./UserAgentPreferencePanel";

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
    "info" | "password" | "notification" | "agent"
  >("info");

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
  ];

  return createPortal(
    <div
      className="fixed inset-0 z-[200] flex items-end sm:items-center sm:justify-center"
      onClick={() => onCloseProfileModal()}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 animate-fade-in" />

      {/* Dialog */}
      <div
        className="relative z-10 w-full sm:max-w-md sm:mx-4 bg-white dark:bg-stone-800 sm:rounded-xl rounded-t-2xl shadow-xl border border-gray-200 dark:border-stone-700 overflow-hidden max-h-[90vh] max-h-[90dvh] flex flex-col animate-slide-up-sheet sm:animate-in sm:fade-in sm:zoom-in-95 sm:duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Mobile drag handle */}
        <div className="sm:hidden flex justify-center pt-3 pb-1">
          <div className="w-9 h-1 bg-gray-300 dark:bg-stone-600 rounded-full" />
        </div>

        {/* Modal Header */}
        <div className="px-4 sm:px-5 py-3 flex items-center justify-between">
          <h3 className="text-base font-semibold text-gray-900 dark:text-stone-100">
            {t("profile.title")}
          </h3>
          <button
            onClick={onCloseProfileModal}
            className="p-1.5 rounded-lg hover:bg-gray-100 dark:hover:bg-stone-700 transition-colors"
          >
            <X size={18} className="text-gray-500 dark:text-stone-400" />
          </button>
        </div>

        {/* Tabs */}
        <div className="px-4 sm:px-5 border-b border-gray-100 dark:border-stone-700/80">
          <div className="flex gap-4 overflow-x-auto scrollbar-none -mb-px">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`relative flex-shrink-0 px-1 py-2.5 text-xs font-medium transition-colors whitespace-nowrap ${
                  activeTab === tab.key
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-gray-500 dark:text-stone-400 hover:text-gray-700 dark:hover:text-stone-200"
                }`}
              >
                {tab.label}
                {activeTab === tab.key && (
                  <span className="absolute bottom-0 left-1 right-1 h-0.5 bg-amber-500 dark:bg-amber-400 rounded-full" />
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto p-4 sm:p-5">
          {activeTab === "info" && <ProfileInfoTab />}
          {activeTab === "password" && <ProfilePasswordTab />}
          {activeTab === "notification" && <ProfileNotificationTab />}
          {activeTab === "agent" && <UserAgentPreferencePanel />}
        </div>

        {/* Modal Footer */}
        <div className="px-4 sm:px-5 py-3 border-t border-gray-100 dark:border-stone-700/60 flex items-center justify-between safe-area-bottom">
          <div className="text-xs text-gray-400 dark:text-stone-500">
            <span className="font-semibold text-gray-500 dark:text-stone-400 font-serif">
              LambChat
            </span>
            {versionInfo?.app_version && (
              <span className="ml-1.5">v{versionInfo.app_version}</span>
            )}
          </div>
          <button
            onClick={onCloseProfileModal}
            className="text-xs text-gray-400 dark:text-stone-500 hover:text-gray-600 dark:hover:text-stone-300 transition-colors"
          >
            {t("common.close")}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
