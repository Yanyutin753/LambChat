import { useTranslation } from "react-i18next";
import { PackageX } from "lucide-react";
import { useAuth } from "../../../hooks/useAuth";
import { useSettingsContext } from "../../../contexts/SettingsContext";
import { Permission } from "../../../types";
import { ConfirmDialog } from "../../common/ConfirmDialog";
import { useSkillsActions } from "./useSkillsActions";
import { SkillsList } from "./SkillsList";
import { SkillFormModal } from "./SkillFormModal";
import { ZipUploadModal } from "./ZipUploadModal";
import { GithubImportModal } from "./GithubImportModal";
import { BatchActionBar } from "./BatchActionBar";
import { PublishDialog } from "./PublishDialog";

export function SkillsPanel() {
  const { t } = useTranslation();
  const { enableSkills } = useSettingsContext();
  const { hasAnyPermission } = useAuth();

  const canRead = hasAnyPermission([Permission.SKILL_READ]);
  const canWrite = hasAnyPermission([Permission.SKILL_WRITE]);
  const canPublish = hasAnyPermission([Permission.MARKETPLACE_PUBLISH]);

  const actions = useSkillsActions();

  if (!canRead) {
    return (
      <div className="flex h-full items-center justify-center text-stone-500 dark:text-stone-400">
        {t("skills.noPermission")}
      </div>
    );
  }

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

  return (
    <div className="skill-theme-shell flex h-full min-h-0 flex-col">
      <SkillsList
        searchQuery={actions.searchQuery}
        setSearchQuery={actions.setSearchQuery}
        selectedTags={actions.selectedTags}
        isFilterOpen={actions.isFilterOpen}
        setIsFilterOpen={actions.setIsFilterOpen}
        availableTags={actions.availableTags}
        filteredSkills={actions.filteredSkills}
        paginatedSkills={actions.paginatedSkills}
        total={actions.total}
        page={actions.page}
        pageSize={actions.pageSize}
        setPage={actions.setPage}
        toggleTag={actions.toggleTag}
        clearFilters={actions.clearFilters}
        isLoading={actions.isLoading}
        error={actions.error}
        clearError={actions.clearError}
        canWrite={canWrite}
        canPublish={canPublish}
        selectedNames={actions.selectedNames}
        onToggle={actions.handleToggle}
        onEdit={actions.handleEdit}
        onDelete={actions.handleDelete}
        onExportZip={actions.handleExportZip}
        onPublish={
          canPublish
            ? (s) => {
                actions.setPublishConfirm({
                  isOpen: true,
                  localSkillName: s.name,
                  marketplaceSkillName:
                    s.published_marketplace_name || s.name,
                  description: s.description || "",
                  tagsInput: s.tags?.join(", ") || "",
                  isPublished: s.is_published,
                });
              }
            : undefined
        }
        onSelectSkill={actions.handleSelectSkill}
        onSelectAll={actions.handleSelectAll}
        onCreate={actions.handleCreate}
        onGithubClick={actions.handleGithubClick}
        onZipClick={actions.handleZipClick}
      />

      <SkillFormModal
        showModal={actions.showModal}
        isCreating={actions.isCreating}
        isFormFullscreen={actions.isFormFullscreen}
        editingSkill={actions.editingSkill}
        isLoading={actions.isLoading}
        onSave={actions.handleSave}
        onCancel={actions.handleCancel}
        onFullscreenChange={actions.setIsFormFullscreen}
      />

      <ZipUploadModal
        showZipModal={actions.showZipModal}
        setShowZipModal={actions.setShowZipModal}
        zipFile={actions.zipFile}
        zipUploading={actions.zipUploading}
        zipPreviewing={actions.zipPreviewing}
        zipSkills={actions.zipSkills}
        selectedZipSkills={actions.selectedZipSkills}
        zipInputRef={actions.zipInputRef}
        isDragging={actions.isDragging}
        onZipFileChange={actions.handleZipFileChange}
        onDragOver={actions.handleDragOver}
        onDragLeave={actions.handleDragLeave}
        onDrop={actions.handleDrop}
        onZipSkillToggle={actions.handleZipSkillToggle}
        onZipSelectAll={actions.handleZipSelectAll}
        onZipUpload={actions.handleZipUpload}
      />

      <GithubImportModal
        showGithubModal={actions.showGithubModal}
        setShowGithubModal={actions.setShowGithubModal}
        githubUrl={actions.githubUrl}
        setGithubUrl={actions.setGithubUrl}
        githubBranch={actions.githubBranch}
        setGithubBranch={actions.setGithubBranch}
        githubSkills={actions.githubSkills}
        selectedGithubSkills={actions.selectedGithubSkills}
        githubLoading={actions.githubLoading}
        githubInstalling={actions.githubInstalling}
        githubExporting={actions.githubExporting}
        onGithubPreview={actions.handleGithubPreview}
        onGithubSkillToggle={actions.handleGithubSkillToggle}
        onGithubInstall={actions.handleGithubInstall}
        onGithubExport={actions.handleGithubExport}
        setSelectedGithubSkills={actions.setSelectedGithubSkills}
      />

      {actions.selectionMode && (
        <BatchActionBar
          selectedCount={actions.selectedNames.size}
          batchLoading={actions.batchLoading}
          onBatchToggle={actions.handleBatchToggle}
          onBatchDelete={actions.handleBatchDelete}
          onClearSelection={actions.clearSelection}
        />
      )}

      <ConfirmDialog
        isOpen={actions.isDeleteConfirmOpen}
        title={t("skills.confirmDelete", {
          name: actions.deleteConfirmData?.name || "",
        })}
        message={t("skills.confirmDeleteMessage", {
          name: actions.deleteConfirmData?.name || "",
        })}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        onConfirm={actions.confirmDelete}
        onCancel={actions.cancelDelete}
        variant="danger"
      />

      <PublishDialog
        publishConfirm={actions.publishConfirm}
        setPublishConfirm={actions.setPublishConfirm}
        onConfirm={actions.confirmPublish}
      />
    </div>
  );
}
