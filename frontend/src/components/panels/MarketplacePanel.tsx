import { useState, useEffect } from "react";
import {
  X,
  Download,
  RefreshCw,
  Tag,
  FileText,
  ShoppingBag,
  Loader2,
  Eye,
  ChevronRight,
  RefreshCcw,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { useMarketplace } from "../../hooks/useMarketplace";
import { useSkills } from "../../hooks/useSkills";
import { Permission } from "../../types";
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
    clearError,
    previewSkill,
    previewFiles,
    previewLoading,
    previewFileContent,
    previewFileLoading,
    openPreview,
    readPreviewFile,
    closePreview,
  } = useMarketplace();

  const { skills: userSkills, fetchSkills: fetchUserSkills } = useSkills();
  const canWrite = hasAnyPermission([Permission.SKILL_WRITE]);

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
        // Refresh user skills list
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
          <button
            onClick={() => fetchSkills()}
            className="btn-secondary"
            title={t("common.refresh")}
          >
            <RefreshCw size={16} className="sm:size-[18px]" />
          </button>
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
        <div className="border-b border-stone-200 px-4 py-2 dark:border-stone-800">
          <div className="flex items-center gap-2 flex-wrap">
            <Tag size={14} className="text-stone-400 flex-shrink-0" />
            {tags.map((tag) => (
              <button
                key={tag}
                onClick={() => toggleTag(tag)}
                className={`rounded-full px-2 py-0.5 text-xs font-medium transition-colors ${
                  selectedTags.includes(tag)
                    ? "bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300"
                    : "bg-stone-100 text-stone-600 hover:bg-stone-200 dark:bg-stone-800 dark:text-stone-400 dark:hover:bg-stone-700"
                }`}
              >
                {tag}
              </button>
            ))}
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="text-xs text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200"
              >
                {t("common.clear")}
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
            <span className="ml-2">{t("marketplace.loading")}</span>
          </div>
        ) : skills.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-stone-500 dark:text-stone-400 px-4">
            <ShoppingBag
              size={40}
              className="mb-3 sm:mb-2 text-stone-300 dark:text-stone-600"
            />
            <p className="text-sm sm:text-base">
              {searchQuery || selectedTags.length > 0
                ? t("marketplace.noMatchingSkills")
                : t("marketplace.noSkills")}
            </p>
            {hasActiveFilters && (
              <button
                onClick={clearFilters}
                className="mt-3 sm:mt-2 text-sm text-stone-600 hover:text-stone-900 dark:text-stone-400 dark:hover:text-stone-100"
              >
                {t("marketplace.clearFilters")}
              </button>
            )}
          </div>
        ) : (
          <div className="space-y-2">
            {skills.map((skill) => {
              const isInstalled = installedNames.has(skill.skill_name);
              return (
                <div
                  key={skill.skill_name}
                  className="rounded-xl border border-stone-200 bg-white p-3 dark:border-stone-700 dark:bg-stone-800/50"
                >
                  {/* Skill Header */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <h3 className="font-medium text-stone-900 dark:text-stone-100 truncate">
                        {skill.skill_name}
                      </h3>
                      <p className="mt-1 text-sm text-stone-500 dark:text-stone-400 line-clamp-2">
                        {skill.description || t("marketplace.noDescription")}
                      </p>
                    </div>
                  </div>

                  {/* Skill Meta */}
                  <div className="mt-2 flex items-center gap-3 text-xs text-stone-400 dark:text-stone-500">
                    {skill.tags.length > 0 && (
                      <div className="flex items-center gap-1 flex-wrap">
                        {skill.tags.slice(0, 3).map((tag) => (
                          <span
                            key={tag}
                            className="rounded bg-stone-100 px-1.5 py-0.5 dark:bg-stone-700"
                          >
                            {tag}
                          </span>
                        ))}
                        {skill.tags.length > 3 && (
                          <span>+{skill.tags.length - 3}</span>
                        )}
                      </div>
                    )}
                    <div className="flex items-center gap-1">
                      <FileText size={12} />
                      <span>
                        {skill.file_count} {t("marketplace.files")}
                      </span>
                    </div>
                    <span>v{skill.version}</span>
                    {isInstalled && (
                      <span className="rounded-full bg-green-100 px-1.5 py-0.5 text-green-700 dark:bg-green-900/40 dark:text-green-300">
                        {t("marketplace.installed")}
                      </span>
                    )}
                  </div>

                  {/* Action Buttons */}
                  {canWrite && (
                    <div className="mt-3 flex justify-end gap-2">
                      <button
                        onClick={() => openPreview(skill)}
                        className="btn-secondary text-xs"
                      >
                        <Eye size={14} />
                        <span>{t("marketplace.preview")}</span>
                      </button>
                      {installingSkill === skill.skill_name ? (
                        <button
                          disabled
                          className="btn-primary opacity-50 text-xs"
                        >
                          <Loader2 size={14} className="animate-spin" />
                          <span>{t("marketplace.installing")}</span>
                        </button>
                      ) : (
                        <button
                          onClick={() => handleInstallClick(skill.skill_name)}
                          className={`text-xs ${
                            isInstalled ? "btn-secondary" : "btn-primary"
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
                      )}
                    </div>
                  )}
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
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-2xl max-h-[80vh] flex flex-col rounded-xl bg-white shadow-xl dark:bg-stone-800">
            {/* Modal Header */}
            <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3 dark:border-stone-700">
              <div className="flex items-center gap-2 min-w-0">
                <ShoppingBag
                  size={18}
                  className="text-stone-500 flex-shrink-0"
                />
                <h2 className="font-medium text-stone-900 dark:text-stone-100 truncate">
                  {previewSkill.skill_name}
                </h2>
                <span className="text-xs text-stone-400">
                  v{previewSkill.version}
                </span>
              </div>
              <button onClick={closePreview} className="btn-icon">
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-4">
              {/* Description */}
              <p className="text-sm text-stone-600 dark:text-stone-400 mb-3">
                {previewSkill.description || t("marketplace.noDescription")}
              </p>

              {/* Tags */}
              {previewSkill.tags.length > 0 && (
                <div className="flex flex-wrap gap-1 mb-4">
                  {previewSkill.tags.map((tag) => (
                    <span
                      key={tag}
                      className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-600 dark:bg-stone-700 dark:text-stone-400"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}

              {/* Files */}
              {previewLoading ? (
                <div className="flex items-center gap-2 text-sm text-stone-500">
                  <LoadingSpinner size="sm" />
                  <span>{t("marketplace.loadingFiles")}</span>
                </div>
              ) : previewFiles ? (
                <div>
                  <h3 className="text-sm font-medium text-stone-700 dark:text-stone-300 mb-2">
                    {t("marketplace.skillFiles")} ({previewFiles.files.length})
                  </h3>
                  <div className="space-y-1">
                    {previewFiles.files.map((filePath) => (
                      <div key={filePath}>
                        <button
                          onClick={() => {
                            if (!previewFileContent[filePath]) {
                              readPreviewFile(
                                previewSkill.skill_name,
                                filePath,
                              );
                            }
                          }}
                          className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm text-stone-700 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-700/50 text-left"
                        >
                          <FileText
                            size={14}
                            className="text-stone-400 flex-shrink-0"
                          />
                          <span className="flex-1 truncate">{filePath}</span>
                          {previewFileLoading === filePath ? (
                            <Loader2
                              size={12}
                              className="animate-spin text-stone-400"
                            />
                          ) : (
                            <ChevronRight
                              size={14}
                              className="text-stone-400"
                            />
                          )}
                        </button>
                        {previewFileContent[filePath] && (
                          <pre className="mt-1 max-h-60 overflow-auto rounded-lg bg-stone-50 p-3 text-xs text-stone-700 dark:bg-stone-900/50 dark:text-stone-300 whitespace-pre-wrap break-all">
                            {previewFileContent[filePath]}
                          </pre>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <p className="text-sm text-stone-500">
                  {t("marketplace.noFiles")}
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
