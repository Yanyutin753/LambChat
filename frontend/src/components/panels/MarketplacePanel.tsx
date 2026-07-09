import { useState, useEffect } from "react";
import { X, ShoppingBag, Plus, RotateCw, Tag, Filter } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { Button, IconButton } from "../common";
import { MarketplacePanelSkeleton } from "../skeletons";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { EmptyState } from "../common/EmptyState";
import { SkillFormSidebar } from "./SkillsPanel/SkillFormSidebar";
import { SkillFilterDropdown } from "./SkillFilterDropdown";
import { useMarketplace } from "../../hooks/useMarketplace";
import { useSkills } from "../../hooks/useSkills";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type { SkillResponse, SkillCreate } from "../../types";
import { SkillCard } from "./MarketplacePanel/SkillCard";
import { SkillPreviewModal } from "./MarketplacePanel/SkillPreviewModal";

type ActiveFilter = "all" | "active" | "inactive";

const ACTIVE_FILTER_OPTIONS: Array<{
  value: ActiveFilter;
  labelKey: string;
}> = [
  { value: "all", labelKey: "marketplace.filterAll" },
  { value: "active", labelKey: "marketplace.filterActive" },
  { value: "inactive", labelKey: "marketplace.filterInactive" },
];

interface MarketplacePanelProps {
  embedded?: boolean;
}

