import { useState, useRef } from "react";
import {
  X,
  Plus,
  RefreshCw,
  Upload,
  Trash2,
  Edit3,
  ShoppingBag,
  Loader2,
  FileText,
  Tag,
  Save,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { useAdminMarketplace } from "../../hooks/useAdminMarketplace";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";

interface SkillFormData {
  skill_name: string;
  description: string;
  tags: string;
  version: string;
}

const emptyForm: SkillFormData = {
  skill_name: "",
  description: "",
  tags: "",
  version: "1.0.0",
};

export function AdminMarketplacePanel() {
  const { t } = useTranslation();
  const { hasAnyPermission } = useAuth();
  const {
    skills,
    isLoading,
    error,
    fetchSkills,
    createSkill,
    updateSkill,
    deleteSkill,
    uploadZip,
    clearError,
  } = useAdminMarketplace();

  const canAdmin = hasAnyPermission([Permission.SKILL_ADMIN]);

  // Modal state
  const [showForm, setShowForm] = useState(false);
  const [editingSkill, setEditingSkill] = useState<string | null>(null);
  const [formData, setFormData] = useState<SkillFormData>(emptyForm);
  const [formLoading, setFormLoading] = useState(false);

  // Delete confirmation
  const [deleteConfirm, setDeleteConfirm] = useState<{
    isOpen: boolean;
    skillName: string;
  } | null>(null);

  // Upload state
  const [uploadingSkill, setUploadingSkill] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploadTarget, setUploadTarget] = useState<string | null>(null);

  const handleCreate = () => {
    setEditingSkill(null);
    setFormData(emptyForm);
    setShowForm(true);
  };

  const handleEdit = (skillName: string) => {
    const skill = skills.find((s) => s.skill_name === skillName);
    if (!skill) return;
    setEditingSkill(skillName);
    setFormData({
      skill_name: skill.skill_name,
      description: skill.description || "",
      tags: skill.tags.join(", "),
      version: skill.version || "1.0.0",
    });
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!formData.skill_name.trim()) {
      toast.error(t("adminMarketplace.nameRequired"));
      return;
    }

    setFormLoading(true);
    const data = {
      skill_name: formData.skill_name.trim(),
      description: formData.description.trim(),
      tags: formData.tags
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean),
      version: formData.version.trim() || "1.0.0",
    };

    const success = editingSkill
      ? await updateSkill(editingSkill, data)
      : await createSkill(data);

    if (success) {
      toast.success(
        editingSkill
          ? t("adminMarketplace.updateSuccess")
          : t("adminMarketplace.createSuccess"),
      );
      setShowForm(false);
    }
    setFormLoading(false);
  };

  const handleDeleteConfirm = async () => {
    if (!deleteConfirm) return;
    const success = await deleteSkill(deleteConfirm.skillName);
    if (success) {
      toast.success(t("adminMarketplace.deleteSuccess"));
    }
    setDeleteConfirm(null);
  };

  const handleUploadClick = (skillName: string) => {
    setUploadTarget(skillName);
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file || !uploadTarget) return;

    if (!file.name.endsWith(".zip")) {
      toast.error(t("adminMarketplace.zipRequired"));
      return;
    }

    setUploadingSkill(uploadTarget);
    const success = await uploadZip(uploadTarget, file);
    if (success) {
      toast.success(
        t("adminMarketplace.uploadSuccess", { name: uploadTarget }),
      );
    }
    setUploadingSkill(null);
    setUploadTarget(null);
    // Reset file input
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  if (!canAdmin) {
    return (
      <div className="flex h-full items-center justify-center text-stone-500 dark:text-stone-400">
        <p>{t("common.noPermission")}</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col min-h-0">
      {/* Hidden file input for ZIP upload */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".zip"
        className="hidden"
        onChange={handleFileChange}
      />

      {/* Header */}
      <PanelHeader
        title={t("adminMarketplace.title")}
        subtitle={t("adminMarketplace.subtitle")}
        icon={
          <ShoppingBag
            size={18}
            className="text-stone-600 dark:text-stone-400"
          />
        }
        actions={
          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchSkills()}
              className="btn-secondary"
              title={t("common.refresh")}
            >
              <RefreshCw size={16} className="sm:size-[18px]" />
            </button>
            <button onClick={handleCreate} className="btn-primary">
              <Plus size={16} />
              <span className="hidden sm:inline">
                {t("adminMarketplace.createSkill")}
              </span>
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
      <div className="flex-1 overflow-y-auto p-2 sm:p-4">
        {isLoading && skills.length === 0 ? (
          <div className="flex h-full items-center justify-center text-stone-500 dark:text-stone-400">
            <LoadingSpinner size="sm" />
            <span className="ml-2">{t("adminMarketplace.loading")}</span>
          </div>
        ) : skills.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-stone-500 dark:text-stone-400 px-4">
            <ShoppingBag
              size={40}
              className="mb-3 text-stone-300 dark:text-stone-600"
            />
            <p className="text-sm">{t("adminMarketplace.noSkills")}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {skills.map((skill) => (
              <div
                key={skill.skill_name}
                className="rounded-xl border border-stone-200 bg-white p-3 dark:border-stone-700 dark:bg-stone-800/50"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <h3 className="font-medium text-stone-900 dark:text-stone-100 truncate">
                      {skill.skill_name}
                    </h3>
                    <p className="mt-1 text-sm text-stone-500 dark:text-stone-400 line-clamp-2">
                      {skill.description || t("marketplace.noDescription")}
                    </p>
                  </div>
                  {/* Action buttons */}
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button
                      onClick={() => handleUploadClick(skill.skill_name)}
                      disabled={uploadingSkill === skill.skill_name}
                      className="btn-icon"
                      title={t("adminMarketplace.uploadZip")}
                    >
                      {uploadingSkill === skill.skill_name ? (
                        <Loader2 size={18} className="animate-spin" />
                      ) : (
                        <Upload size={18} />
                      )}
                    </button>
                    <button
                      onClick={() => handleEdit(skill.skill_name)}
                      className="btn-icon"
                      title={t("common.edit")}
                    >
                      <Edit3 size={18} />
                    </button>
                    <button
                      onClick={() =>
                        setDeleteConfirm({
                          isOpen: true,
                          skillName: skill.skill_name,
                        })
                      }
                      className="btn-icon hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                      title={t("common.delete")}
                    >
                      <Trash2 size={18} />
                    </button>
                  </div>
                </div>

                {/* Meta */}
                <div className="mt-2 flex items-center gap-3 text-xs text-stone-400 dark:text-stone-500">
                  {skill.tags.length > 0 && (
                    <div className="flex items-center gap-1 flex-wrap">
                      {skill.tags.slice(0, 5).map((tag) => (
                        <span
                          key={tag}
                          className="rounded bg-stone-100 px-1.5 py-0.5 dark:bg-stone-700"
                        >
                          {tag}
                        </span>
                      ))}
                      {skill.tags.length > 5 && (
                        <span>+{skill.tags.length - 5}</span>
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
                  {skill.created_by && (
                    <span className="text-stone-400">
                      {t("adminMarketplace.createdBy", {
                        who: skill.created_by,
                      })}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Delete Confirmation */}
      <ConfirmDialog
        isOpen={deleteConfirm?.isOpen ?? false}
        title={t("adminMarketplace.confirmDelete", {
          name: deleteConfirm?.skillName,
        })}
        message={t("adminMarketplace.confirmDeleteMessage")}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setDeleteConfirm(null)}
        variant="danger"
      />

      {/* Create/Edit Form Modal */}
      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md rounded-xl bg-white shadow-xl dark:bg-stone-800">
            <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3 dark:border-stone-700">
              <h2 className="font-medium text-stone-900 dark:text-stone-100">
                {editingSkill
                  ? t("adminMarketplace.editSkill")
                  : t("adminMarketplace.createSkill")}
              </h2>
              <button onClick={() => setShowForm(false)} className="btn-icon">
                <X size={18} />
              </button>
            </div>

            <div className="p-4 space-y-3">
              {/* Skill Name */}
              <div>
                <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
                  {t("adminMarketplace.skillName")} *
                </label>
                <input
                  type="text"
                  value={formData.skill_name}
                  onChange={(e) =>
                    setFormData((f) => ({ ...f, skill_name: e.target.value }))
                  }
                  disabled={!!editingSkill}
                  className="input-field w-full"
                  placeholder={t("adminMarketplace.skillNamePlaceholder")}
                />
              </div>

              {/* Description */}
              <div>
                <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
                  {t("adminMarketplace.description")}
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) =>
                    setFormData((f) => ({ ...f, description: e.target.value }))
                  }
                  className="input-field w-full min-h-[80px]"
                  placeholder={t("adminMarketplace.descriptionPlaceholder")}
                />
              </div>

              {/* Tags */}
              <div>
                <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
                  {t("adminMarketplace.tags")}
                </label>
                <div className="relative">
                  <Tag
                    size={14}
                    className="absolute left-2.5 top-1/2 -translate-y-1/2 text-stone-400"
                  />
                  <input
                    type="text"
                    value={formData.tags}
                    onChange={(e) =>
                      setFormData((f) => ({ ...f, tags: e.target.value }))
                    }
                    className="input-field w-full pl-8"
                    placeholder={t("adminMarketplace.tagsPlaceholder")}
                  />
                </div>
                <p className="mt-1 text-xs text-stone-400">
                  {t("adminMarketplace.tagsHint")}
                </p>
              </div>

              {/* Version */}
              <div>
                <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
                  {t("adminMarketplace.version")}
                </label>
                <input
                  type="text"
                  value={formData.version}
                  onChange={(e) =>
                    setFormData((f) => ({ ...f, version: e.target.value }))
                  }
                  className="input-field w-full"
                  placeholder="1.0.0"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 border-t border-stone-200 px-4 py-3 dark:border-stone-700">
              <button
                onClick={() => setShowForm(false)}
                className="btn-secondary"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={handleSave}
                disabled={formLoading}
                className="btn-primary"
              >
                {formLoading ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : (
                  <Save size={14} />
                )}
                <span>{t("common.save")}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
