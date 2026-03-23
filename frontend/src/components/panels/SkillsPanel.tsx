/**
 * SkillsPanel - Simplified Architecture
 *
 * New backend supports:
 * - List, get, create, update, delete user skills
 * - Toggle skill enabled/disabled
 * - Marketplace browse and install
 *
 * Removed features (not in new backend):
 * - GitHub import
 * - ZIP upload
 * - JSON import/export
 * - Promote/demote system skills
 */

import { useState, useEffect } from "react";
import { Plus, X, FolderOpen, PackageX } from "lucide-react";
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

export function SkillsPanel() {
  const { t } = useTranslation();
  const { enableSkills } = useSettingsContext();
  const {
    skills,
    isLoading,
    error,
    createSkill,
    updateSkill,
    deleteSkill,
    toggleSkill,
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
  const canAdmin = hasAnyPermission([Permission.SKILL_ADMIN]);

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

  const handleEdit = (skill: SkillResponse) => {
    setEditingSkill(skill);
    setIsCreating(false);
    setShowModal(true);
  };

  const handleSave = async (
    data: SkillCreate,
    _isSystem: boolean,
  ): Promise<boolean> => {
    let success = false;

    try {
      if (isCreating) {
        success = await createSkill(data);
        if (success) {
          // toast.success(t("skills.createSuccess")); // TODO: wire toast
        }
      } else if (editingSkill) {
        success = await updateSkill(editingSkill.name, {
          description: data.description,
          content: data.content,
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
            <button onClick={handleCreate} className="btn-primary">
              <Plus size={16} />
              <span className="hidden sm:inline">{t("skills.newSkill")}</span>
            </button>
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
                  isAdmin={canAdmin}
                  onFullscreenChange={setIsFormFullscreen}
                />
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
