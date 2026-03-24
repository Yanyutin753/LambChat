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
  RefreshCcw,
  Pencil,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { SkillForm } from "../skill/SkillForm";
import { useMarketplace } from "../../hooks/useMarketplace";
import { useSkills } from "../../hooks/useSkills";
import { Permission } from "../../types";
import type { SkillResponse, SkillCreate } from "../../types";
import { useAuth } from "../../hooks/useAuth";

export function MarketplacePanel() {
  const { t } = useTranslation();
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

  const { skills: userSkills, fetchSkills: fetchUserSkills, isLoading: userSkillsLoading, getSkill } = useSkills();
  const canWrite = hasAnyPermission([Permission.SKILL_WRITE]);
  const canAdmin = hasAnyPermission([Permission.SKILL_ADMIN]);

  // Build set of installed skill names
  const installedNames = new Set(userSkills.map((s) => s.name));

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

  // Edit modal state
  const [editingSkill, setEditingSkill] = useState<SkillResponse | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [isFormFullscreen, setIsFormFullscreen] = useState(false);

  const [adminDeleteConfirm, setAdminDeleteConfirm] = useState<{
    isOpen: boolean;
    skillName: string;
  } | null>(null);

  const handleActivate = async (skillName: string, isActive: boolean) => {
    const success = await activateSkill(skillName, isActive);
    if (success) {
      toast.success(isActive ? t("marketplace.activateSuccess") : t("marketplace.deactivateSuccess"));
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
    const action = installedNames.has(skillName) ? "update" : "install";
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
  };

  const handleSave = async (data: SkillCreate): Promise<boolean> => {
    try {
      let success = false;
      if (isCreating) {
        // 创建：直接发布到商店
        success = await createAndPublish({
          skill_name: data.name,
          description: data.description,
          tags: [],
          version: "1.0.0",
          files: data.files || { "SKILL.md": data.content },
        });
      } else if (editingSkill) {
        // 编辑：直接更新商店
        success = await updateMarketplaceSkill(editingSkill.name, {
          skill_name: editingSkill.name,
          description: data.description,
          tags: [],
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
    <div className="flex h-full flex-col min-h-0">
      {/* Header */}
      <PanelHeader
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
        actions={
          <div className="flex items-center gap-2">
            {canWrite && (
              <button onClick={handleCreate} className="btn-primary">
                <Plus size={16} />
                <span className="hidden sm:inline">{t("marketplace.createAndPublish")}</span>
              </button>
            )}
            <button onClick={() => fetchSkills()} className="btn-secondary" title={t("common.refresh")}>
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

      {/* Tags Filter */}
      {tags.length > 0 && (
        <div className="border-b px-4 py-3 bg-[var(--theme-bg)] border-[var(--theme-border)]">
          <div className="flex items-center gap-2 flex-wrap">
            <Tag size={14} className="text-[var(--theme-text-secondary)] flex-shrink-0" />
            {tags.map((tag) => (
              <button
                key={tag}
                onClick={() => toggleTag(tag)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition-all ${
                  selectedTags.includes(tag)
                    ? "bg-[var(--theme-primary)] text-white shadow-sm"
                    : "bg-[var(--theme-primary-light)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-primary)] hover:text-white"
                }`}
              >
                {tag}
              </button>
            ))}
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="text-xs text-[var(--theme-text-secondary)] hover:text-[var(--theme-primary)] transition-colors ml-1"
              >
                {t("common.clear")}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Skills List */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6 bg-[var(--theme-bg)]">
        {isLoading && skills.length === 0 ? (
          <div className="flex h-full items-center justify-center text-[var(--theme-text-secondary)]">
            <LoadingSpinner size="sm" />
            <span className="ml-2">{t("marketplace.loading")}</span>
          </div>
        ) : skills.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-[var(--theme-text-secondary)] px-4">
            <ShoppingBag
              size={48}
              className="mb-4 text-[var(--theme-primary)] opacity-40"
            />
            <p className="text-sm sm:text-base">
              {searchQuery || selectedTags.length > 0
                ? t("marketplace.noMatchingSkills")
                : t("marketplace.noSkills")}
            </p>
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="mt-3 text-sm text-[var(--theme-primary)] hover:text-[var(--theme-primary-hover)] transition-colors"
              >
                {t("marketplace.clearFilters")}
              </button>
            )}
          </div>
        ) : (
          <div className="grid gap-4 grid-cols-1 xl:grid-cols-2 2xl:grid-cols-3">
            {skills.map((skill) => {
              const isInstalled = installedNames.has(skill.skill_name);
              const isOwner = skill.is_owner;
              const canManage = isOwner || canAdmin;
              return (
                <div
                  key={skill.skill_name}
                  className={`group flex h-full flex-col rounded-2xl border p-4 sm:p-5 transition-all duration-200 ${
                    skill.is_active
                      ? "border-[var(--theme-border)] bg-[var(--theme-bg-card)] hover:shadow-lg hover:border-[var(--theme-primary)]"
                      : "border-[var(--theme-border)] bg-[var(--theme-bg-secondary)] opacity-70"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="truncate text-lg font-semibold text-[var(--theme-text)]">
                          {skill.skill_name}
                        </h3>
                        <span
                          className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                            skill.is_active
                              ? "bg-[var(--theme-primary-light)] text-[var(--theme-primary)]"
                              : "bg-stone-200 text-stone-600 dark:bg-stone-700 dark:text-stone-300"
                          }`}
                        >
                          {skill.is_active ? t("marketplace.active") : t("marketplace.inactive")}
                        </span>
                        {isInstalled && (
                          <span className="rounded-full bg-green-100 px-2.5 py-1 text-[11px] font-medium text-green-700 dark:bg-green-900/40 dark:text-green-300">
                            {t("marketplace.installed")}
                          </span>
                        )}
                      </div>
                      <p className="mt-2 text-sm leading-relaxed text-[var(--theme-text-secondary)] line-clamp-3 min-h-[3.75rem]">
                        {skill.description || t("marketplace.noDescription")}
                      </p>
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-[var(--theme-text-secondary)]">
                    <div className="inline-flex items-center gap-1.5 rounded-full bg-[var(--theme-bg)] px-2.5 py-1 border border-[var(--theme-border)]">
                      <FileText size={13} />
                      <span>
                        {skill.file_count} {t("marketplace.files")}
                      </span>
                    </div>
                    <div className="inline-flex items-center rounded-full bg-[var(--theme-bg)] px-2.5 py-1 border border-[var(--theme-border)]">
                      v{skill.version}
                    </div>
                    {skill.created_by_username && (
                      <div className="truncate rounded-full bg-[var(--theme-bg)] px-2.5 py-1 border border-[var(--theme-border)] max-w-full">
                        {t("marketplace.publishedBy", { username: skill.created_by_username })}
                      </div>
                    )}
                  </div>

                  {skill.tags.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {skill.tags.slice(0, 4).map((tag) => (
                        <span
                          key={tag}
                          className="rounded-full bg-[var(--theme-primary-light)] px-2.5 py-1 text-xs font-medium text-[var(--theme-text-secondary)]"
                        >
                          {tag}
                        </span>
                      ))}
                      {skill.tags.length > 4 && (
                        <span className="rounded-full bg-[var(--theme-bg)] px-2.5 py-1 text-xs text-[var(--theme-text-secondary)] border border-[var(--theme-border)]">
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
                      {canWrite && (
                        installingSkill === skill.skill_name ? (
                          <button disabled className="btn-primary opacity-50 text-xs min-h-9 px-3 py-2">
                            <Loader2Icon size={14} className="animate-spin" />
                            <span>{t("marketplace.installing")}</span>
                          </button>
                        ) : userSkillsLoading ? (
                          <span className="inline-flex min-h-9 items-center text-xs text-[var(--theme-text-secondary)] px-2">
                            <Loader2Icon size={14} className="animate-spin inline mr-1" />
                          </span>
                        ) : (
                          <button
                            onClick={() => handleInstallClick(skill.skill_name)}
                            className={`text-xs flex min-h-9 items-center gap-1.5 px-3 py-2 ${
                              isInstalled ? "btn-secondary" : "btn-primary shadow-sm"
                            }`}
                          >
                            {isInstalled ? (
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
                        )
                      )}
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
                          onClick={() => handleActivate(skill.skill_name, !skill.is_active)}
                          className={`text-xs min-h-9 rounded-full px-3 py-1.5 font-medium transition-all ${
                            skill.is_active
                              ? "bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300 shadow-sm"
                              : "bg-[var(--theme-primary-light)] text-[var(--theme-text-secondary)] hover:bg-[var(--theme-primary)] hover:text-white"
                          }`}
                        >
                          {skill.is_active ? t("marketplace.active") : t("marketplace.inactive")}
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="w-full max-w-3xl max-h-[85vh] flex flex-col rounded-2xl bg-[var(--theme-bg-card)] shadow-2xl border border-[var(--theme-border)]">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-[var(--theme-border)] px-6 py-4 bg-[var(--theme-primary-light)]">
              <div className="flex items-center gap-3 min-w-0">
                <ShoppingBag
                  size={20}
                  className="text-[var(--theme-primary)] flex-shrink-0"
                />
                <h2 className="text-lg font-semibold text-[var(--theme-text)] truncate">
                  {previewSkill.skill_name}
                </h2>
                <span className="text-xs text-[var(--theme-text-secondary)] bg-[var(--theme-bg-card)] px-2 py-1 rounded-full">
                  v{previewSkill.version}
                </span>
              </div>
              <button onClick={closePreview} className="btn-icon hover:bg-[var(--theme-bg-card)]">
                <X size={20} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-6">
              {/* Description */}
              <p className="text-sm text-[var(--theme-text-secondary)] mb-4 leading-relaxed">
                {previewSkill.description || t("marketplace.noDescription")}
              </p>

              {/* Tags */}
              {previewSkill.tags.length > 0 && (
                <div className="flex flex-wrap gap-2 mb-5">
                  {previewSkill.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-[var(--theme-primary-light)] px-3 py-1 text-xs text-[var(--theme-text-secondary)] font-medium"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}

              {/* Files */}
              {previewLoading ? (
                <div className="flex items-center gap-2 text-sm text-[var(--theme-text-secondary)]">
                  <LoadingSpinner size="sm" />
                  <span>{t("marketplace.loadingFiles")}</span>
                </div>
              ) : previewFiles ? (
                <div>
                  <h3 className="text-sm font-semibold text-[var(--theme-text)] mb-3 flex items-center gap-2">
                    <FileText size={16} className="text-[var(--theme-primary)]" />
                    {t("marketplace.skillFiles")} ({previewFiles.files.length})
                  </h3>
                  <div className="space-y-3">
                    {previewFiles.files.map((filePath) => {
                      const isOpen = Boolean(previewFileContent[filePath]);
                      const isLoadingFile = previewFileLoading === filePath;

                      return (
                        <div
                          key={filePath}
                          className="overflow-hidden rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)]"
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
                              readPreviewFile(previewSkill.skill_name, filePath);
                            }}
                            className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-[var(--theme-primary-light)]"
                          >
                            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--theme-primary-light)] text-[var(--theme-primary)]">
                              <FileText size={14} />
                            </div>
                            <div className="min-w-0 flex-1">
                              <div className="truncate text-sm font-medium text-[var(--theme-text)]">
                                {filePath}
                              </div>
                              <div className="text-xs text-[var(--theme-text-secondary)]">
                                {isOpen ? "Click to collapse" : "Click to preview"}
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
                            <div className="border-t border-[var(--theme-border)] bg-[var(--theme-bg-card)] p-4">
                              <pre className="max-h-72 overflow-auto rounded-lg bg-[var(--theme-bg)] p-4 text-xs text-[var(--theme-text)] whitespace-pre-wrap break-all font-mono leading-6">
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
      {(showCreateModal || editingSkill) && (
        <>
          {!isFormFullscreen && (
            <div className="fixed inset-0" onClick={handleFormCancel} />
          )}
          <div className="modal-bottom-sheet sm:modal-centered-wrapper">
            <div className="modal-bottom-sheet-content sm:modal-centered-content">
              {!isFormFullscreen && (
                <>
                  <div className="bottom-sheet-handle sm:hidden" />
                  <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4 dark:border-stone-800 shrink-0">
                    <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 font-serif">
                      {isCreating
                        ? t("marketplace.createTitle")
                        : t("skills.editSkill", { name: editingSkill?.name })}
                    </h3>
                    <button onClick={handleFormCancel} className="btn-icon">
                      <X size={20} />
                    </button>
                  </div>
                </>
              )}
              <div className="flex-1 min-h-0 overflow-hidden flex flex-col px-2 sm:px-4 py-2 sm:py-3">
                <SkillForm
                  skill={editingSkill}
                  onSave={handleSave}
                  onCancel={handleFormCancel}
                  isLoading={isLoading}
                  onFullscreenChange={setIsFormFullscreen}
                />
              </div>
            </div>
          </div>
        </>
      )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={adminDeleteConfirm?.isOpen ?? false}
        title={t("marketplace.confirmDelete", { name: adminDeleteConfirm?.skillName })}
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
