import { useEffect } from "react";
import { Package, PackageX, Plug, ShoppingBag } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { useSettingsContext } from "../../contexts/SettingsContext";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import { MarketplacePanel } from "./MarketplacePanel";
import { PluginRuntimePanel } from "./PluginRuntimePanel";
import { SkillsPanel } from "./SkillsPanel";
import type { PluginRuntimeContributionStates } from "../../extensions/coreContributions";
import { resolveSkillsHubTab, type SkillsHubTab } from "./SkillsHubPanel/state";

const TAB_PATHS: Record<SkillsHubTab, string> = {
  skills: "/skills",
  marketplace: "/marketplace",
  plugins: "/plugins",
};

type SkillsHubTabItem = {
  key: SkillsHubTab;
  label: string;
  icon: typeof Package;
  path: string;
};

export function SkillsHubPanel({
  runtimePlugins,
}: {
  runtimePlugins?: PluginRuntimeContributionStates;
}) {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const { hasAnyPermission } = useAuth();
  const { enableSkills } = useSettingsContext();

  const canReadSkills = hasAnyPermission([Permission.SKILL_READ]);
  const canReadMarketplace = hasAnyPermission([Permission.MARKETPLACE_READ]);
  const requestedTab: SkillsHubTab =
    location.pathname === "/marketplace"
      ? "marketplace"
      : location.pathname === "/plugins"
        ? "plugins"
        : "skills";
  const visibleTab = resolveSkillsHubTab(
    requestedTab,
    canReadSkills,
    canReadMarketplace,
  );
  const showTabSwitcher = canReadSkills || canReadMarketplace;
  const hubTabs: SkillsHubTabItem[] = [
    canReadSkills
      ? {
          key: "skills" as const,
          label: t("nav.skills"),
          icon: Package,
          path: TAB_PATHS.skills,
        }
      : null,
    canReadMarketplace
      ? {
          key: "marketplace" as const,
          label: t("nav.marketplace"),
          icon: ShoppingBag,
          path: TAB_PATHS.marketplace,
        }
      : null,
    canReadMarketplace
      ? {
          key: "plugins" as const,
          label: t("nav.plugins"),
          icon: Plug,
          path: TAB_PATHS.plugins,
        }
      : null,
  ].filter((tab): tab is SkillsHubTabItem => tab !== null);

  useEffect(() => {
    if (!visibleTab) return;
    const targetPath = TAB_PATHS[visibleTab];
    if (location.pathname !== targetPath) {
      navigate(targetPath, { replace: true });
    }
  }, [location.pathname, navigate, visibleTab]);

  if (!enableSkills && visibleTab !== "plugins") {
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
          className="skills-hub-tabs"
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
          <SkillsPanel embedded runtimePlugins={runtimePlugins} />
        ) : visibleTab === "plugins" ? (
          <PluginRuntimePanel embedded />
        ) : (
          <MarketplacePanel embedded />
        )}
      </div>
    </div>
  );
}
