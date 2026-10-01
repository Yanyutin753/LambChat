import { ModalSurface } from "../common/ModalSurface";
import { Select } from "../common/ui/Select";
import { useState, useEffect, useRef, useId } from "react";
import { useTranslation } from "react-i18next";
import {
  X,
  User,
  Bell,
  Settings,
  Braces,
  Wrench,
  Cpu,
  Scale,
  LogOut,
} from "lucide-react";
import { useAuth } from "../../hooks/useAuth";
import { BrandWordmark } from "../common/BrandWordmark";
import { APP_VERSION } from "../../utils/appVersion";

import { ProfileInfoTab } from "./tabs/ProfileInfoTab";
import { ProfileNotificationTab } from "./tabs/ProfileNotificationTab";
import { ProfilePreferencesTab } from "./tabs/ProfilePreferencesTab";
import { ProfileEnvVarsTab } from "./tabs/ProfileEnvVarsTab";
import { ProfileToolsTab } from "./tabs/ProfileToolsTab";
import { ProfileModelsTab } from "./tabs/ProfileModelsTab";
import { ProfileTermsTab } from "./tabs/ProfileTermsTab";

import "./profile.css";

interface ProfileModalProps {
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
}

const TAB_ICONS = {
  info: User,
  notification: Bell,
  preferences: Settings,
  envvars: Braces,
  tools: Wrench,
  models: Cpu,
  terms: Scale,
};
type ProfileTab = keyof typeof TAB_ICONS;

export function ProfileModal({
  showProfileModal,
  onCloseProfileModal,
}: ProfileModalProps) {
  const { t } = useTranslation();
  const { logout } = useAuth();
  const [activeTab, setActiveTab] = useState<ProfileTab>("info");
  const contentRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (showProfileModal) setActiveTab("info");
  }, [showProfileModal]);

  useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = 0;
  }, [activeTab]);
  if (!showProfileModal) return null;

  const tabs: { key: ProfileTab; label: string }[] = [
    { key: "info", label: t("profile.title") },
    { key: "notification", label: t("profile.notifications") },
    { key: "preferences", label: t("profile.preferences") },
    { key: "envvars", label: t("envVars.title") },
    { key: "tools", label: t("profile.toolsTab") },
    { key: "models", label: t("profile.modelIntro") },
    { key: "terms", label: t("profile.termsTab") },
  ];
  const logoutButton = (
    <button
      type="button"
      className="profile-logout"
      onClick={() => {
        logout();
        onCloseProfileModal();
      }}
    >
      <LogOut size={16} />
      {t("auth.logout")}
    </button>
  );

  return (
    <ModalSurface
      open={showProfileModal}
      onClose={onCloseProfileModal}
      labelledBy={titleId}
      className="profile-modal-surface"
    >
      <div className="profile-dialog safe-area-bottom">
        <header className="profile-header">
          <h2 id={titleId} className="font-serif">
            {t("nav.settings")}
          </h2>
          <button
            type="button"
            className="profile-icon-button"
            aria-label={t("common.close")}
            onClick={onCloseProfileModal}
          >
            <X size={18} />
          </button>
        </header>
        <div className="profile-body">
          <nav className="profile-nav" aria-label={t("profile.preferences")}>
            <div className="profile-nav-items">
              {tabs.map((tab) => {
                const Icon = TAB_ICONS[tab.key];
                return (
                  <button
                    type="button"
                    key={tab.key}
                    aria-current={activeTab === tab.key ? "page" : undefined}
                    onClick={() => setActiveTab(tab.key)}
                  >
                    <Icon size={16} />
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </div>
            {logoutButton}
          </nav>
          <div className="profile-category">
            <Select
              value={activeTab}
              onChange={(value) => setActiveTab(value as ProfileTab)}
              ariaLabel={t("profile.preferences")}
              options={tabs.map((tab) => ({
                value: tab.key,
                label: tab.label,
              }))}
            />
            {logoutButton}
          </div>
          <div ref={contentRef} className="profile-content">
            <div key={activeTab} className="profile-page">
              <h2 className="profile-page-title font-serif">
                {tabs.find((tab) => tab.key === activeTab)?.label}
              </h2>
              {activeTab === "info" && <ProfileInfoTab />}
              {activeTab === "notification" && <ProfileNotificationTab />}
              {activeTab === "preferences" && <ProfilePreferencesTab />}
              {activeTab === "envvars" && <ProfileEnvVarsTab />}
              {activeTab === "tools" && <ProfileToolsTab />}
              {activeTab === "models" && <ProfileModelsTab />}
              {activeTab === "terms" && <ProfileTermsTab />}
            </div>
          </div>
        </div>
        <footer className="profile-footer">
          <a
            href="https://github.com/Yanyutin753/LambChat"
            target="_blank"
            rel="noopener noreferrer"
          >
            <BrandWordmark decorative className="h-4 w-auto" />
            <span>v{APP_VERSION}</span>
          </a>
          <span>{t("common.poweredBy")}</span>
        </footer>
      </div>
    </ModalSurface>
  );
}
