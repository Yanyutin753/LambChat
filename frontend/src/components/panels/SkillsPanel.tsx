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
import { Plus, X, FolderOpen, PackageX, Archive, Upload, Github, Check } from "lucide-react";
import { useTranslation } from "react-i18next";
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
    clearError,
  } = useSkills();
  const { hasAnyPermission } = useAuth();

  const [searchQuery, setSearchQuery] = useState("");
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

  // Update total when skills change
  useEffect(() => {
    setTotal(skills.length);
  }, [skills]);

  // Reset to page 1 when search changes
  useEffect(() => {
    setPage(1);
  }, [searchQuery]);

  // Delete confirmation dialog state
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [deleteConfirmData, setDeleteConfirmData] = useState<{
    name: string;
  } | null>(null);

  const canRead = hasAnyPermission([Permission.SKILL_READ]);
  const canWrite = hasAnyPermission([Permission.SKILL_WRITE]);

  const filteredSkills = skills.filter(
    (skill) =>
      skill.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      skill.description.toLowerCase().includes(searchQuery.toLowerCase()),
  );

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
    } catch (err) {
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

  const handleDelete = async (name: string) => {
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
      const result = await installGitHubSkills(githubUrl, selectedGithubSkills, githubBranch);
      if (result) {
        setShowGithubModal(false);
        setGithubSkills([]);
        setSelectedGithubSkills([]);
      }
    } finally {
      setGithubInstalling(false);
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
          canWrite && (
            <>
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
            </>
          )
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
      <div className="flex-1 overflow-y-auto p-2 sm:p-4">
        {isLoading && skills.length === 0 ? (
          <div className="flex h-full items-center justify-center text-stone-500 dark:text-stone-400">
            <LoadingSpinner size="sm" />
            <span className="ml-2">{t("skills.loading")}</span>
          </div>
        ) : filteredSkills.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-stone-500 dark:text-stone-400 px-4">
            <FolderOpen
              size={40}
              className="mb-3 sm:mb-2 text-stone-300 dark:text-stone-600"
            />
            <p className="text-sm sm:text-base">
              {searchQuery
                ? t("skills.noMatchingSkills")
                : t("skills.noSkills")}
            </p>
            {!searchQuery && canWrite && (
              <button
                onClick={handleCreate}
                className="mt-3 sm:mt-2 text-sm text-stone-600 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100"
              >
                {t("skills.createFirst")}
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-1.5 sm:space-y-2">
            {paginatedSkills.map((skill) => (
              <SkillCard
                key={skill.name}
                skill={skill}
                onToggle={handleToggle}
                onEdit={handleEdit}
                onDelete={handleDelete}
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
            <div className="modal-bottom-sheet-content sm:modal-centered-content">
              {!isFormFullscreen && (
                <>
                  <div className="bottom-sheet-handle sm:hidden" />
                  {/* Header */}
                  <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4 dark:border-stone-800 shrink-0">
                    <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 font-serif">
                      {isCreating
                        ? t("skills.createNew")
                        : t("skills.editSkill", { name: editingSkill?.name })}
                    </h3>
                    <button onClick={handleCancel} className="btn-icon">
                      <X size={20} />
                    </button>
                  </div>
                </>
              )}
              {/* Content */}
              <div className="flex-1 min-h-0 overflow-hidden flex flex-col px-2 sm:px-4 py-2 sm:py-3">
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
            <div className="modal-bottom-sheet-content sm:modal-centered-content">
              <div className="bottom-sheet-handle sm:hidden" />
              {/* Header */}
              <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4 dark:border-stone-800">
                <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 font-serif">
                  {t("skills.uploadZipTitle")}
                </h3>
                <button
                  onClick={() => setShowZipModal(false)}
                  className="btn-icon"
                >
                  <X size={20} />
                </button>
              </div>
              {/* Content */}
              <div className="flex-1 overflow-y-auto px-2 sm:px-6 py-4 space-y-2">
                <div className="space-y-4">
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
                  <div className="flex justify-end gap-2">
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
            <div className="modal-bottom-sheet-content sm:modal-centered-content">
              <div className="bottom-sheet-handle sm:hidden" />
              {/* Header */}
              <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4 dark:border-stone-800">
                <h3 className="text-xl font-semibold text-stone-900 dark:text-stone-100 font-serif">
                  {t("skills.importFromGitHub")}
                </h3>
                <button
                  onClick={() => setShowGithubModal(false)}
                  className="btn-icon"
                >
                  <X size={20} />
                </button>
              </div>
              {/* Content */}
              <div className="flex-1 overflow-y-auto px-2 sm:px-6 py-4 space-y-4">
                {/* URL Input */}
                <div className="space-y-2">
                  <label className="block text-sm font-medium text-stone-700 dark:text-stone-300">
                    {t("skills.githubRepoUrl")}
                  </label>
                  <div className="flex gap-2">
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
                      className="input-field w-24"
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
                          className={`flex items-center gap-3 p-3 rounded-lg cursor-pointer transition-colors ${
                            selectedGithubSkills.includes(skill.name)
                              ? "bg-blue-50 dark:bg-blue-900/30"
                              : "bg-stone-50 dark:bg-stone-800/50 hover:bg-stone-100 dark:hover:bg-stone-800"
                          }`}
                        >
                          <div className={`w-5 h-5 rounded border flex items-center justify-center ${
                            selectedGithubSkills.includes(skill.name)
                              ? "bg-blue-500 border-blue-500"
                              : "border-stone-300 dark:border-stone-600"
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
                <div className="flex justify-end gap-2 pt-2">
                  <button
                    onClick={() => setShowGithubModal(false)}
                    className="btn-secondary"
                  >
                    {t("common.cancel")}
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
    </div>
  );
}
