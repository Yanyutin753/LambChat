import { useState } from "react";
import {
  Plus,
  X,
  Search,
  Download,
  Upload,
  FolderOpen,
  Loader2,
  Check,
  Github,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { SkillCard } from "../skill/SkillCard";
import { SkillForm } from "../skill/SkillForm";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { useSkills } from "../../hooks/useSkills";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type {
  SkillResponse,
  SkillCreate,
  GitHubSkillPreview,
} from "../../types";

export function SkillsPanel() {
  const { t } = useTranslation();
  const {
    skills,
    isLoading,
    error,
    createSkill,
    updateSkill,
    deleteSkill,
    toggleSkill,
    importSkills,
    exportSkills,
    previewGitHubSkills,
    installGitHubSkills,
    promoteSkill,
    demoteSkill,
    clearError,
  } = useSkills();
  const { hasAnyPermission, user } = useAuth();

  const [searchQuery, setSearchQuery] = useState("");
  const [editingSkill, setEditingSkill] = useState<SkillResponse | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importJson, setImportJson] = useState("");
  const [importOverwrite, setImportOverwrite] = useState(false);
  const [importResult, setImportResult] = useState<{
    success: boolean;
    message: string;
  } | null>(null);
  const [showGithubModal, setShowGithubModal] = useState(false);
  const [githubUrl, setGithubUrl] = useState("");
  const [githubBranch, setGithubBranch] = useState("main");
  const [githubSkills, setGithubSkills] = useState<GitHubSkillPreview[]>([]);
  const [selectedGithubSkills, setSelectedGithubSkills] = useState<string[]>(
    [],
  );
  const [githubLoading, setGithubLoading] = useState(false);
  const [githubInstallAsSystem, setGithubInstallAsSystem] = useState(false);

  // Delete confirmation dialog state
  const [isDeleteConfirmOpen, setIsDeleteConfirmOpen] = useState(false);
  const [deleteConfirmData, setDeleteConfirmData] = useState<{
    name: string;
    isSystem: boolean;
  } | null>(null);

  const canRead = hasAnyPermission([Permission.SKILL_READ]);
  const canWrite = hasAnyPermission([Permission.SKILL_WRITE]);
  const canAdmin = hasAnyPermission([Permission.SKILL_ADMIN]);

  const filteredSkills = skills.filter(
    (skill) =>
      skill.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      skill.description.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  const handleCreate = () => {
    setIsCreating(true);
    setEditingSkill(null);
    setShowModal(true);
  };

  const handleEdit = (skill: SkillResponse) => {
    setEditingSkill(skill);
    setIsCreating(false);
    setShowModal(true);
  };

  const handleSave = async (
    data: SkillCreate,
    isSystem: boolean,
  ): Promise<boolean> => {
    let success = false;

    try {
      if (isCreating) {
        const result = await createSkill(data, isSystem);
        success = result !== null;
        if (success) {
          toast.success(t("skills.createSuccess"));
        } else {
          toast.error(t("skills.createFailed"));
        }
      } else if (editingSkill) {
        // Check if skill type is changing (use isSystem param from SkillForm)
        const typeChanging = isSystem !== editingSkill.is_system;

        if (typeChanging && canAdmin) {
          // Handle type change
          if (isSystem) {
            const result = await promoteSkill(
              editingSkill.name,
              user?.id || "",
            );
            success = result !== null;
            if (success) {
              toast.success(t("skills.promoteSuccess"));
            } else {
              toast.error(t("skills.promoteFailed"));
            }
          } else {
            const result = await demoteSkill(editingSkill.name, user?.id || "");
            success = result !== null;
            if (success) {
              toast.success(t("skills.demoteSuccess"));
            } else {
              toast.error(t("skills.demoteFailed"));
            }
          }
        } else {
          // Normal update - include is_system if admin (for switching type)
          const result = await updateSkill(
            editingSkill.name,
            {
              description: data.description,
              content: data.content,
              enabled: data.enabled,
              is_system: canAdmin ? isSystem : undefined,
              files: data.files,
            },
            editingSkill.is_system,
          );
          success = result !== null;
          if (success) {
            toast.success(t("skills.updateSuccess"));
          } else {
            toast.error(t("skills.updateFailed"));
          }
        }
      }

      if (success) {
        setShowModal(false);
        setEditingSkill(null);
        setIsCreating(false);
      }
    } catch (error) {
      toast.error((error as Error).message || t("skills.operationFailed"));
      success = false;
    }

    return success;
  };

  const handleCancel = () => {
    setShowModal(false);
    setEditingSkill(null);
    setIsCreating(false);
  };

  const handleDelete = async (name: string, isSystem: boolean = false) => {
    setDeleteConfirmData({ name, isSystem });
    setIsDeleteConfirmOpen(true);
  };

  const confirmDelete = async () => {
    if (!deleteConfirmData) return;
    try {
      await deleteSkill(deleteConfirmData.name, deleteConfirmData.isSystem);
      toast.success(t("skills.deleteSuccess"));
    } catch (error) {
      toast.error((error as Error).message || t("skills.deleteFailed"));
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

  const handleExport = async () => {
    try {
      const result = await exportSkills();
      if (result && result.skills) {
        const blob = new Blob(
          [JSON.stringify({ skills: result.skills }, null, 2)],
          { type: "application/json" },
        );
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = "skills.json";
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        toast.success(t("skills.exportSuccess"));
      } else {
        toast.error(t("skills.exportFailed"));
      }
    } catch (error) {
      toast.error((error as Error).message || t("skills.exportFailed"));
    }
  };

  const handleImportClick = () => {
    setImportJson("");
    setImportOverwrite(false);
    setImportResult(null);
    setShowImportModal(true);
  };

  const handleImport = async () => {
    setImportResult(null);

    try {
      const parsed = JSON.parse(importJson);
      if (!parsed.skills || typeof parsed.skills !== "object") {
        setImportResult({
          success: false,
          message: "Invalid format: missing skills object",
        });
        toast.error(t("skills.invalidFormat"));
        return;
      }

      const result = await importSkills({
        skills: parsed.skills,
        overwrite: importOverwrite,
      });

      if (result) {
        const message = `${result.message}${
          result.errors.length > 0
            ? `\nErrors: ${result.errors.join(", ")}`
            : ""
        }`;
        setImportResult({ success: true, message });

        if (result.errors.length === 0) {
          toast.success(t("skills.importSuccess"));
          setTimeout(() => {
            setShowImportModal(false);
            setImportJson("");
            setImportResult(null);
          }, 1500);
        }
      }
    } catch (error) {
      setImportResult({ success: false, message: "Invalid JSON format" });
      toast.error(t("skills.invalidJson"));
    }
  };

  const handleGithubClick = () => {
    setGithubUrl("");
    setGithubBranch("main");
    setGithubSkills([]);
    setSelectedGithubSkills([]);
    setGithubInstallAsSystem(false);
    setShowGithubModal(true);
  };

  const handleGithubPreview = async () => {
    if (!githubUrl.trim()) return;

    setGithubLoading(true);
    setGithubSkills([]);

    try {
      const result = await previewGitHubSkills({
        repo_url: githubUrl,
        branch: githubBranch,
      });

      if (result) {
        setGithubSkills(result.skills);
        setSelectedGithubSkills(result.skills.map((s) => s.name));
      }
    } catch (err) {
      console.error("Failed to preview GitHub skills:", err);
    } finally {
      setGithubLoading(false);
    }
  };

  const handleGithubInstall = async () => {
    if (selectedGithubSkills.length === 0) return;

    setGithubLoading(true);

    try {
      await installGitHubSkills(
        {
          repo_url: githubUrl,
          branch: githubBranch,
          skill_names: selectedGithubSkills,
          as_system: githubInstallAsSystem,
        },
        githubInstallAsSystem,
      );

      setShowGithubModal(false);
      setGithubUrl("");
      setGithubBranch("main");
      setGithubSkills([]);
      setSelectedGithubSkills([]);
    } catch (err) {
      console.error("Failed to install GitHub skills:", err);
    } finally {
      setGithubLoading(false);
    }
  };

  const toggleGithubSkill = (name: string) => {
    setSelectedGithubSkills((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    );
  };

  if (!canRead) {
    return (
      <div className="flex h-full items-center justify-center text-stone-500 dark:text-stone-400">
        {t("skills.noPermission")}
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col min-h-0">
      {/* Header */}
      <div className="panel-header">
        <div className="flex flex-col gap-2 sm:gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <h2 className="text-lg font-semibold text-stone-900 dark:text-stone-100 whitespace-nowrap">
              {t("skills.title")}
            </h2>
            <p className="mt-0.5 text-sm text-stone-500 dark:text-stone-400 whitespace-nowrap">
              {t("skills.subtitle")}
            </p>
          </div>
          <div className="flex gap-1.5 sm:gap-2">
            {canWrite && (
              <>
                <button
                  onClick={handleGithubClick}
                  className="btn-secondary !py-1.5 !px-2 sm:!py-2 sm:!px-3"
                  title={t("skills.importFromGitHub")}
                >
                  <Github size={16} />
                  <span className="hidden sm:inline">GitHub</span>
                </button>
                <button
                  onClick={handleImportClick}
                  className="btn-secondary !py-1.5 !px-2 sm:!py-2 sm:!px-3"
                  title={t("skills.importFromJSON")}
                >
                  <Upload size={16} />
                  <span className="hidden sm:inline">{t("common.import")}</span>
                </button>
                <button
                  onClick={handleExport}
                  className="btn-secondary !py-1.5 !px-2 sm:!py-2 sm:!px-3"
                  title={t("skills.exportToJSON")}
                >
                  <Download size={16} />
                  <span className="hidden sm:inline">{t("common.export")}</span>
                </button>
                <button
                  onClick={handleCreate}
                  className="btn-primary !py-1.5 !px-2 sm:!py-2 sm:!px-3 whitespace-nowrap"
                >
                  <Plus size={16} />
                  <span className="hidden sm:inline">
                    {t("skills.newSkill")}
                  </span>
                </button>
              </>
            )}
          </div>
        </div>

        {/* Search */}
        <div className="relative mt-2 sm:mt-3">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
          />
          <input
            type="text"
            placeholder={t("skills.searchPlaceholder")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="panel-search !py-2"
          />
        </div>
      </div>

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
            <Loader2 size={24} className="animate-spin" />
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
            {filteredSkills.map((skill) => (
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

      {/* Form Modal - Bottom Sheet */}
      {showModal && (
        <>
          <div className="fixed inset-0 " onClick={handleCancel} />
          <div className="modal-bottom-sheet sm:modal-centered-wrapper">
            <div className="modal-bottom-sheet-content sm:modal-centered-content">
              <div className="bottom-sheet-handle sm:hidden" />
              {/* Header */}
              <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4 dark:border-stone-800">
                <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                  {isCreating
                    ? t("skills.createNew")
                    : t("skills.editSkill", { name: editingSkill?.name })}
                </h3>
                <button onClick={handleCancel} className="btn-icon">
                  <X size={20} />
                </button>
              </div>
              {/* Content */}
              <div className="flex-1 overflow-y-auto px-2 sm:px-6 py-4 space-y-2">
                <SkillForm
                  skill={editingSkill}
                  onSave={handleSave}
                  onCancel={handleCancel}
                  isLoading={isLoading}
                  isAdmin={canAdmin}
                />
              </div>
            </div>
          </div>
        </>
      )}

      {/* Import Modal - Bottom Sheet */}
      {showImportModal && (
        <>
          <div
            className="fixed inset-0 "
            onClick={() => setShowImportModal(false)}
          />
          <div className="modal-bottom-sheet sm:modal-centered-wrapper">
            <div className="modal-bottom-sheet-content sm:modal-centered-content">
              <div className="bottom-sheet-handle sm:hidden" />
              {/* Header */}
              <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4 dark:border-stone-800">
                <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                  {t("skills.importSkills")}
                </h3>
                <button
                  onClick={() => setShowImportModal(false)}
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
                      {t("skills.jsonConfig")}
                    </label>
                    <textarea
                      value={importJson}
                      onChange={(e) => setImportJson(e.target.value)}
                      rows={10}
                      placeholder={`{
  "skills": {
    "skill-name": {
      "description": "A helpful skill",
      "content": "You are a helpful assistant that...",
      "enabled": true
    }
  }
}`}
                      className="w-full rounded-xl border border-stone-200 bg-white px-3 py-2 font-mono text-sm text-stone-900 placeholder-stone-400 focus:border-stone-400 focus:outline-none dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:placeholder-stone-500"
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      id="importOverwrite"
                      checked={importOverwrite}
                      onChange={(e) => setImportOverwrite(e.target.checked)}
                      className="h-4 w-4 rounded border-stone-300 text-stone-600 focus:ring-stone-500 dark:border-stone-600 dark:bg-stone-800"
                    />
                    <label
                      htmlFor="importOverwrite"
                      className="text-sm text-stone-700 dark:text-stone-300"
                    >
                      {t("skills.overwriteExisting")}
                    </label>
                  </div>

                  {importResult && (
                    <div
                      className={`flex items-center gap-2 rounded-xl p-3 ${
                        importResult.success
                          ? "bg-green-50 text-green-700 dark:bg-green-900/30 dark:text-green-400"
                          : "bg-red-50 text-red-700 dark:bg-red-900/30 dark:text-red-400"
                      }`}
                    >
                      {importResult.success ? (
                        <Check size={20} className="flex-shrink-0" />
                      ) : (
                        <X size={20} className="flex-shrink-0" />
                      )}
                      <span className="whitespace-pre-wrap text-sm">
                        {importResult.message}
                      </span>
                    </div>
                  )}

                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setShowImportModal(false)}
                      className="btn-secondary"
                    >
                      {t("common.cancel")}
                    </button>
                    <button
                      onClick={handleImport}
                      disabled={isLoading || !importJson.trim()}
                      className="btn-primary disabled:opacity-50"
                    >
                      {isLoading ? (
                        <>
                          <Loader2 size={18} className="animate-spin" />
                          {t("common.importing")}
                        </>
                      ) : (
                        <>
                          <Upload size={18} />
                          {t("common.import")}
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
          <div
            className="fixed inset-0 "
            onClick={() => setShowGithubModal(false)}
          />
          <div className="modal-bottom-sheet sm:modal-centered-wrapper">
            <div className="modal-bottom-sheet-content sm:modal-centered-content">
              <div className="bottom-sheet-handle sm:hidden" />
              {/* Header */}
              <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4 dark:border-stone-800">
                <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
                  {t("skills.importFromGitHubTitle")}
                </h3>
                <button
                  onClick={() => setShowGithubModal(false)}
                  className="btn-icon"
                >
                  <X size={20} />
                </button>
              </div>
              {/* Content */}
              <div className="flex-1 overflow-y-auto px-2 sm:px-6 py-4 space-y-2">
                <div className="space-y-4">
                  {/* Repository URL */}
                  <div>
                    <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
                      {t("skills.repositoryUrl")}
                    </label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={githubUrl}
                        onChange={(e) => setGithubUrl(e.target.value)}
                        placeholder="https://github.com/owner/repo"
                        className="flex-1 rounded-xl border border-stone-200 px-3 py-2 text-sm text-stone-900 placeholder-stone-400 focus:border-stone-400 focus:outline-none dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:placeholder-stone-500"
                      />
                      <input
                        type="text"
                        value={githubBranch}
                        onChange={(e) => setGithubBranch(e.target.value)}
                        placeholder="main"
                        className="w-24 rounded-xl border border-stone-200 px-3 py-2 text-sm text-stone-900 placeholder-stone-400 focus:border-stone-400 focus:outline-none dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:placeholder-stone-500"
                      />
                      <button
                        onClick={handleGithubPreview}
                        disabled={githubLoading || !githubUrl.trim()}
                        className="btn-secondary disabled:opacity-50"
                      >
                        {githubLoading ? (
                          <Loader2 size={18} className="animate-spin" />
                        ) : (
                          <Search size={18} />
                        )}
                        <span className="hidden sm:inline">Preview</span>
                      </button>
                    </div>
                  </div>

                  {/* Skills Preview */}
                  {githubSkills.length > 0 && (
                    <div>
                      <label className="mb-2 block text-sm font-medium text-stone-700 dark:text-stone-300">
                        {t("skills.foundSkills", {
                          count: githubSkills.length,
                        })}
                      </label>
                      <div className="max-h-60 space-y-2 overflow-y-auto rounded-xl border border-stone-200 p-2 dark:border-stone-700">
                        {githubSkills.map((skill) => (
                          <label
                            key={skill.name}
                            className="flex cursor-pointer items-start gap-2 rounded-xl p-2 hover:bg-stone-50 dark:hover:bg-stone-800"
                          >
                            <input
                              type="checkbox"
                              checked={selectedGithubSkills.includes(
                                skill.name,
                              )}
                              onChange={() => toggleGithubSkill(skill.name)}
                              className="mt-0.5 h-4 w-4 rounded border-stone-300 text-stone-600 focus:ring-stone-500 dark:border-stone-600 dark:bg-stone-800"
                            />
                            <div className="flex-1">
                              <div className="font-medium text-stone-900 dark:text-stone-100">
                                {skill.name}
                              </div>
                              <div className="text-xs text-stone-500 dark:text-stone-400">
                                {skill.description || t("skills.noDescription")}
                              </div>
                            </div>
                          </label>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Admin option */}
                  {canAdmin && selectedGithubSkills.length > 0 && (
                    <div className="flex items-center gap-2 rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 dark:border-amber-800 dark:bg-amber-900/20">
                      <input
                        type="checkbox"
                        id="githubInstallAsSystem"
                        checked={githubInstallAsSystem}
                        onChange={(e) =>
                          setGithubInstallAsSystem(e.target.checked)
                        }
                        className="h-4 w-4 rounded border-stone-300 text-amber-600 focus:ring-amber-500 dark:border-stone-600 dark:bg-stone-800"
                      />
                      <label
                        htmlFor="githubInstallAsSystem"
                        className="text-sm text-amber-800 dark:text-amber-200"
                      >
                        {t("skills.installAsSystem")}
                      </label>
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setShowGithubModal(false)}
                      className="btn-secondary"
                    >
                      {t("common.cancel")}
                    </button>
                    <button
                      onClick={handleGithubInstall}
                      disabled={
                        githubLoading || selectedGithubSkills.length === 0
                      }
                      className="btn-primary disabled:opacity-50"
                    >
                      {githubLoading ? (
                        <>
                          <Loader2 size={18} className="animate-spin" />
                          {t("skills.installing")}
                        </>
                      ) : (
                        <>
                          <Github size={18} />
                          {t("skills.installCount", {
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