export function MarketplacePanel({ embedded = false }: MarketplacePanelProps) {
  const { t } = useTranslation();
  const { hasAnyPermission } = useAuth();
  const {
    filteredSkills,
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
    fetchSkills,
    installSkill,
    updateSkill,
    createAndPublish,
    updateMarketplaceSkill,
    activateSkill,
    deleteSkill,
    loadMarketplaceSkillForEdit,
    clearError,
    previewSkill,
    previewFiles,
    previewLoading,
    previewFileContent,
    previewBinaryFiles,
    previewFileLoading,
    openPreview,
    readPreviewFile,
    closePreview,
    setPreviewFileContent,
  } = useMarketplace();

  const {
    skills: userSkills,
    fetchSkills: fetchUserSkills,
    isLoading: userSkillsLoading,
    getSkill,
  } = useSkills();
  const canWrite = hasAnyPermission([Permission.MARKETPLACE_PUBLISH]);
  const canAdmin = hasAnyPermission([Permission.MARKETPLACE_ADMIN]);

  const installedMarketplaceNames = new Set(
    userSkills
      .filter((skill) => skill.installed_from === "marketplace")
      .map((skill) => skill.name),
  );

  useEffect(() => {
    fetchUserSkills();
  }, [fetchUserSkills]);

  // Install confirmation dialog
  const [installConfirm, setInstallConfirm] = useState<{
    isOpen: boolean;
    skillName: string;
    action: "install" | "update";
  } | null>(null);
  const [installingSkill, setInstallingSkill] = useState<string | null>(null);

  // Filter & edit state
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<SkillResponse | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [openMenuName, setOpenMenuName] = useState<string | null>(null);

  // Close card menus when clicking outside
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement;
      if (openMenuName && !target.closest("[data-mp-menu]")) {
        setOpenMenuName(null);
      }
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [openMenuName]);

  // Admin delete confirmation
  const [adminDeleteConfirm, setAdminDeleteConfirm] = useState<{
    isOpen: boolean;
    skillName: string;
  } | null>(null);

  const handleActivate = async (skillName: string, isActive: boolean) => {
    const success = await activateSkill(skillName, isActive);
    if (success) {
      toast.success(
        isActive
          ? t("marketplace.activateSuccess")
          : t("marketplace.deactivateSuccess"),
      );
    }
  };

  const handleAdminDelete = (skillName: string) => {
    setAdminDeleteConfirm({ isOpen: true, skillName });
  };

  const confirmAdminDelete = async () => {
    if (!adminDeleteConfirm) return;
    const success = await deleteSkill(adminDeleteConfirm.skillName);
    if (success) {
      toast.success(t("marketplace.deleteSuccess"));
      await fetchUserSkills();
    }
    setAdminDeleteConfirm(null);
  };

  const handleInstallClick = (skillName: string) => {
    const action = installedMarketplaceNames.has(skillName)
      ? "update"
      : "install";
    setInstallConfirm({ isOpen: true, skillName, action });
  };

  const confirmInstall = async () => {
    if (!installConfirm) return;

    const { skillName, action } = installConfirm;
    setInstallingSkill(skillName);

    try {
      const success =
        action === "install"
          ? await installSkill(skillName)
          : await updateSkill(skillName);

      if (success) {
        toast.success(
          action === "install"
            ? t("marketplace.installSuccess", { name: skillName })
            : t("marketplace.updateSuccess", { name: skillName }),
        );
        await fetchUserSkills();
      } else {
        toast.error(
          action === "install"
            ? t("marketplace.installFailed")
            : t("marketplace.updateFailed"),
        );
      }
    } finally {
      setInstallingSkill(null);
      setInstallConfirm(null);
    }
  };

  const cancelInstall = () => {
    setInstallConfirm(null);
  };

  const handleEdit = async (skillName: string) => {
    let fullSkill = await getSkill(skillName);
    if (!fullSkill) {
      fullSkill = await loadMarketplaceSkillForEdit(skillName);
      if (!fullSkill) {
        toast.error(t("marketplace.loadFailed"));
        return;
      }
    }
    setEditingSkill(fullSkill);
    setIsCreating(false);
  };

  const handleCreate = () => {
    setEditingSkill(null);
    setIsCreating(true);
    setShowCreateModal(true);
  };

  const handleSave = async (data: SkillCreate): Promise<boolean> => {
    try {
      let success = false;
      if (isCreating) {
        success = await createAndPublish({
          skill_name: data.name,
          description: data.description,
          tags: data.tags,
          version: "1.0.0",
          files: data.files || { "SKILL.md": data.content },
        });
      } else if (editingSkill) {
        success = await updateMarketplaceSkill(editingSkill.name, {
          skill_name: editingSkill.name,
          description: data.description,
          tags: data.tags,
          version: "1.0.0",
          files: data.files || { "SKILL.md": data.content },
        });
      }
      if (success) {
        setEditingSkill(null);
        setIsCreating(false);
        setShowCreateModal(false);
        await fetchSkills();
        await fetchUserSkills();
        toast.success(
          isCreating
            ? t("marketplace.publishSuccess", { name: data.name })
            : t("marketplace.republishSuccess", { name: editingSkill?.name }),
        );
      }
      return success;
    } catch {
      return false;
    }
  };

  const handleFormCancel = () => {
    setEditingSkill(null);
    setIsCreating(false);
    setShowCreateModal(false);
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
      clearLabel={t("marketplace.clearFilters")}
      onOpenChange={setIsFilterOpen}
      onValueChange={setActiveFilter}
      onToggleTag={toggleTag}
      onClearFilters={clearFilters}
    />
  );

  const headerActions = (
    <>
      {canWrite && (
        <Button variant="primary" onClick={handleCreate} className="h-10">
          <Plus size={16} />
          <span className="hidden sm:inline">
            {t("marketplace.createAndPublish")}
          </span>
        </Button>
      )}
      <Button
        variant="secondary"
        onClick={() => fetchSkills()}
        className="h-10"
        title={t("common.refresh")}
      >
        <RotateCw size={16} />
        <span className="hidden sm:inline">{t("common.refresh")}</span>
      </Button>
    </>
  );

  const isInitialLoading =
    isLoading && filteredSkills.length === 0 && !hasActiveFilters;

  if (isInitialLoading) {
    return <MarketplacePanelSkeleton />;
  }

  return (
    <div className="skill-theme-shell flex h-full min-h-0 flex-col">
      {embedded && (
        <PanelHeader
          className="skill-panel-header"
          title={t("marketplace.title")}
          searchOnly
          searchValue={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder={t("marketplace.searchPlaceholder")}
          searchAccessory={filterMenu}
          searchActions={headerActions}
        />
      )}
      {!embedded && (
        <PanelHeader
          className="skill-panel-header"
          title={t("marketplace.title")}
          subtitle={t("marketplace.subtitle")}
          icon={
            <ShoppingBag
              size={20}
              className="text-stone-600 dark:text-stone-400"
            />
          }
          searchValue={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder={t("marketplace.searchPlaceholder")}
          searchAccessory={filterMenu}
          actions={headerActions}
        />
      )}

      {/* Error */}
      {error && (
        <div className="mx-4 mt-4 flex items-center justify-between rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-400">
          <span>{error}</span>
          <IconButton
            aria-label={t("common.close")}
            icon={<X size={18} />}
            onClick={clearError}
            className="hover:text-red-900 dark:hover:text-red-300"
          />
        </div>
      )}

      {/* Skills List */}
      <div className="skill-content-area flex-1 overflow-y-auto py-2 sm:py-4 px-4 sm:p-6 lg:px-8 lg:py-8">
        {filteredSkills.length === 0 ? (
          <EmptyState
            icon={<ShoppingBag size={28} />}
            title={
              hasActiveFilters
                ? t("marketplace.noMatchingSkills")
                : t("marketplace.noSkills")
            }
            description={
              hasActiveFilters
                ? t("marketplace.subtitle")
                : t("marketplace.createHint")
            }
            action={
              hasActiveFilters ? (
                <Button variant="secondary" onClick={clearFilters}>
                  {t("marketplace.clearFilters")}
                </Button>
              ) : undefined
            }
          />
        ) : (
          <div className="grid auto-grid-cols gap-5">
            {filteredSkills.map((skill, index) => (
              <SkillCard
                key={skill.skill_name}
                skill={skill}
                index={index}
                isInstalled={installedMarketplaceNames.has(skill.skill_name)}
                isOwner={skill.is_owner}
                canManage={skill.is_owner || canAdmin}
                canWrite={canWrite}
                installingSkill={installingSkill}
                userSkillsLoading={userSkillsLoading}
                selectedTags={selectedTags}
                openMenuName={openMenuName}
                onInstallClick={handleInstallClick}
                onPreview={() => openPreview(skill)}
                onToggleTag={toggleTag}
                onOpenMenu={setOpenMenuName}
                onEdit={handleEdit}
                onActivate={handleActivate}
                onDelete={handleAdminDelete}
              />
            ))}
          </div>
        )}
      </div>

      {/* Install/Update Confirmation Dialog */}
      <ConfirmDialog
        isOpen={installConfirm?.isOpen ?? false}
        title={
          installConfirm?.action === "install"
            ? t("marketplace.confirmInstall", {
                name: installConfirm?.skillName,
              })
            : t("marketplace.confirmUpdate", {
                name: installConfirm?.skillName,
              })
        }
        message={
          installConfirm?.action === "install"
            ? t("marketplace.confirmInstallMessage")
            : t("marketplace.confirmUpdateMessage")
        }
        confirmText={
          installConfirm?.action === "install"
            ? t("marketplace.install")
            : t("marketplace.update")
        }
        cancelText={t("common.cancel")}
        onConfirm={confirmInstall}
        onCancel={cancelInstall}
        variant="info"
        loading={!!installingSkill}
      />

      {/* Skill Preview Modal */}
      {previewSkill && (
        <SkillPreviewModal
          previewSkill={previewSkill}
          previewFiles={previewFiles}
          previewLoading={previewLoading}
          previewFileContent={previewFileContent}
          previewBinaryFiles={previewBinaryFiles}
          previewFileLoading={previewFileLoading}
          onClose={closePreview}
          onReadFile={readPreviewFile}
          onSetFileContent={setPreviewFileContent}
        />
      )}

      {/* Create / Edit Sidebar */}
      <SkillFormSidebar
        showModal={showCreateModal || !!editingSkill}
        isCreating={isCreating}
        editingSkill={editingSkill}
        isLoading={isLoading}
        onSave={handleSave}
        onCancel={handleFormCancel}
        createTitle={t("marketplace.createTitle")}
        subtitle={t("marketplace.createHint")}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={adminDeleteConfirm?.isOpen ?? false}
        title={t("marketplace.confirmDelete", {
          name: adminDeleteConfirm?.skillName,
        })}
        message={t("marketplace.confirmDeleteMessage")}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        onConfirm={confirmAdminDelete}
        onCancel={() => setAdminDeleteConfirm(null)}
        variant="danger"
      />
    </div>
  );
}
