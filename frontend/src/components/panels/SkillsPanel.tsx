/**
 * SkillsPanel - Simplified Architecture
 *
 * New backend supports:
 * - List, get, create, update, delete user skills
 * - Toggle skill enabled/disabled
 * - Marketplace browse and install
 * - ZIP upload
 * - GitHub import
 */

import { useState, useEffect, useRef } from "react";
import { Plus, X, FolderOpen, PackageX, Archive, Upload, Github, Check, Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { exportProjectZip } from "../../utils/exportProjectZip";
import { PanelHeader } from "../common/PanelHeader";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { Pagination } from "../common/Pagination";
import { SkillCard } from "../skill/SkillCard";
import { SkillForm } from "../skill/SkillForm";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { useSkills } from "../../hooks/useSkills";
import { useAuth } from "../../hooks/useAuth";
import { useSettingsContext } from "../../contexts/SettingsContext";
import { Permission } from "../../types";
import type { SkillResponse, SkillCreate } from "../../types";
import {
  collectSkillTags,
  skillMatchesQuery,
} from "../../utils/skillFilters";

interface GitHubSkill {
  name: string;
  path: string;
  description: string;
}

export function SkillsPanel() {
  const { t } = useTranslation();
  const { enableSkills } = useSettingsContext();
  const {
    skills,
    isLoading,
    error,
    getSkill,
    createSkill,
    updateSkill,
    deleteSkill,
    toggleSkill,
    uploadSkill,
    previewGitHubSkills,
    installGitHubSkills,
    publishToMarketplace,
    clearError,
  } = useSkills();
  const { hasAnyPermission } = useAuth();

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [editingSkill, setEditingSkill] = useState<SkillResponse | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [isFormFullscreen, setIsFormFullscreen] = useState(false);

  // Pagination state
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  // ZIP upload state
  const [showZipModal, setShowZipModal] = useState(false);
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [zipUploading, setZipUploading] = useState(false);
  const zipInputRef = useRef<HTMLInputElement>(null);

  // GitHub import state
  const [showGithubModal, setShowGithubModal] = useState(false);
  const [githubUrl, setGithubUrl] = useState("");
  const [githubBranch, setGithubBranch] = useState("main");
  const [githubSkills, setGithubSkills] = useState<GitHubSkill[]>([]);
  const [selectedGithubSkills, setSelectedGithubSkills] = useState<string[]>([]);
  const [githubLoading, setGithubLoading] = useState(false);
  const [githubInstalling, setGithubInstalling] = useState(false);
  const [githubExporting, setGithubExporting] = useState(false);

  // Update total when skills change
  useEffect(() => {
    setTotal(skills.length);
  }, [skills]);

  // Reset to page 1 when search changes
  useEffect(() => {
    setPage(1);
  }, [searchQuery, selectedTags]);

  // Delete confirmation dialog state
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [deleteConfirmData, setDeleteConfirmData] = useState<{
    name: string;
  } | null>(null);

  // Publish confirmation dialog state
  const [publishConfirm, setPublishConfirm] = useState<{
    isOpen: boolean;
    localSkillName: string;
    marketplaceSkillName: string;
    description: string;
    tagsInput: string;
    isPublished: boolean;
    error?: string;
  } | null>(null);

  const canRead = hasAnyPermission([Permission.SKILL_READ]);
  const canWrite = hasAnyPermission([Permission.SKILL_WRITE]);

  const availableTags = collectSkillTags(skills);

  const filteredSkills = skills.filter((skill) => {
    const matchesQuery = skillMatchesQuery(skill, searchQuery);
    const matchesTags =
      selectedTags.length === 0 ||
      selectedTags.every((tag) => skill.tags.includes(tag));

    return matchesQuery && matchesTags;
  });

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((item) => item !== tag) : [...prev, tag],
    );
  };

  const clearFilters = () => {
    setSearchQuery("");
    setSelectedTags([]);
  };

  // Get paginated skills
  const paginatedSkills = filteredSkills.slice(
    (page - 1) * pageSize,
    page * pageSize,
  );

  const handleCreate = () => {
    setIsCreating(true);
    setEditingSkill(null);
    setShowModal(true);
  };

  const handleEdit = async (skill: SkillResponse) => {
    // 加载完整的文件内容
    const fullSkill = await getSkill(skill.name);
    setEditingSkill(fullSkill || skill);
    setIsCreating(false);
    setShowModal(true);
  };

  const handleSave = async (data: SkillCreate): Promise<boolean> => {
    let success = false;

    try {
      if (isCreating) {
        success = await createSkill(data);
      } else if (editingSkill) {
        // 计算被删除的文件
        const oldFiles = Object.keys(editingSkill.files);
        const newFiles = data.files ? Object.keys(data.files) : [];
        const deletedFiles = oldFiles.filter((f) => !newFiles.includes(f));

        success = await updateSkill(editingSkill.name, {
          description: data.description,
          content: data.content,
          files: data.files,
          deletedFiles,
        });
      }

      if (success) {
        setShowModal(false);
        setEditingSkill(null);
        setIsCreating(false);
      }
    } catch {
      success = false;
    }

    return success;
  };

  const handleCancel = () => {
    setShowModal(false);
    setEditingSkill(null);
    setIsCreating(false);
    setIsFormFullscreen(false);
  };

  const handleExportZip = async (name: string) => {
    const fullSkill = await getSkill(name);
    if (!fullSkill) {
      toast.error(t("skills.exportFailed"));
      return;
    }

    try {
      await exportProjectZip(fullSkill.files, name);
      toast.success(t("skills.exportSuccess"));
    } catch {
      toast.error(t("skills.exportFailed"));
    }
  };

  const handleDelete = (name: string) => {
    setDeleteConfirmData({ name });
    setIsDeleteConfirmOpen(true);
  };

  const confirmDelete = async () => {
    if (!deleteConfirmData) return;
    try {
      await deleteSkill(deleteConfirmData.name);
    } finally {
      setIsDeleteConfirmOpen(false);
      setDeleteConfirmData(null);
    }
  };

  const cancelDelete = () => {
    setIsDeleteConfirmOpen(false);
    setDeleteConfirmData(null);
  };

  const handleToggle = async (name: string) => {
    await toggleSkill(name);
  };

  const confirmPublish = async () => {
    if (!publishConfirm) return;
    const { localSkillName, marketplaceSkillName, description } = publishConfirm;

    if (!marketplaceSkillName.trim()) {
      setPublishConfirm({
        ...publishConfirm,
        error: t("skills.form.validation.nameRequired"),
      });
      return;
    }
    if (!/^[\w\u4e00-\u9fff\-.]+$/.test(marketplaceSkillName.trim())) {
      setPublishConfirm({
        ...publishConfirm,
        error: t("skills.form.validation.nameInvalid"),
      });
      return;
    }
    if (!description.trim()) {
      setPublishConfirm({
        ...publishConfirm,
        error: t("skills.form.validation.descriptionRequired"),
      });
      return;
    }

    const normalizedTags = Array.from(
      new Set(
        publishConfirm.tagsInput
          .split(",")
          .map((tag) => tag.trim())
          .filter(Boolean),
      ),
    );

    const success = await publishToMarketplace(localSkillName, {
      skill_name: marketplaceSkillName.trim(),
      description: description.trim() || undefined,
      tags: normalizedTags,
    });

    if (success) {
      toast.success(
        publishConfirm.isPublished
          ? t("skills.republishSuccess")
          : t("skills.publishSuccess"),
      );
      setPublishConfirm(null);
      return;
    }

    setPublishConfirm({
      ...publishConfirm,
      error: t("skills.publishFailed") || "Publish failed",
    });
  };

  // ZIP upload handlers
  const handleZipClick = () => {
    setZipFile(null);
    setShowZipModal(true);
  };

  const handleZipFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setZipFile(file);
  };

  const handleZipUpload = async () => {
    if (!zipFile) return;

    setZipUploading(true);
    try {
      const success = await uploadSkill(zipFile);
      if (success) {
        setShowZipModal(false);
        setZipFile(null);
      }
    } finally {
      setZipUploading(false);
    }
  };

  // GitHub import handlers
  const handleGithubClick = () => {
    setGithubUrl("");
    setGithubBranch("main");
    setGithubSkills([]);
    setSelectedGithubSkills([]);
    setShowGithubModal(true);
  };

  const handleGithubPreview = async () => {
    if (!githubUrl.trim()) return;

    setGithubLoading(true);
    setGithubSkills([]);
    setSelectedGithubSkills([]);
    try {
      const result = await previewGitHubSkills(githubUrl, githubBranch);
      if (result && result.skills) {
        setGithubSkills(result.skills);
      }
    } finally {
      setGithubLoading(false);
    }
  };

  const handleGithubSkillToggle = (name: string) => {
    setSelectedGithubSkills((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
  };

  const handleGithubInstall = async () => {
    if (selectedGithubSkills.length === 0) return;

    setGithubInstalling(true);
    try {
      const result = await installGitHubSkills(
        githubUrl,
        selectedGithubSkills,
        githubBranch,
      );
      if (result) {
        setShowGithubModal(false);
        setGithubSkills([]);
        setSelectedGithubSkills([]);
      }
    } finally {
      setGithubInstalling(false);
    }
  };

  const handleGithubExport = async () => {
    if (selectedGithubSkills.length === 0) return;

    setGithubExporting(true);
    try {
      const result = await installGitHubSkills(githubUrl, selectedGithubSkills, githubBranch);
      if (!result?.installed?.length) {
        toast.error(t("skills.exportFailed"));
        return;
      }

      const installedSkill = await getSkill(result.installed[0]);
      if (!installedSkill) {
        toast.error(t("skills.exportFailed"));
        return;
      }

      await exportProjectZip(installedSkill.files, installedSkill.name);
      toast.success(t("skills.exportSuccess"));
    } catch {
      toast.error(t("skills.exportFailed"));
    } finally {
      setGithubExporting(false);
    }
  };

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

  const hasActiveFilters = searchQuery.trim().length > 0 || selectedTags.length > 0;

  return (
    <div className="flex h-full flex-col min-h-0">
      {/* Header */}
      <PanelHeader
        title={t("skills.title")}
        subtitle={t("skills.subtitle")}
        icon={
          <FolderOpen
            size={18}
            className="text-stone-600 dark:text-stone-400"
          />
        }
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        searchPlaceholder={t("skills.searchPlaceholder")}
        actions={
          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-end sm:gap-2">
            <button onClick={handleGithubClick} className="btn-secondary justify-center">
              <Github size={16} />
              <span className="hidden sm:inline">GitHub</span>
            </button>
            <button onClick={handleZipClick} className="btn-secondary justify-center">
              <Archive size={16} />
              <span className="hidden sm:inline">ZIP</span>
            </button>
            <button onClick={handleCreate} className="btn-primary justify-center">
              <Plus size={16} />
              <span className="hidden sm:inline">{t("skills.newSkill")}</span>
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

      {availableTags.length > 0 && (
        <div className="border-b border-[var(--theme-border)] bg-[var(--theme-bg)] px-4 py-3 sm:px-6">
          <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg-card)]/85 px-3 py-3 shadow-sm backdrop-blur">
            {availableTags.map((tag) => (
              <button
                key={tag}
                type="button"
                onClick={() => toggleTag(tag)}
                className={`skill-tag-chip ${
                  selectedTags.includes(tag) ? "skill-tag-chip--active" : ""
                }`}
              >
                {tag}
              </button>
            ))}
            {hasActiveFilters && (
              <button
                type="button"
                onClick={clearFilters}
                className="ml-1 text-xs text-[var(--theme-text-secondary)] transition-colors hover:text-[var(--theme-primary)]"
              >
                {t("marketplace.clearFilters")}
              </button>
            )}
          </div>
        </div>
      )}

      {/* Skills List */}
      <div className="flex-1 overflow-y-auto p-2 sm:p-4">
        {isLoading && skills.length === 0 ? (
          <div className="flex h-full items-center justify-center text-stone-500 dark:text-stone-400">
            <LoadingSpinner size="sm" />
            <span className="ml-2">{t("skills.loading")}</span>
          </div>
        ) : filteredSkills.length === 0 ? (
          <div className="skill-empty-state">
            <div className="skill-empty-state__icon">
              <FolderOpen size={28} />
            </div>
            <p className="skill-empty-state__title">
              {hasActiveFilters
                ? t("skills.noMatchingSkills")
                : t("skills.noSkills")}
            </p>
            <p className="skill-empty-state__description">
              {hasActiveFilters
                ? t("skills.subtitle")
                : t("skills.createFirst")}
            </p>
            {!hasActiveFilters && canWrite && (
              <button
                onClick={handleCreate}
                className="btn-primary mt-4"
              >
                <Plus size={16} />
                <span>{t("skills.newSkill")}</span>
              </button>
            )}
            {hasActiveFilters && (
              <button
                type="button"
                onClick={clearFilters}
                className="btn-secondary mt-4"
              >
                {t("marketplace.clearFilters")}
              </button>
            )}
          </div>
        ) : (
          <div className="grid gap-4 grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {paginatedSkills.map((skill) => (
              <SkillCard
                key={skill.name}
                skill={skill}
                onToggle={handleToggle}
                onEdit={handleEdit}
                onDelete={handleDelete}
                onExportZip={handleExportZip}
                isPublished={skill.is_published}
              />
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > pageSize && (
        <div className="border-t border-stone-200 px-3 py-3 dark:border-stone-800 sm:px-4">
          <Pagination
            page={page}
            pageSize={pageSize}
            total={total}
            onChange={setPage}
          />
        </div>
      )}

      {/* Form Modal - Bottom Sheet */}
      {showModal && (
        <>
          {!isFormFullscreen && (
            <div className="fixed inset-0" onClick={handleCancel} />
          )}
          <div className="modal-bottom-sheet sm:modal-centered-wrapper">
            <div className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-[72rem]">
              {!isFormFullscreen && (
                <>
                  <div className="bottom-sheet-handle sm:hidden" />
                  {/* Header */}
                  <div className="skill-modal-header">
                    <div>
                      <h3 className="skill-modal-header__title">
                        {isCreating
                          ? t("skills.createNew")
                          : t("skills.editSkill", { name: editingSkill?.name })}
                      </h3>
                      <p className="skill-modal-header__subtitle">
                        {t("skills.subtitle")}
                      </p>
                    </div>
                    <button onClick={handleCancel} className="btn-icon">
                      <X size={20} />
                    </button>
                  </div>
                </>
              )}
              {/* Content */}
              <div className="flex flex-1 min-h-0 overflow-hidden flex-col bg-[var(--theme-bg)]/30 px-3 py-3 sm:px-5 sm:py-4">
                <SkillForm
                  skill={editingSkill}
                  onSave={handleSave}
                  onCancel={handleCancel}
                  isLoading={isLoading}
                  onFullscreenChange={setIsFormFullscreen}
                />
              </div>
            </div>
          </div>
        </>
      )}

      {/* ZIP Upload Modal - Bottom Sheet */}
      {showZipModal && (
        <>
          <div className="fixed inset-0" onClick={() => setShowZipModal(false)} />
          <div className="modal-bottom-sheet sm:modal-centered-wrapper">
            <div className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-[72rem]">
              <div className="bottom-sheet-handle sm:hidden" />
              {/* Header */}
              <div className="skill-modal-header">
                <div>
                  <h3 className="skill-modal-header__title">
                    {t("skills.uploadZipTitle")}
                  </h3>
                  <p className="skill-modal-header__subtitle">
                    {t("skills.subtitle")}
                  </p>
                </div>
                <button
                  onClick={() => setShowZipModal(false)}
                  className="btn-icon"
                >
                  <X size={20} />
                </button>
              </div>
              {/* Content */}
              <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-6 sm:py-5">
                <div className="skill-modal-section space-y-4">
                  <div className="flex items-start gap-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)]/85 px-4 py-4">
                    <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--theme-primary-light)] text-[var(--theme-primary)]">
                      <Archive size={18} />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-[var(--theme-text)]">
                        {t("skills.selectZipFile")}
                      </p>
                      <p className="mt-1 text-xs leading-5 text-[var(--theme-text-secondary)]">
                        {t("skills.subtitle")}
                      </p>
                    </div>
                  </div>
                  <div>
                    <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
                      {t("skills.selectZipFile")}
                    </label>
                    <input
                      ref={zipInputRef}
                      type="file"
                      accept=".zip"
                      onChange={handleZipFileChange}
                      className="block w-full text-sm text-stone-500
                        file:mr-4 file:rounded-lg file:border-0
                        file:bg-stone-100 file:px-4 file:py-2
                        file:text-sm file:font-medium
                        file:text-stone-700 hover:file:bg-stone-200
                        dark:file:bg-stone-700 dark:file:text-stone-200
                        dark:hover:file:bg-stone-600"
                    />
                    {zipFile && (
                      <p className="mt-1 text-xs text-stone-500 dark:text-stone-400">
                        {zipFile.name} ({(zipFile.size / 1024).toFixed(1)} KB)
                      </p>
                    )}
                  </div>

                  {/* Actions */}
                  <div className="flex justify-end gap-2 border-t border-[var(--theme-border)] pt-4">
                    <button
                      onClick={() => setShowZipModal(false)}
                      className="btn-secondary"
                    >
                      {t("common.cancel")}
                    </button>
                    <button
                      onClick={handleZipUpload}
                      disabled={zipUploading || !zipFile}
                      className="btn-primary disabled:opacity-50"
                    >
                      {zipUploading ? (
                        <>
                          <LoadingSpinner size="sm" />
                          {t("skills.uploading")}
                        </>
                      ) : (
                        <>
                          <Upload size={18} />
                          {t("skills.upload")}
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </>
      )}

      {/* GitHub Import Modal - Bottom Sheet */}
      {showGithubModal && (
        <>
          <div className="fixed inset-0" onClick={() => setShowGithubModal(false)} />
          <div className="modal-bottom-sheet sm:modal-centered-wrapper">
            <div className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-[72rem]">
              <div className="bottom-sheet-handle sm:hidden" />
              {/* Header */}
              <div className="skill-modal-header">
                <div>
                  <h3 className="skill-modal-header__title">
                    {t("skills.importFromGitHub")}
                  </h3>
                  <p className="skill-modal-header__subtitle">
                    {t("skills.subtitle")}
                  </p>
                </div>
                <button
                  onClick={() => setShowGithubModal(false)}
                  className="btn-icon"
                >
                  <X size={20} />
                </button>
              </div>
              {/* Content */}
              <div className="flex-1 overflow-y-auto px-3 py-4 sm:px-6 sm:py-5">
                <div className="skill-modal-section space-y-4">
                  <div className="flex items-start gap-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)]/85 px-4 py-4">
                    <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-[var(--theme-primary-light)] text-[var(--theme-primary)]">
                      <Sparkles size={18} />
                    </div>
                    <div>
                      <p className="text-sm font-medium text-[var(--theme-text)]">
                        {t("skills.importFromGitHub")}
                      </p>
                      <p className="mt-1 text-xs leading-5 text-[var(--theme-text-secondary)]">
                        {t("skills.importFromGitHubTitle")}
                      </p>
                    </div>
                  </div>
                  {/* URL Input */}
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-stone-700 dark:text-stone-300">
                      {t("skills.githubRepoUrl")}
                    </label>
                    <div className="flex gap-2 flex-col sm:flex-row">
                    <input
                      type="text"
                      value={githubUrl}
                      onChange={(e) => setGithubUrl(e.target.value)}
                      placeholder="https://github.com/owner/repo"
                      className="input-field flex-1"
                    />
                    <input
                      type="text"
                      value={githubBranch}
                      onChange={(e) => setGithubBranch(e.target.value)}
                      placeholder="main"
                      className="input-field sm:w-24"
                    />
                    <button
                      onClick={handleGithubPreview}
                      disabled={githubLoading || !githubUrl.trim()}
                      className="btn-secondary"
                    >
                      {githubLoading ? <LoadingSpinner size="sm" /> : t("skills.preview")}
                    </button>
                  </div>
                </div>

                {/* Skills List */}
                {githubSkills.length > 0 && (
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-stone-700 dark:text-stone-300">
                      {t("skills.selectSkillsToInstall")}
                    </label>
                    <div className="space-y-1 max-h-60 overflow-y-auto">
                      {githubSkills.map((skill) => (
                        <div
                          key={skill.name}
                          onClick={() => handleGithubSkillToggle(skill.name)}
                          className={`skill-surface-card flex items-center gap-3 rounded-2xl p-3 cursor-pointer ${
                            selectedGithubSkills.includes(skill.name)
                              ? "border-[color:color-mix(in_srgb,var(--theme-primary)_28%,var(--theme-border))] bg-[color:color-mix(in_srgb,var(--theme-primary-light)_82%,white_18%)]"
                              : ""
                          }`}
                        >
                          <div className={`flex h-5 w-5 items-center justify-center rounded-md border ${
                            selectedGithubSkills.includes(skill.name)
                              ? "border-[var(--theme-primary)] bg-[var(--theme-primary)] text-white dark:text-stone-950"
                              : "border-[var(--theme-border)] text-transparent"
                          }`}>
                            {selectedGithubSkills.includes(skill.name) && (
                              <Check size={14} className="text-white" />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="font-medium text-stone-900 dark:text-stone-100 truncate">
                              {skill.name}
                            </p>
                            <p className="text-sm text-stone-500 dark:text-stone-400 truncate">
                              {skill.description}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Actions */}
                <div className="flex justify-end gap-2 border-t border-[var(--theme-border)] pt-4">
                  <button
                    onClick={() => setShowGithubModal(false)}
                    className="btn-secondary"
                  >
                    {t("common.cancel")}
                  </button>
                  <button
                    onClick={handleGithubExport}
                    disabled={githubExporting || selectedGithubSkills.length === 0}
                    className="btn-secondary disabled:opacity-50"
                  >
                    {githubExporting ? (
                      <>
                        <LoadingSpinner size="sm" />
                        {t("skills.exportZip")}
                      </>
                    ) : (
                      <>
                        <Archive size={18} />
                        {t("skills.exportZip")}
                      </>
                    )}
                  </button>
                  <button
                    onClick={handleGithubInstall}
                    disabled={githubInstalling || selectedGithubSkills.length === 0}
                    className="btn-primary disabled:opacity-50"
                  >
                    {githubInstalling ? (
                      <>
                        <LoadingSpinner size="sm" />
                        {t("skills.installing")}
                      </>
                    ) : (
                      <>
                        <Upload size={18} />
                        {t("skills.installSelected", { count: selectedGithubSkills.length })}
                      </>
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </>
    )}

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={isDeleteConfirmOpen}
        title={t("skills.confirmDelete", {
          name: deleteConfirmData?.name || "",
        })}
        message={t("skills.confirmDeleteMessage", {
          name: deleteConfirmData?.name || "",
        })}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        onConfirm={confirmDelete}
        onCancel={cancelDelete}
        variant="danger"
      />

      {/* Publish Form Dialog */}
      {publishConfirm && (
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm p-0 sm:items-center sm:p-4">
          <div className="w-full max-w-lg rounded-t-[1.75rem] border border-[var(--theme-border)] bg-[var(--theme-bg-card)] shadow-[0_28px_80px_-36px_rgba(15,23,42,0.55)] sm:rounded-[1.75rem]">
              <div className="skill-modal-header">
                <div>
                  <h3 className="skill-modal-header__title">
                    {publishConfirm.isPublished
                      ? t("skills.republishTitle", { name: publishConfirm.localSkillName })
                      : t("skills.publishTitle", { name: publishConfirm.localSkillName })}
                  </h3>
                  <p className="skill-modal-header__subtitle">
                    {publishConfirm.isPublished
                      ? t("skills.republishMessage")
                      : t("skills.publishMessage")}
                  </p>
                </div>
              </div>
            <div className="space-y-4 p-5 sm:p-6">
              <div className="skill-modal-section">
                <p className="text-xs font-medium uppercase tracking-wide text-[var(--theme-text-secondary)]">
                  {t("skills.publishLocalSkill")}
                </p>
                <p className="mt-1 font-mono text-sm text-[var(--theme-text)] break-all">
                  {publishConfirm.localSkillName}
                </p>
              </div>

              <div>
                <label className="mb-2 block text-sm font-medium text-[var(--theme-text)]">
                  {t("skills.publishMarketplaceName")}
                </label>
                <input
                  type="text"
                  value={publishConfirm.marketplaceSkillName}
                  onChange={(e) =>
                    setPublishConfirm({
                      ...publishConfirm,
                      marketplaceSkillName: e.target.value,
                      error: undefined,
                    })
                  }
                  className="w-full rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2.5 text-[var(--theme-text)] focus:border-[var(--theme-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20"
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-[var(--theme-text)]">
                  {t("skills.form.description")}
                </label>
                <textarea
                  value={publishConfirm.description}
                  onChange={(e) =>
                    setPublishConfirm({
                      ...publishConfirm,
                      description: e.target.value,
                      error: undefined,
                    })
                  }
                  rows={4}
                  className="w-full rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2.5 text-[var(--theme-text)] focus:border-[var(--theme-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20"
                  placeholder={t("skills.form.descriptionPlaceholder")}
                />
              </div>
              <div>
                <label className="mb-2 block text-sm font-medium text-[var(--theme-text)]">
                  {t("adminMarketplace.tags")}
                </label>
                <p className="mb-2 text-xs leading-5 text-[var(--theme-text-secondary)]/80">
                  {t("adminMarketplace.tagsHint")}
                </p>
                <input
                  type="text"
                  value={publishConfirm.tagsInput}
                  onChange={(e) =>
                    setPublishConfirm({
                      ...publishConfirm,
                      tagsInput: e.target.value,
                      error: undefined,
                    })
                  }
                  className="w-full rounded-xl border border-[var(--theme-border)] bg-[var(--theme-bg)] px-3 py-2.5 text-[var(--theme-text)] focus:border-[var(--theme-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--theme-primary)]/20"
                  placeholder={t("adminMarketplace.tagsPlaceholder")}
                />
                <div className="mt-3 flex flex-wrap gap-2">
                  {Array.from(
                    new Set(
                      publishConfirm.tagsInput
                        .split(",")
                        .map((tag) => tag.trim())
                        .filter(Boolean),
                    ),
                  ).map((tag) => (
                    <span key={tag} className="skill-tag-chip skill-tag-chip--active">
                      {tag}
                    </span>
                  ))}
                  {publishConfirm.tagsInput.trim().length === 0 && (
                    <span className="text-xs text-[var(--theme-text-secondary)]/80">
                      {t("adminMarketplace.tagsPlaceholder")}
                    </span>
                  )}
                </div>
              </div>
              {publishConfirm.error && (
                <div className="rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-600 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-400">
                  {publishConfirm.error}
                </div>
              )}
            </div>
            <div className="flex flex-col-reverse gap-2 border-t border-[var(--theme-border)] px-5 py-4 sm:flex-row sm:justify-end sm:px-6">
              <button
                onClick={() => setPublishConfirm(null)}
                className="btn-secondary"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={confirmPublish}
                className="btn-primary"
              >
                {publishConfirm.isPublished ? t("skills.republish") : t("skills.publish")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
