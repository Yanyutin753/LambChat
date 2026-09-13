import { useEffect } from "react";
import { Package, PackageX, ShoppingBag } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { useSettingsContext } from "../../contexts/SettingsContext";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import { MarketplacePanel } from "./MarketplacePanel";
import { SkillsPanel } from "./SkillsPanel";
import { resolveSkillsHubTab, type SkillsHubTab } from "./SkillsHubPanel/state";

const TAB_PATHS: Record<SkillsHubTab, string> = {
  skills: "/skills",
  marketplace: "/marketplace",
};

export function SkillsHubPanel() {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { hasAnyPermission } = useAuth();
  const { enableSkills } = useSettingsContext();

  const canReadSkills = hasAnyPermission([Permission.SKILL_READ]);
  const canReadMarketplace = hasAnyPermission([Permission.MARKETPLACE_READ]);
  const requestedTab: SkillsHubTab =
    location.pathname === "/marketplace" ? "marketplace" : "skills";
  const visibleTab = resolveSkillsHubTab(
    requestedTab,
    canReadSkills,
    canReadMarketplace,
  );
  const showTabSwitcher = canReadSkills && canReadMarketplace;
  const hubTabs = [
    {
      key: "skills" as const,
      label: t("nav.skills"),
      icon: Package,
      path: TAB_PATHS.skills,
    },
    {
      key: "marketplace" as const,
      label: t("nav.marketplace"),
      icon: ShoppingBag,
      path: TAB_PATHS.marketplace,
    },
  ];

  useEffect(() => {
    if (!visibleTab) return;
    const targetPath = TAB_PATHS[visibleTab];
    if (location.pathname !== targetPath) {
      navigate(targetPath, { replace: true });
    }
  }, [location.pathname, navigate, visibleTab]);

  if (!enableSkills) {
    return (
      <div className="flex h-full flex-col items-center justify-center text-stone-500 dark:text-stone-400">
        <PackageX
          size={48}
          className="mb-3 text-stone-300 dark:text-stone-600"
        />
        <p className="text-center">{t("skills.featureDisabled")}</p>
      </div>
    );
  }

  if (!visibleTab) {
    return (
      <div className="flex h-full items-center justify-center text-stone-500 dark:text-stone-400">
        {t("skills.noPermission")}
      </div>
    );
  }

  return (
    <div className="skill-theme-shell flex h-full min-h-0 flex-col">
      {showTabSwitcher && (
        <div
          className="skills-hub-tabs font-serif"
          role="tablist"
          aria-label={t("skillsHub.title")}
        >
          <div className="skills-hub-tabs__group">
            {hubTabs.map(({ key, label, icon: Icon, path }) => {
              const isActive = visibleTab === key;
              return (
                <button
                  key={key}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => navigate(path)}
                  className={`skills-hub-tabs__item ${
                    isActive ? "skills-hub-tabs__item--active" : ""
                  }`}
                >
                  <Icon size={16} />
                  <span>{label}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-hidden">
        {visibleTab === "skills" ? (
          <SkillsPanel embedded />
        ) : (
          <MarketplacePanel embedded />
        )}
      </div>
    </div>
  );
}
