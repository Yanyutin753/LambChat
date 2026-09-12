import { useEffect, useState } from "react";
import { X, Puzzle, RotateCw, Tag, Filter } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { Button, IconButton } from "../common";
import { MarketplacePanelSkeleton } from "../skeletons";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { EmptyState } from "../common/EmptyState";
import { SkillFilterDropdown } from "./SkillFilterDropdown";
import { usePlugins } from "../../hooks/usePlugins";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type { PluginResponse } from "../../types";
import { PluginCard } from "./PluginMarketPanel/PluginCard";
import { PluginPreviewModal } from "./PluginMarketPanel/PluginPreviewModal";

type ActiveFilter = "all" | "active" | "inactive";

const ACTIVE_FILTER_OPTIONS: Array<{
  value: ActiveFilter;
  labelKey: string;
}> = [
  { value: "all", labelKey: "plugins.filterAll" },
  { value: "active", labelKey: "plugins.filterActive" },
  { value: "inactive", labelKey: "plugins.filterInactive" },
];

interface PluginMarketPanelProps {
  embedded?: boolean;
}

export function PluginMarketPanel({ embedded = false }: PluginMarketPanelProps) {
  const { t } = useTranslation();
  const { hasAnyPermission } = useAuth();
  const {
    plugins,
    tags,
    isLoading,
    error,
    selectedTags,
    searchQuery,
    setSearchQuery,
    activeFilter,
    setActiveFilter,
    toggleTag,
    clearFilters,
    fetchPlugins,
    installPlugin,
    updatePlugin,
    uninstallPlugin,
    activatePlugin,
    deletePlugin,
    clearError,
  } = usePlugins();

  const canAdmin = hasAnyPermission([Permission.MARKETPLACE_ADMIN]);

  const [installConfirm, setInstallConfirm] = useState<{
    isOpen: boolean;
    pluginName: string;
    action: "install" | "update";
  } | null>(null);
  const [installingPlugin, setInstallingPlugin] = useState<string | null>(null);
  const [uninstallConfirm, setUninstallConfirm] = useState<{
    isOpen: boolean;
    pluginName: string;
  } | null>(null);
  const [deleteConfirm, setDeleteConfirm] = useState<{
    isOpen: boolean;
    pluginName: string;
  } | null>(null);
  const [previewPlugin, setPreviewPlugin] = useState<PluginResponse | null>(null);
  const [openMenuName, setOpenMenuName] = useState<string | null>(null);
  const [isFilterOpen, setIsFilterOpen] = useState(false);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (openMenuName && !target.closest("[data-plugin-menu]")) {
        setOpenMenuName(null);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [openMenuName]);

  const handleInstallClick = (pluginName: string) => {
    const plugin = plugins.find((p) => p.name === pluginName);
    setInstallConfirm({
      isOpen: true,
      pluginName,
      action: plugin?.installed ? "update" : "install",
    });
  };

  const confirmInstall = async () => {
    if (!installConfirm) return;
    const { pluginName, action } = installConfirm;
    setInstallingPlugin(pluginName);
    try {
      const success =
        action === "install"
          ? await installPlugin(pluginName)
          : await updatePlugin(pluginName);
      if (success) {
        toast.success(
          action === "install"
            ? t("plugins.installSuccess", { name: pluginName })
            : t("plugins.updateSuccess", { name: pluginName }),
        );
      } else {
        toast.error(
          action === "install"
            ? t("plugins.installFailed")
            : t("plugins.updateFailed"),
        );
      }
    } finally {
      setInstallingPlugin(null);
      setInstallConfirm(null);
    }
  };

  const confirmUninstall = async () => {
    if (!uninstallConfirm) return;
    const success = await uninstallPlugin(uninstallConfirm.pluginName);
    if (success) {
      toast.success(
        t("plugins.uninstallSuccess", { name: uninstallConfirm.pluginName }),
      );
    }
    setUninstallConfirm(null);
  };

  const handleActivate = async (pluginName: string, isActive: boolean) => {
    const success = await activatePlugin(pluginName, isActive);
    if (success) {
      toast.success(
        isActive
          ? t("plugins.activateSuccess")
          : t("plugins.deactivateSuccess"),
      );
    }
  };

  const confirmDelete = async () => {
    if (!deleteConfirm) return;
    const success = await deletePlugin(deleteConfirm.pluginName);
    if (success) {
      toast.success(t("plugins.deleteSuccess"));
    }
    setDeleteConfirm(null);
  };

  const canManageFilters = canAdmin;
  const hasActiveFilters =
    (canManageFilters && activeFilter !== "all") ||
    selectedTags.length > 0 ||
    searchQuery.length > 0;

  const filterMenu = (canManageFilters || tags.length > 0) && (
    <SkillFilterDropdown
      isOpen={isFilterOpen}
      label={canManageFilters ? t("skills.filter") : t("adminMarketplace.tags")}
      icon={canManageFilters ? <Filter size={16} /> : <Tag size={16} />}
      activeCount={
        (canManageFilters && activeFilter !== "all" ? 1 : 0) +
        selectedTags.length
      }
      options={
        canManageFilters
          ? ACTIVE_FILTER_OPTIONS.map((opt) => ({
              value: opt.value,
              label: t(opt.labelKey),
            }))
          : undefined
      }
      value={activeFilter}
      tags={tags}
      selectedTags={selectedTags}
      tagsLabel={t("adminMarketplace.tags")}
      clearLabel={t("plugins.clearFilters")}
      onOpenChange={setIsFilterOpen}
      onValueChange={setActiveFilter}
      onToggleTag={toggleTag}
      onClearFilters={clearFilters}
    />
  );

  const headerActions = (
    <Button
      variant="secondary"
      onClick={() => fetchPlugins()}
      className="h-10"
      title={t("common.refresh")}
    >
      <RotateCw size={16} />
      <span className="hidden sm:inline">{t("common.refresh")}</span>
    </Button>
  );

  const isInitialLoading = isLoading && plugins.length === 0 && !hasActiveFilters;

  if (isInitialLoading) {
    return <MarketplacePanelSkeleton />;
  }

  return (
    <div className="skill-theme-shell flex h-full min-h-0 flex-col">
      {embedded && (
        <PanelHeader
          className="skill-panel-header"
          title={t("plugins.title")}
          searchOnly
          searchValue={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder={t("plugins.searchPlaceholder")}
          searchAccessory={filterMenu}
          searchActions={headerActions}
        />
      )}
      {!embedded && (
        <PanelHeader
          className="skill-panel-header"
          title={t("plugins.title")}
          subtitle={t("plugins.subtitle")}
          icon={
            <Puzzle
              size={20}
              className="text-stone-600 dark:text-stone-400"
            />
          }
          searchValue={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder={t("plugins.searchPlaceholder")}
          searchAccessory={filterMenu}
          actions={headerActions}
        />
      )}

      {error && (
        <div className="mx-4 mt-4 flex items-center justify-between rounded-xl bg-red-50 p-3 text-14 text-red-700 dark:bg-red-900/30 dark:text-red-400">
          <span>{error}</span>
          <IconButton
            aria-label={t("common.close")}
            icon={<X size={18} />}
            onClick={clearError}
            className="hover:text-red-900 dark:hover:text-red-300"
          />
        </div>
      )}

      <div className="skill-content-area flex-1 overflow-y-auto py-2 sm:py-4 px-4 sm:p-6 lg:px-8 lg:py-8">
        {plugins.length === 0 ? (
          <EmptyState
            icon={<Puzzle size={28} />}
            title={
              hasActiveFilters
                ? t("plugins.noMatchingPlugins")
                : t("plugins.noPlugins")
            }
            description={
              hasActiveFilters
                ? t("plugins.subtitle")
                : t("plugins.emptyHint")
            }
            action={
              hasActiveFilters ? (
                <Button variant="secondary" onClick={clearFilters}>
                  {t("plugins.clearFilters")}
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className="grid auto-grid-cols gap-5">
            {plugins.map((plugin, index) => (
              <PluginCard
                key={plugin.name}
                plugin={plugin}
                index={index}
                canAdmin={canAdmin}
                installingPlugin={installingPlugin}
                openMenuName={openMenuName}
                onInstallClick={handleInstallClick}
                onUninstall={(name) =>
                  setUninstallConfirm({ isOpen: true, pluginName: name })
                }
                onPreview={() => setPreviewPlugin(plugin)}
                onOpenMenu={setOpenMenuName}
                onActivate={handleActivate}
                onDelete={(name) =>
                  setDeleteConfirm({ isOpen: true, pluginName: name })
                }
              />
            ))}
          </div>
        )}
      </div>

      <ConfirmDialog
        isOpen={installConfirm?.isOpen ?? false}
        title={
          installConfirm?.action === "install"
            ? t("plugins.confirmInstall", { name: installConfirm?.pluginName })
            : t("plugins.confirmUpdate", { name: installConfirm?.pluginName })
        }
        message={
          installConfirm?.action === "install"
            ? t("plugins.confirmInstallMessage")
            : t("plugins.confirmUpdateMessage")
        }
        confirmText={
          installConfirm?.action === "install"
            ? t("plugins.install")
            : t("plugins.update")
        }
        cancelText={t("common.cancel")}
        onConfirm={confirmInstall}
        onCancel={() => setInstallConfirm(null)}
        variant="info"
        loading={!!installingPlugin}
      />

      <ConfirmDialog
        isOpen={uninstallConfirm?.isOpen ?? false}
        title={t("plugins.confirmUninstall", {
          name: uninstallConfirm?.pluginName,
        })}
        message={t("plugins.confirmUninstallMessage")}
        confirmText={t("plugins.uninstall")}
        cancelText={t("common.cancel")}
        onConfirm={confirmUninstall}
        onCancel={() => setUninstallConfirm(null)}
        variant="info"
      />

      <ConfirmDialog
        isOpen={deleteConfirm?.isOpen ?? false}
        title={t("plugins.confirmDelete", {
          name: deleteConfirm?.pluginName,
        })}
        message={t("plugins.confirmDeleteMessage")}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteConfirm(null)}
        variant="danger"
      />

      {previewPlugin && (
        <PluginPreviewModal
          plugin={previewPlugin}
          onClose={() => setPreviewPlugin(null)}
        />
      )}
    </div>
  );
}
