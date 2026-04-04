import { useState, useEffect } from "react";
import {
  X,
  Download,
  RefreshCw,
  Tag,
  FileText,
  ShoppingBag,
  Plus,
  Trash2,
  Loader2 as Loader2Icon,
  Eye,
  ChevronRight,
  ChevronDown,
  RefreshCcw,
  Pencil,
  AlertTriangle,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { useNavigate } from "react-router-dom";
import { PanelHeader } from "../common/PanelHeader";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { SkillFormModal } from "./SkillsPanel/SkillFormModal";
import { useMarketplace } from "../../hooks/useMarketplace";
import { useSkills } from "../../hooks/useSkills";
import { Permission } from "../../types";
import type { SkillResponse, SkillCreate } from "../../types";
import { useAuth } from "../../hooks/useAuth";

export function MarketplacePanel() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { hasAnyPermission } = useAuth();
  const {
    skills,
    tags,
    isLoading,
    error,
    selectedTags,
    searchQuery,
    setSearchQuery,
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

  // Only marketplace-installed local skills are eligible for "update from marketplace".
  const installedMarketplaceNames = new Set(
    userSkills
      .filter((skill) => skill.installed_from === "marketplace")
      .map((skill) => skill.name),
  );
  const localManualConflicts = new Set(
    userSkills
      .filter((skill) => skill.installed_from !== "marketplace")
      .map((skill) => skill.name),
  );

  // Refresh user skills on mount to know which are installed
  useEffect(() => {
    fetchUserSkills();
  }, [fetchUserSkills]);

  // Install confirmation dialog state
  const [installConfirm, setInstallConfirm] = useState<{
    isOpen: boolean;
    skillName: string;
    action: "install" | "update";
  } | null>(null);
  const [installingSkill, setInstallingSkill] = useState<string | null>(null);

  const [showCreateModal, setShowCreateModal] = useState(false);
  const [isFilterOpen, setIsFilterOpen] = useState(false);

  // Edit modal state
  const [editingSkill, setEditingSkill] = useState<SkillResponse | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isFormFullscreen, setIsFormFullscreen] = useState(false);
  const [isDescExpanded, setIsDescExpanded] = useState(false);

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
        if (action === "install" && localManualConflicts.has(skillName)) {
          toast.error(t("marketplace.installNameConflict"));
        } else {
          toast.error(
            action === "install"
              ? t("marketplace.installFailed")
              : t("marketplace.updateFailed"),
          );
        }
      }
    } finally {
      setInstallingSkill(null);
      setInstallConfirm(null);
    }
  };

  const cancelInstall = () => {
    setInstallConfirm(null);
  };

  // Edit handlers — load from local or marketplace
  const handleEdit = async (skillName: string) => {
    // Try local first
    let fullSkill = await getSkill(skillName);

    // If no local copy, load from marketplace
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
        // 创建：直接发布到商店
        success = await createAndPublish({
          skill_name: data.name,
          description: data.description,
          tags: data.tags,
          version: "1.0.0",
          files: data.files || { "SKILL.md": data.content },
        });
      } else if (editingSkill) {
        // 编辑：直接更新商店
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
        setIsFormFullscreen(false);
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
    setIsFormFullscreen(false);
    setShowCreateModal(false);
  };

  const hasActiveFilters = selectedTags.length > 0 || searchQuery.length > 0;

  return (
    <div className="skill-theme-shell flex h-full min-h-0 flex-col">
      {/* Header */}
      <PanelHeader
        className="skill-panel-header"
        title={t("marketplace.title")}
        subtitle={t("marketplace.subtitle")}
        icon={
          <ShoppingBag
            size={18}
            className="text-stone-600 dark:text-stone-400"
          />
        }
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        searchPlaceholder={t("marketplace.searchPlaceholder")}
        searchAccessory={
          tags.length > 0 ? (
            <div className="relative shrink-0">
              <button
                type="button"
                onClick={() => setIsFilterOpen((prev) => !prev)}
                className={`btn-secondary min-h-10 px-3 ${
                  selectedTags.length > 0
                    ? "border-[var(--theme-primary)] text-[var(--theme-text)]"
                    : ""
                }`}
              >
                <Tag size={14} />
                <span className="hidden sm:inline">
                  {t("adminMarketplace.tags")}
                </span>
                {selectedTags.length > 0 && (
                  <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-[var(--theme-primary-light)] px-1 text-[11px]">
                    {selectedTags.length}
                  </span>
                )}
                <ChevronDown
                  size={14}
                  className={`transition-transform ${
                    isFilterOpen ? "rotate-180" : ""
                  }`}
                />
              </button>
              {isFilterOpen && (
                <div className="skill-filter-dropdown absolute right-0 top-[calc(100%+0.5rem)] z-20 w-72 rounded-2xl border  p-3 shadow-lg">
                  <div className="mb-2 flex items-center justify-between">
                    <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[var(--theme-text-secondary)]">
                      {t("adminMarketplace.tags")}
                    </p>
                    {hasActiveFilters && (
                      <button
                        type="button"
                        onClick={clearFilters}
                        className="text-xs text-[var(--theme-text-secondary)] transition-colors hover:text-[var(--theme-primary)]"
                      >
                        {t("marketplace.clearFilters")}
                      </button>
                    )}
                  </div>
                  <div className="flex max-h-56 flex-wrap gap-2 overflow-y-auto">
                    {tags.map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        onClick={() => toggleTag(tag)}
                        className={`skill-tag-chip ${
                          selectedTags.includes(tag)
                            ? "skill-tag-chip--active"
                            : ""
                        }`}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ) : null
        }
        actions={
          <div className="flex items-center gap-2">
            {canWrite && (
              <button onClick={handleCreate} className="btn-primary">
                <Plus size={16} />
                <span className="hidden sm:inline">
                  {t("marketplace.createAndPublish")}
                </span>
              </button>
            )}
            <button
              onClick={() => fetchSkills()}
              className="btn-secondary"
              title={t("common.refresh")}
            >
              <RefreshCw size={16} className="sm:size-[18px]" />
            </button>
          </div>
        }
      />

      {/* Error */}
      {error && (
        <div className="mx-4 mt-4 flex items-center justify-between rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/30 dark:text-red-400">
          <span>{error}</span>
          <button
            onClick={clearError}
            className="btn-icon hover:text-red-900 dark:hover:text-red-300"
          >
            <X size={18} />
          </button>
        </div>
      )}

      {/* Skills List */}
      <div className="skill-content-area flex-1 overflow-y-auto bg-[var(--theme-bg)] p-4 sm:p-6">
        {isLoading && skills.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[var(--theme-text-secondary)]">
            <LoadingSpinner size="sm" />
            <span className="ml-2">{t("marketplace.loading")}</span>
          </div>
        ) : skills.length === 0 ? (
          <div className="skill-empty-state">
            <div className="skill-empty-state__icon">
              <ShoppingBag size={28} />
            </div>
            <p className="skill-empty-state__title">
              {searchQuery || selectedTags.length > 0
                ? t("marketplace.noMatchingSkills")
                : t("marketplace.noSkills")}
            </p>
            <p className="skill-empty-state__description">
              {searchQuery || selectedTags.length > 0
                ? t("marketplace.subtitle")
                : t("marketplace.createHint")}
            </p>
            {hasActiveFilters && (
              <button onClick={clearFilters} className="btn-secondary mt-4">
                {t("marketplace.clearFilters")}
              </button>
            )}
          </div>
        ) : (
          <div className="skill-grid grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {skills.map((skill) => {
              const isInstalled = installedMarketplaceNames.has(
                skill.skill_name,
              );
              const hasLocalManualConflict = localManualConflicts.has(
                skill.skill_name,
              );
              const isOwner = skill.is_owner;
              const canManage = isOwner || canAdmin;
              return (
                <div
                  key={skill.skill_name}
                  className={`skill-surface-card group flex h-full flex-col rounded-[1.6rem] p-4 sm:p-5 ${
                    skill.is_active
                      ? ""
                      : "skill-surface-card--muted opacity-80"
                  }`}
                >
                  <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[var(--theme-primary)]/20 to-transparent opacity-0 transition-opacity duration-200 group-hover:opacity-100" />
                  <div className="relative flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate text-lg font-semibold text-[var(--theme-text)]">
                          {skill.skill_name}
                        </h3>
                        <span
                          className={`skill-status-pill ${
                            skill.is_active
                              ? "skill-status-pill--active"
                              : "skill-status-pill--disabled"
                          }`}
                        >
                          {skill.is_active
                            ? t("marketplace.active")
                            : t("marketplace.inactive")}
                        </span>
                        {isInstalled && (
                          <span className="skill-status-pill skill-status-pill--installed">
                            {t("marketplace.installed")}
                          </span>
                        )}
                        {hasLocalManualConflict && (
                          <span className="skill-status-pill skill-status-pill--disabled">
                            {t("marketplace.nameConflict")}
                          </span>
                        )}
                      </div>
                      <p className="mt-2 text-sm leading-relaxed text-[var(--theme-text-secondary)] line-clamp-3 min-h-[3.75rem]">
                        {skill.description || t("marketplace.noDescription")}
                      </p>
                      {hasLocalManualConflict && (
                        <div className="mt-3 rounded-xl border border-amber-200 bg-amber-50/90 px-3 py-2 text-xs text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-300">
                          <div className="flex items-start gap-2">
                            <AlertTriangle
                              size={14}
                              className="mt-0.5 shrink-0"
                            />
                            <span>{t("marketplace.installNameConflict")}</span>
                          </div>
                          <button
                            type="button"
                            onClick={() =>
                              navigate("/skills", {
                                state: { prefillSkillSearch: skill.skill_name },
                              })
                            }
                            className="mt-2 inline-flex items-center gap-1.5 font-medium text-amber-900 underline decoration-amber-400 underline-offset-2 transition-colors hover:text-amber-950 dark:text-amber-200 dark:decoration-amber-700 dark:hover:text-amber-100"
                          >
                            <Pencil size={13} />
                            <span>{t("marketplace.viewInMySkills")}</span>
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-[var(--theme-text-secondary)]">
                    <div className="skill-meta-pill">
                      <FileText size={13} />
                      <span>
                        {skill.file_count} {t("marketplace.files")}
                      </span>
                    </div>
                    <div className="skill-meta-pill">v{skill.version}</div>
                    {skill.created_by_username && (
                      <div className="skill-meta-pill truncate">
                        {t("marketplace.publishedBy", {
                          username: skill.created_by_username,
                        })}
                      </div>
                    )}
                  </div>

                  {skill.tags.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {skill.tags.slice(0, 4).map((tag) => (
                        <button
                          key={tag}
                          type="button"
                          onClick={() => toggleTag(tag)}
                          className={`skill-tag-chip ${
                            selectedTags.includes(tag)
                              ? "skill-tag-chip--active"
                              : ""
                          }`}
                        >
                          {tag}
                        </button>
                      ))}
                      {skill.tags.length > 4 && (
                        <span className="skill-tag-chip">
                          +{skill.tags.length - 4}
                        </span>
                      )}
                    </div>
                  )}

                  <div className="mt-auto space-y-3 pt-5">
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => openPreview(skill)}
                        className="btn-secondary text-xs flex min-h-9 items-center gap-1.5 px-3 py-2"
                      >
                        <Eye size={14} />
                        <span>{t("marketplace.preview")}</span>
                      </button>
                      {canWrite &&
                        (installingSkill === skill.skill_name ? (
                          <button
                            disabled
                            className="btn-primary opacity-50 text-xs min-h-9 px-3 py-2"
                          >
                            <Loader2Icon size={14} className="animate-spin" />
                            <span>{t("marketplace.installing")}</span>
                          </button>
                        ) : userSkillsLoading ? (
                          <span className="inline-flex min-h-9 items-center text-xs text-[var(--theme-text-secondary)] px-2">
                            <Loader2Icon
                              size={14}
                              className="animate-spin inline mr-1"
                            />
                          </span>
                        ) : (
                          <button
                            onClick={() => handleInstallClick(skill.skill_name)}
                            disabled={hasLocalManualConflict}
                            title={
                              hasLocalManualConflict
                                ? t("marketplace.installNameConflict")
                                : undefined
                            }
                            className={`text-xs flex min-h-9 items-center gap-1.5 px-3 py-2 ${
                              hasLocalManualConflict
                                ? "btn-secondary cursor-not-allowed opacity-60"
                                : isInstalled
                                  ? "btn-secondary"
                                  : "btn-primary shadow-sm"
                            }`}
                          >
                            {hasLocalManualConflict ? (
                              <>
                                <AlertTriangle size={14} />
                                <span>{t("marketplace.nameConflict")}</span>
                              </>
                            ) : isInstalled ? (
                              <>
                                <RefreshCcw size={14} />
                                <span>{t("marketplace.update")}</span>
                              </>
                            ) : (
                              <>
                                <Download size={14} />
                                <span>{t("marketplace.install")}</span>
                              </>
                            )}
                          </button>
                        ))}
                    </div>

                    {canManage && (
                      <div className="flex flex-wrap items-center gap-2 border-t border-[var(--theme-border)] pt-3">
                        {isOwner && (
                          <button
                            onClick={() => handleEdit(skill.skill_name)}
                            className="btn-secondary text-xs flex min-h-9 items-center gap-1.5 px-3 py-1.5"
                          >
                            <Pencil size={14} />
                            <span>{t("common.edit")}</span>
                          </button>
                        )}
                        <div className="flex-1" />
                        <button
                          onClick={() =>
                            handleActivate(skill.skill_name, !skill.is_active)
                          }
                          className={`skill-status-pill min-h-9 px-3 py-1.5 text-xs transition-all ${
                            skill.is_active
                              ? "skill-status-pill--active"
                              : "skill-status-pill--disabled"
                          }`}
                        >
                          {skill.is_active
                            ? t("marketplace.active")
                            : t("marketplace.inactive")}
                        </button>
                        <button
                          onClick={() => handleAdminDelete(skill.skill_name)}
                          className="inline-flex h-9 w-9 items-center justify-center rounded-xl text-[var(--theme-text-secondary)] transition-colors hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20 dark:hover:text-red-400"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
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
      />

      {/* Skill Preview Modal */}
      {previewSkill && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/55 p-0 backdrop-blur-sm sm:items-center sm:p-4">
          <div className="skill-preview-shell flex max-h-[92vh] w-full flex-col overflow-hidden rounded-t-[1.5rem] border sm:max-h-[88vh] sm:max-w-4xl sm:rounded-[1.75rem] shadow-[0_-16px_48px_-16px_rgba(15,23,42,0.3)] sm:shadow-[0_32px_80px_-32px_rgba(15,23,42,0.55)]">
            {/* Modal Header */}
            <div className="border-b border-[var(--theme-border)] bg-[var(--theme-bg)]/88 px-4 py-4 backdrop-blur sm:px-6 sm:py-5">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2.5 sm:gap-3 min-w-0">
                    <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-xl bg-[var(--theme-primary-light)] text-[var(--theme-primary)] shadow-sm sm:h-11 sm:w-11 sm:rounded-2xl">
                      <ShoppingBag size={16} className="sm:size-[20px]" />
                    </div>
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
                        <h2 className="truncate text-base font-semibold text-[var(--theme-text)] sm:text-lg">
                          {previewSkill.skill_name}
                        </h2>
                        <span className="skill-meta-pill text-[10px] sm:text-xs">
                          v{previewSkill.version}
                        </span>
                      </div>
                      <button
                        type="button"
                        onClick={() => setIsDescExpanded((v) => !v)}
                        className="mt-1 text-left text-sm leading-relaxed text-[var(--theme-text-secondary)]"
                      >
                        <span className={!isDescExpanded ? "line-clamp-2" : ""}>
                          {previewSkill.description ||
                            t("marketplace.noDescription")}
                        </span>
                        {(previewSkill.description?.length || 0) > 80 && (
                          <span className="ml-1 inline-flex items-center gap-0.5 text-xs text-[var(--theme-primary)]">
                            {isDescExpanded
                              ? t("marketplace.previewCollapse")
                              : t("marketplace.previewExpand")}
                            <ChevronDown
                              size={12}
                              className={`transition-transform ${
                                isDescExpanded ? "rotate-180" : ""
                              }`}
                            />
                          </span>
                        )}
                      </button>
                    </div>
                  </div>
                  {previewSkill.tags.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1.5 sm:mt-4 sm:gap-2">
                      {previewSkill.tags.slice(0, 3).map((tag) => (
                        <span
                          key={tag}
                          className="skill-tag-chip skill-tag-chip--active text-[10px] sm:text-xs"
                        >
                          {tag}
                        </span>
                      ))}
                      {previewSkill.tags.length > 3 && (
                        <span className="skill-tag-chip text-[10px] sm:text-xs">
                          +{previewSkill.tags.length - 3}
                        </span>
                      )}
                    </div>
                  )}
                </div>
                <button
                  onClick={closePreview}
                  className="btn-icon -mr-1 -mt-1 hover:bg-[var(--theme-bg-card)]"
                >
                  <X size={20} />
                </button>
              </div>
            </div>

            {/* Modal Body */}
            <div className="skill-modal-body flex-1 overflow-y-auto px-4 py-4 sm:px-6 sm:py-5">
              {/* Files */}
              {previewLoading ? (
                <div className="flex items-center gap-2 text-sm text-[var(--theme-text-secondary)]">
                  <LoadingSpinner size="sm" />
                  <span>{t("marketplace.loadingFiles")}</span>
                </div>
              ) : previewFiles ? (
                <div>
                  <h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-[var(--theme-text)]">
                    <FileText
                      size={16}
                      className="text-[var(--theme-primary)]"
                    />
                    {t("marketplace.skillFiles")} ({previewFiles.files.length})
                  </h3>
                  <div className="space-y-3">
                    {previewFiles.files.map((filePath) => {
                      const isOpen = Boolean(previewFileContent[filePath]);
                      const isLoadingFile = previewFileLoading === filePath;

                      return (
                        <div
                          key={filePath}
                          className="overflow-hidden rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)]/78 shadow-sm"
                        >
                          <button
                            onClick={() => {
                              if (isOpen) {
                                setPreviewFileContent((prev) => {
                                  const next = { ...prev };
                                  delete next[filePath];
                                  return next;
                                });
                                return;
                              }
                              readPreviewFile(
                                previewSkill.skill_name,
                                filePath,
                              );
                            }}
                            className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--theme-primary-light)]/80"
                          >
                            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-[var(--theme-primary-light)] text-[var(--theme-primary)]">
                              <FileText size={14} />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-sm font-medium text-[var(--theme-text)]">
                                {filePath}
                              </div>
                              <div className="text-xs text-[var(--theme-text-secondary)]">
                                {isOpen
                                  ? t("marketplace.previewCollapse")
                                  : t("marketplace.previewExpand")}
                              </div>
                            </div>
                            {isLoadingFile ? (
                              <Loader2Icon
                                size={16}
                                className="animate-spin text-[var(--theme-text-secondary)]"
                              />
                            ) : (
                              <ChevronRight
                                size={16}
                                className={`text-[var(--theme-text-secondary)] transition-transform ${
                                  isOpen ? "rotate-90" : ""
                                }`}
                              />
                            )}
                          </button>
                          {isOpen && (
                            <div className="border-t /92 p-4">
                              <pre className="max-h-72 overflow-auto rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] p-4 text-xs leading-6 text-[var(--theme-text)] whitespace-pre-wrap break-all font-mono">
                                {previewFileContent[filePath]}
                              </pre>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-[var(--theme-text-secondary)]">
                  {t("marketplace.noFiles")}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Create / Edit Modal */}
      <SkillFormModal
        showModal={showCreateModal || !!editingSkill}
        isCreating={isCreating}
        isFormFullscreen={isFormFullscreen}
        editingSkill={editingSkill}
        isLoading={isLoading}
        onSave={handleSave}
        onCancel={handleFormCancel}
        onFullscreenChange={setIsFormFullscreen}
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
