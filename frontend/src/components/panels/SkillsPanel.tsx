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
import {
  Plus,
  X,
  FolderOpen,
  PackageX,
  Archive,
  Upload,
  Github,
  Check,
  Sparkles,
  Tag,
  ChevronDown,
  Trash2,
  ToggleLeft,
  ToggleRight,
} from "lucide-react";
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
import { sanitizeSkillName } from "../../utils/skillFilters";
import type { SkillResponse, SkillCreate } from "../../types";
import { collectSkillTags, skillMatchesQuery } from "../../utils/skillFilters";

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
    batchDeleteSkills,
    batchToggleSkills,
    toggleSkill,
    uploadSkill,
    previewZipSkills,
    previewGitHubSkills,
    installGitHubSkills,
    publishToMarketplace,
    clearError,
  } = useSkills();
  const { hasAnyPermission } = useAuth();

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [isFilterOpen, setIsFilterOpen] = useState(false);
  const [editingSkill, setEditingSkill] = useState<SkillResponse | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [isFormFullscreen, setIsFormFullscreen] = useState(false);

  // Batch selection state
  const [selectedNames, setSelectedNames] = useState<Set<string>>(new Set());
  const [batchLoading, setBatchLoading] = useState(false);

  // Pagination state
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  // ZIP upload state
  const [showZipModal, setShowZipModal] = useState(false);
  const [zipFile, setZipFile] = useState<File | null>(null);
  const [zipUploading, setZipUploading] = useState(false);
  const [zipPreviewing, setZipPreviewing] = useState(false);
  const [zipSkills, setZipSkills] = useState<
    Array<{
      name: string;
      description: string;
      file_count: number;
      files: string[];
      already_exists: boolean;
    }>
  >([]);
  const [selectedZipSkills, setSelectedZipSkills] = useState<string[]>([]);
  const zipInputRef = useRef<HTMLInputElement>(null);

  // GitHub import state
  const [showGithubModal, setShowGithubModal] = useState(false);
  const [githubUrl, setGithubUrl] = useState("");
  const [githubBranch, setGithubBranch] = useState("main");
  const [githubSkills, setGithubSkills] = useState<GitHubSkill[]>([]);
  const [selectedGithubSkills, setSelectedGithubSkills] = useState<string[]>(
    [],
  );
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

  // Batch selection handlers
  const selectionMode = selectedNames.size > 0;

  const handleSelectSkill = (name: string) => {
    setSelectedNames((prev) => {
      const next = new Set(prev);
      if (next.has(name)) {
        next.delete(name);
      } else {
        next.add(name);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedNames.size === filteredSkills.length) {
      setSelectedNames(new Set());
    } else {
      setSelectedNames(new Set(filteredSkills.map((s) => s.name)));
    }
  };

  const clearSelection = () => setSelectedNames(new Set());

  const handleBatchDelete = async () => {
    if (selectedNames.size === 0) return;
    setBatchLoading(true);
    try {
      await batchDeleteSkills(Array.from(selectedNames));
      clearSelection();
      toast.success(
        t("skills.batchDeleteSuccess", { count: selectedNames.size }),
      );
    } catch {
      toast.error(t("skills.batchDeleteFailed"));
    } finally {
      setBatchLoading(false);
    }
  };

  const handleBatchToggle = async (enabled: boolean) => {
    if (selectedNames.size === 0) return;
    setBatchLoading(true);
    try {
      await batchToggleSkills(Array.from(selectedNames), enabled);
      clearSelection();
      toast.success(
        enabled
          ? t("skills.batchEnableSuccess", { count: selectedNames.size })
          : t("skills.batchDisableSuccess", { count: selectedNames.size }),
      );
    } catch {
      toast.error(t("skills.batchToggleFailed"));
    } finally {
      setBatchLoading(false);
    }
  };

  const confirmPublish = async () => {
    if (!publishConfirm) return;
    const { localSkillName, marketplaceSkillName, description } =
      publishConfirm;

    if (!marketplaceSkillName.trim()) {
      setPublishConfirm({
        ...publishConfirm,
        error: t("skills.form.validation.nameRequired"),
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
      skill_name: sanitizeSkillName(marketplaceSkillName.trim()),
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
    setZipSkills([]);
    setSelectedZipSkills([]);
    setShowZipModal(true);
  };

  const handleZipFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] || null;
    setZipFile(file);
    setZipSkills([]);
    setSelectedZipSkills([]);
  };

  const handleZipPreview = async () => {
    if (!zipFile) return;

    setZipPreviewing(true);
    setZipSkills([]);
    setSelectedZipSkills([]);
    try {
      const result = await previewZipSkills(zipFile);
      if (result && result.skills) {
        setZipSkills(result.skills);
        // 默认选中未安装的
        setSelectedZipSkills(
          result.skills.filter((s) => !s.already_exists).map((s) => s.name),
        );
      }
    } finally {
      setZipPreviewing(false);
    }
  };

  const handleZipSkillToggle = (name: string) => {
    setSelectedZipSkills((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
  };

  const handleZipUpload = async () => {
    if (!zipFile || selectedZipSkills.length === 0) return;

    setZipUploading(true);
    try {
      const result = await uploadSkill(zipFile, selectedZipSkills);
      if (result && result.created.length > 0) {
        setShowZipModal(false);
        setZipFile(null);
        setZipSkills([]);
        setSelectedZipSkills([]);
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
      const result = await installGitHubSkills(
        githubUrl,
        selectedGithubSkills,
        githubBranch,
      );
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

  const hasActiveFilters =
    searchQuery.trim().length > 0 || selectedTags.length > 0;

  return (
    <div className="skill-theme-shell flex h-full min-h-0 flex-col">
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
        searchAccessory={
          availableTags.length > 0 ? (
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
                    {availableTags.map((tag) => (
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
            {filteredSkills.length > 0 && (
              <button onClick={handleSelectAll} className="btn-secondary">
                <Check size={16} />
                <span className="hidden sm:inline">
                  {selectedNames.size === filteredSkills.length &&
                  filteredSkills.length > 0
                    ? t("common.deselectAll")
                    : t("common.selectAll")}
                </span>
              </button>
            )}
            <button onClick={handleGithubClick} className="btn-secondary">
              <Github size={16} />
              <span className="hidden sm:inline">GitHub</span>
            </button>
            <button onClick={handleZipClick} className="btn-secondary">
              <Archive size={16} />
              <span className="hidden sm:inline">ZIP</span>
            </button>
            <button onClick={handleCreate} className="btn-primary">
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

      {/* Skills List */}
      <div className="skill-content-area flex-1 overflow-y-auto p-2 sm:p-4">
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
              <button onClick={handleCreate} className="btn-primary mt-4">
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
          <div className="skill-grid grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {paginatedSkills.map((skill) => (
              <SkillCard
                key={skill.name}
                skill={skill}
                onToggle={handleToggle}
                onEdit={handleEdit}
                onDelete={handleDelete}
                onExportZip={handleExportZip}
                onPublish={(s) => {
                  setPublishConfirm({
                    isOpen: true,
                    localSkillName: s.name,
                    marketplaceSkillName:
                      s.published_marketplace_name || s.name,
                    description: s.description || "",
                    tagsInput: s.tags?.join(", ") || "",
                    isPublished: s.is_published,
                  });
                }}
                isPublished={skill.is_published}
                selected={selectedNames.has(skill.name)}
                onSelect={handleSelectSkill}
                selectionMode={true}
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
              <div className="skill-modal-body flex min-h-0 flex-1 overflow-hidden flex-col bg-[var(--theme-bg)]/30 px-3 py-3 sm:px-5 sm:py-4">
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
          <div
            className="fixed inset-0"
            onClick={() => setShowZipModal(false)}
          />
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
              <div className="skill-modal-body flex-1 overflow-y-auto px-3 py-4 sm:px-6 sm:py-5">
                <div className="skill-modal-section space-y-4">
                  <div className="skill-callout flex items-start gap-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)]/85 px-4 py-4">
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

                  {/* Preview button */}
                  {zipFile && zipSkills.length === 0 && (
                    <button
                      onClick={handleZipPreview}
                      disabled={zipPreviewing}
                      className="btn-secondary w-full"
                    >
                      {zipPreviewing ? (
                        <>
                          <LoadingSpinner size="sm" />
                          {t("skills.preview")}
                        </>
                      ) : (
                        t("skills.preview")
                      )}
                    </button>
                  )}

                  {/* Skills preview list */}
                  {zipSkills.length > 0 && (
                    <div className="space-y-2">
                      <div className="flex items-center justify-between">
                        <label className="block text-sm font-medium text-stone-700 dark:text-stone-300">
                          {t("skills.selectSkillsToInstall")}
                        </label>
                        <button
                          onClick={() => {
                            const allNew = zipSkills
                              .filter((s) => !s.already_exists)
                              .map((s) => s.name);
                            setSelectedZipSkills(
                              selectedZipSkills.length === allNew.length
                                ? []
                                : allNew,
                            );
                          }}
                          className="text-xs text-[var(--theme-primary)] hover:underline"
                        >
                          {selectedZipSkills.length ===
                          zipSkills.filter((s) => !s.already_exists).length
                            ? t("common.deselectAll")
                            : t("common.selectAll")}
                        </button>
                      </div>
                      <div className="space-y-1 max-h-72 overflow-y-auto">
                        {zipSkills.map((skill) => (
                          <div
                            key={skill.name}
                            onClick={() =>
                              !skill.already_exists &&
                              handleZipSkillToggle(skill.name)
                            }
                            className={`skill-surface-card skill-select-card flex cursor-pointer items-center gap-3 rounded-2xl p-3 ${
                              skill.already_exists
                                ? "opacity-50 cursor-not-allowed"
                                : selectedZipSkills.includes(skill.name)
                                  ? "border-[color:color-mix(in_srgb,var(--theme-primary)_28%,var(--theme-border))] bg-[color:color-mix(in_srgb,var(--theme-primary-light)_82%,white_18%)]"
                                  : ""
                            }`}
                          >
                            <div
                              className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border ${
                                selectedZipSkills.includes(skill.name)
                                  ? "border-[var(--theme-primary)] bg-[var(--theme-primary)] text-white dark:text-stone-950"
                                  : "border-[var(--theme-border)] text-transparent"
                              }`}
                            >
                              {selectedZipSkills.includes(skill.name) && (
                                <Check size={14} className="text-white" />
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="font-medium text-stone-900 dark:text-stone-100 truncate">
                                  {skill.name}
                                </p>
                                {skill.already_exists && (
                                  <span className="shrink-0 rounded-full bg-stone-200 px-2 py-0.5 text-[10px] font-medium text-stone-500 dark:bg-stone-700 dark:text-stone-400">
                                    {t("skills.installed")}
                                  </span>
                                )}
                              </div>
                              <p className="text-sm text-stone-500 dark:text-stone-400 truncate">
                                {skill.description ||
                                  `${skill.file_count} files`}
                              </p>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex justify-end gap-2 border-t border-[color-mix(in_srgb,var(--theme-border)_40%,transparent)] pt-4">
                    <button
                      onClick={() => setShowZipModal(false)}
                      className="btn-secondary"
                    >
                      {t("common.cancel")}
                    </button>
                    {zipSkills.length > 0 && (
                      <button
                        onClick={handleZipUpload}
                        disabled={
                          zipUploading || selectedZipSkills.length === 0
                        }
                        className="btn-primary disabled:opacity-50"
                      >
                        {zipUploading ? (
                          <>
                            <LoadingSpinner size="sm" />
                            {t("skills.installing")}
                          </>
                        ) : (
                          <>
                            <Upload size={18} />
                            {t("skills.install")} ({selectedZipSkills.length})
                          </>
                        )}
                      </button>
                    )}
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
          <div
            className="fixed inset-0"
            onClick={() => setShowGithubModal(false)}
          />
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
              <div className="skill-modal-body flex-1 overflow-y-auto px-3 py-4 sm:px-6 sm:py-5">
                <div className="skill-modal-section space-y-4">
                  <div className="skill-callout flex items-start gap-3 rounded-2xl border border-[var(--theme-border)] bg-[var(--theme-bg)]/85 px-4 py-4">
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
                    <div className="skill-github-import flex flex-col gap-2 sm:flex-row">
                      <div className="skill-github-import__field skill-github-import__field--repo">
                        <input
                          type="text"
                          value={githubUrl}
                          onChange={(e) => setGithubUrl(e.target.value)}
                          placeholder="https://github.com/owner/repo"
                          className="input-field skill-github-import__input"
                        />
                      </div>
                      <div className="skill-github-import__field skill-github-import__field--branch">
                        <input
                          type="text"
                          value={githubBranch}
                          onChange={(e) => setGithubBranch(e.target.value)}
                          placeholder="main"
                          className="input-field skill-github-import__input"
                        />
                      </div>
                      <button
                        onClick={handleGithubPreview}
                        disabled={githubLoading || !githubUrl.trim()}
                        className="btn-secondary skill-github-import__button"
                      >
                        {githubLoading ? (
                          <LoadingSpinner size="sm" />
                        ) : (
                          t("skills.preview")
                        )}
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
                            className={`skill-surface-card skill-select-card flex cursor-pointer items-center gap-3 rounded-2xl p-3 ${
                              selectedGithubSkills.includes(skill.name)
                                ? "border-[color:color-mix(in_srgb,var(--theme-primary)_28%,var(--theme-border))] bg-[color:color-mix(in_srgb,var(--theme-primary-light)_82%,white_18%)]"
                                : ""
                            }`}
                          >
                            <div
                              className={`flex h-5 w-5 items-center justify-center rounded-md border ${
                                selectedGithubSkills.includes(skill.name)
                                  ? "border-[var(--theme-primary)] bg-[var(--theme-primary)] text-white dark:text-stone-950"
                                  : "border-[var(--theme-border)] text-transparent"
                              }`}
                            >
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
                  <div className="flex justify-end gap-2 border-t border-[color-mix(in_srgb,var(--theme-border)_40%,transparent)] pt-4">
                    <button
                      onClick={() => setShowGithubModal(false)}
                      className="btn-secondary"
                    >
                      {t("common.cancel")}
                    </button>
                    <button
                      onClick={handleGithubExport}
                      disabled={
                        githubExporting || selectedGithubSkills.length === 0
                      }
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
                      disabled={
                        githubInstalling || selectedGithubSkills.length === 0
                      }
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
                          {t("skills.installSelected", {
                            count: selectedGithubSkills.length,
                          })}
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

      {/* Batch Action Bar */}
      {selectionMode && (
        <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-stone-200 bg-white/95 px-4 py-3 shadow-lg backdrop-blur-sm dark:border-stone-800 dark:bg-stone-900/95 sm:left-auto sm:right-auto sm:mx-auto sm:max-w-3xl sm:rounded-t-2xl">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm text-[var(--theme-text)]">
              <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-[var(--theme-primary)] px-1.5 text-[11px] font-bold text-white">
                {selectedNames.size}
              </span>
              <span className="text-[var(--theme-text-secondary)]">
                {t("skills.batchSelected")}
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleBatchToggle(false)}
                disabled={batchLoading}
                className="btn-secondary text-xs"
              >
                <ToggleLeft size={14} />
                <span className="hidden sm:inline">
                  {t("skills.card.disable")}
                </span>
              </button>
              <button
                onClick={() => handleBatchToggle(true)}
                disabled={batchLoading}
                className="btn-secondary text-xs"
              >
                <ToggleRight size={14} />
                <span className="hidden sm:inline">
                  {t("skills.card.enable")}
                </span>
              </button>
              <button
                onClick={handleBatchDelete}
                disabled={batchLoading}
                className="inline-flex items-center gap-1.5 rounded-xl bg-red-50 px-3 py-2 text-xs font-medium text-red-600 transition-colors hover:bg-red-100 dark:bg-red-900/30 dark:text-red-400 dark:hover:bg-red-900/50 disabled:opacity-50"
              >
                {batchLoading ? (
                  <LoadingSpinner size="sm" />
                ) : (
                  <Trash2 size={14} />
                )}
                <span className="hidden sm:inline">{t("common.delete")}</span>
              </button>
              <button
                onClick={clearSelection}
                className="btn-secondary text-xs"
              >
                <X size={14} />
                <span className="hidden sm:inline">{t("common.cancel")}</span>
              </button>
            </div>
          </div>
        </div>
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
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm p-0 sm:items-center sm:p-4 animate-fade-in">
          <div className="skill-theme-shell w-full max-w-lg rounded-t-[1.75rem] border border-[var(--skill-border)] bg-[var(--skill-surface)] shadow-[0_28px_80px_-36px_rgba(15,23,42,0.55)] sm:rounded-[1.75rem] sm:animate-scale-in max-sm:animate-slide-up-sheet">
            <div className="skill-modal-header">
              <div className="flex items-center gap-3">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-[var(--skill-border)] bg-[var(--skill-accent-soft)] text-[var(--skill-accent)]">
                  <Sparkles className="h-5 w-5" />
                </div>
                <div>
                  <h3 className="skill-modal-header__title">
                    {publishConfirm.isPublished
                      ? t("skills.republishTitle", {
                          name: publishConfirm.localSkillName,
                        })
                      : t("skills.publishTitle", {
                          name: publishConfirm.localSkillName,
                        })}
                  </h3>
                  <p className="skill-modal-header__subtitle">
                    {publishConfirm.isPublished
                      ? t("skills.republishMessage")
                      : t("skills.publishMessage")}
                  </p>
                </div>
              </div>
            </div>
            <div className="space-y-5 p-5 sm:p-6">
              <div className="skill-modal-section">
                <div className="flex items-center gap-2">
                  <PackageX className="h-3.5 w-3.5 text-[var(--theme-text-secondary)]" />
                  <p className="text-xs font-medium uppercase tracking-wide text-[var(--theme-text-secondary)]">
                    {t("skills.publishLocalSkill")}
                  </p>
                </div>
                <p className="mt-1.5 font-mono text-sm text-[var(--theme-text)] break-all">
                  {publishConfirm.localSkillName}
                </p>
              </div>

              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-[var(--theme-text)]">
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
                  className="w-full rounded-xl border border-[var(--skill-border)] bg-[var(--theme-bg)] px-3.5 py-2.5 text-sm text-[var(--theme-text)] placeholder:text-[var(--theme-text-secondary)]/60 focus:border-[var(--skill-border-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--skill-accent)]/14 transition-[border-color,box-shadow] duration-180"
                />
              </div>
              <div className="space-y-1.5">
                <label className="block text-sm font-medium text-[var(--theme-text)]">
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
                  className="w-full rounded-xl border border-[var(--skill-border)] bg-[var(--theme-bg)] px-3.5 py-2.5 text-sm text-[var(--theme-text)] placeholder:text-[var(--theme-text-secondary)]/60 focus:border-[var(--skill-border-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--skill-accent)]/14 transition-[border-color,box-shadow] duration-180 resize-none"
                  placeholder={t("skills.form.descriptionPlaceholder")}
                />
              </div>
              <div className="space-y-1.5">
                <label className="flex items-center gap-1.5 text-sm font-medium text-[var(--theme-text)]">
                  <Tag className="h-3.5 w-3.5 text-[var(--theme-text-secondary)]" />
                  {t("adminMarketplace.tags")}
                </label>
                <p className="text-xs leading-5 text-[var(--theme-text-secondary)]/80">
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
                  className="w-full rounded-xl border border-[var(--skill-border)] bg-[var(--theme-bg)] px-3.5 py-2.5 text-sm text-[var(--theme-text)] placeholder:text-[var(--theme-text-secondary)]/60 focus:border-[var(--skill-border-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--skill-accent)]/14 transition-[border-color,box-shadow] duration-180"
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
                    <span
                      key={tag}
                      className="skill-tag-chip skill-tag-chip--active"
                    >
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
                <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-2.5 text-sm text-red-600 dark:border-red-900/40 dark:bg-red-900/20 dark:text-red-400">
                  {publishConfirm.error}
                </div>
              )}
            </div>
            <div className="flex flex-col-reverse gap-2 border-t border-[color-mix(in_srgb,var(--theme-border)_40%,transparent)] px-5 py-4 sm:flex-row sm:justify-end sm:px-6">
              <button
                onClick={() => setPublishConfirm(null)}
                className="btn-secondary"
              >
                {t("common.cancel")}
              </button>
              <button onClick={confirmPublish} className="btn-primary">
                {publishConfirm.isPublished
                  ? t("skills.republish")
                  : t("skills.publish")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
