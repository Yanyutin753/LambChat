import { InteractiveIcon } from "../common/InteractiveIcon";
import { DialogCloseButton } from "../common/DialogCloseButton";
import { ModalSurface } from "../common/ModalSurface";
import { Select } from "../common/ui/Select";
import { observePanelWidths } from "../common/panelWidths";
import { useState, useEffect, useRef, useId } from "react";
import { useTranslation } from "react-i18next";
import {
  User,
  Bell,
  Settings,
  Braces,
  Wrench,
  Cpu,
  Scale,
  Gauge,
} from "lucide-react";
import { BrandWordmark } from "../common/BrandWordmark";
import { APP_VERSION } from "../../utils/appVersion";

import { ProfileInfoTab } from "./tabs/ProfileInfoTab";
import { ProfileNotificationTab } from "./tabs/ProfileNotificationTab";
import { ProfilePreferencesTab } from "./tabs/ProfilePreferencesTab";
import { ProfileEnvVarsTab } from "./tabs/ProfileEnvVarsTab";
import { ProfileToolsTab } from "./tabs/ProfileToolsTab";
import { ProfileModelsTab } from "./tabs/ProfileModelsTab";
import { ProfileTermsTab } from "./tabs/ProfileTermsTab";
import { ComposerUsageChip } from "../chat/ComposerUsageChip";

import "./profile.css";

interface ProfileModalProps {
  showProfileModal: boolean;
  onCloseProfileModal: () => void;
}

const TAB_ICONS = {
  info: User,
  notification: Bell,
  preferences: Settings,
  quota: Gauge,
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
  const [activeTab, setActiveTab] = useState<ProfileTab>("info");
  const contentRef = useRef<HTMLDivElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useEffect(() => {
    if (showProfileModal) setActiveTab("info");
  }, [showProfileModal]);

  useEffect(() => {
    if (contentRef.current) contentRef.current.scrollTop = 0;
  }, [activeTab]);
  useEffect(() => {
    if (showProfileModal && dialogRef.current)
      return observePanelWidths(dialogRef.current);
  }, [showProfileModal]);
  if (!showProfileModal) return null;

  const tabs: { key: ProfileTab; label: string }[] = [
    { key: "info", label: t("profile.title") },
    { key: "notification", label: t("profile.notifications") },
    { key: "preferences", label: t("profile.preferences") },
    { key: "quota", label: t("usage.quotaAndCards") },
    { key: "envvars", label: t("envVars.title") },
    { key: "tools", label: t("profile.toolsTab") },
    { key: "models", label: t("profile.modelIntro") },
    { key: "terms", label: t("profile.termsTab") },
  ];

  return (
    <ModalSurface
      open={showProfileModal}
      onClose={onCloseProfileModal}
      labelledBy={titleId}
      className="profile-modal-surface"
    >
      <div ref={dialogRef} className="profile-dialog safe-area-bottom">
        <header className="profile-header">
          <h2 id={titleId} className="font-serif">
            {t("nav.settings")}
          </h2>
          <DialogCloseButton onClick={onCloseProfileModal} />
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
                    <InteractiveIcon>
                      <Icon size={16} />
                    </InteractiveIcon>
                    <span>{tab.label}</span>
                  </button>
                );
              })}
            </div>
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
          </div>
          <div ref={contentRef} className="profile-content panel-scroll">
            <div key={activeTab} className="profile-page">
              <h2 className="profile-page-title font-serif">
                {tabs.find((tab) => tab.key === activeTab)?.label}
              </h2>
              {activeTab === "info" && <ProfileInfoTab />}
              {activeTab === "notification" && <ProfileNotificationTab />}
              {activeTab === "preferences" && <ProfilePreferencesTab />}
              {activeTab === "quota" && <ComposerUsageChip embedded />}
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
