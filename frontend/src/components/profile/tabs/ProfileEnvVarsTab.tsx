import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Trash2, Braces, Pencil, X, Check } from "lucide-react";
import { toast } from "react-hot-toast";
import { envvarApi } from "../../../services/api/envvar";
import type { EnvVarResponse } from "../../../services/api/envvar";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types/auth";
import { SkeletonList } from "../../skeletons";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { ConfirmDialog } from "../../common/ConfirmDialog";

const ENV_KEY_REGEX = /^[A-Za-z_][A-Za-z0-9_]*$/;
const MAX_VALUE_LENGTH = 4096;

export function ProfileEnvVarsTab() {
  const { t } = useTranslation();
  const { hasAnyPermission } = useAuth();

  const canRead = hasAnyPermission([Permission.ENVVAR_READ]);
  const canWrite = hasAnyPermission([Permission.ENVVAR_WRITE]);
  const canDelete = hasAnyPermission([Permission.ENVVAR_DELETE]);

  const [vars, setVars] = useState<EnvVarResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadFailed, setLoadFailed] = useState(false);

  // 新建状态
  const [newKey, setNewKey] = useState("");
  const [newValue, setNewValue] = useState("");
  const [adding, setAdding] = useState(false);

  // 编辑状态（不回填旧值，直接输入新值覆盖）
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState("");
  const [saving, setSaving] = useState(false);

  // 删除确认框
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const fetchVars = useCallback(async () => {
    if (!canRead) return;
    setLoading(true);
    setLoadFailed(false);
    try {
      const res = await envvarApi.list();
      setVars(res.variables);
    } catch {
      setLoadFailed(true);
    } finally {
      setLoading(false);
    }
  }, [canRead]);

  useEffect(() => {
    fetchVars();
  }, [fetchVars]);

  // 添加新变量
  const handleAdd = async () => {
    const trimmedKey = newKey.trim();
    const trimmedValue = newValue.trim();
    if (!trimmedKey || !trimmedValue) return;
    if (!ENV_KEY_REGEX.test(trimmedKey)) {
      toast.error(t("envVars.invalidKey"));
      return;
    }
    if (trimmedValue.length > MAX_VALUE_LENGTH) {
      toast.error(t("envVars.valueTooLong"));
      return;
    }
    setAdding(true);
    try {
      await envvarApi.set(trimmedKey, trimmedValue);
      toast.success(t("envVars.added"));
      setNewKey("");
      setNewValue("");
      fetchVars();
    } catch (err) {
      toast.error((err as Error).message || t("envVars.addFailed"));
    } finally {
      setAdding(false);
    }
  };

  // 开始编辑（不请求旧值，直接输入新值）
  const startEdit = (key: string) => {
    setEditingKey(key);
    setEditingValue("");
  };

  // 保存编辑
  const saveEdit = async () => {
    if (!editingKey || !editingValue.trim()) return;
    setSaving(true);
    try {
      await envvarApi.set(editingKey, editingValue.trim());
      toast.success(t("envVars.updated"));
      setEditingKey(null);
      setEditingValue("");
      fetchVars();
    } catch {
      toast.error(t("envVars.updateFailed"));
    } finally {
      setSaving(false);
    }
  };

  // 取消编辑
  const cancelEdit = () => {
    setEditingKey(null);
    setEditingValue("");
  };

  // 删除
  const handleDelete = async (key: string) => {
    setDeleteTarget(key);
  };

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await envvarApi.delete(deleteTarget);
      toast.success(t("envVars.deleted"));
      fetchVars();
    } catch {
      toast.error(t("envVars.deleteFailed"));
    } finally {
      setDeleteTarget(null);
    }
  };

  if (!canRead) {
    return (
      <div className="flex items-center justify-center py-12 text-theme-text-tertiary dark:text-stone-500 text-14">
        {t("common.noPermission")}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <ConfirmDialog
        isOpen={deleteTarget !== null}
        title={t("envVars.confirmDelete", { key: deleteTarget ?? "" })}
        message={t("envVars.description")}
        onConfirm={confirmDelete}
        onCancel={() => setDeleteTarget(null)}
        variant="danger"
      />
      <div className="profile-section">
        <p className="text-12 text-theme-text-secondary dark:text-stone-400 mb-3">
          {t("envVars.description")}
        </p>

        {/* 添加新变量 */}
        {canWrite && (
          <div className="profile-env-form">
            <label>
              {t("envVars.keyLabel")}
              <input
                type="text"
                value={newKey}
                onChange={(e) => setNewKey(e.target.value)}
                placeholder={t("envVars.keyPlaceholder")}
                className="profile-input"
                onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              />
            </label>
            <label>
              {t("envVars.valueLabel")}
              <input
                type="password"
                value={newValue}
                onChange={(e) => setNewValue(e.target.value)}
                placeholder={t("envVars.valuePlaceholder")}
                className="profile-input"
                onKeyDown={(e) => e.key === "Enter" && handleAdd()}
              />
            </label>
            <button
              aria-label={t("common.add")}
              onClick={handleAdd}
              disabled={adding || !newKey.trim() || !newValue.trim()}
              className="profile-icon-button ui-button ui-button--primary !size-11"
            >
              {adding ? (
                <LoadingSpinner size="xs" color="text-white" />
              ) : (
                <Plus size={14} />
              )}
            </button>
          </div>
        )}

        {/* 变量列表 */}
        {loading ? (
          <SkeletonList count={4} className="py-1" />
        ) : loadFailed ? (
          <div role="alert" className="profile-empty">
            <p className="text-theme-error">{t("envVars.fetchFailed")}</p>
            <button
              type="button"
              className="ui-button ui-button--secondary ui-button--md"
              onClick={fetchVars}
            >
              {t("common.refresh")}
            </button>
          </div>
        ) : vars.length === 0 ? (
          <div className="profile-empty">
            <Braces size={24} strokeWidth={1.5} aria-hidden="true" />
            {t("envVars.empty")}
          </div>
        ) : (
          <div className="space-y-1.5">
            {vars.map((envVar) => (
              <div key={envVar.key} className="profile-env-row group">
                {editingKey === envVar.key ? (
                  <>
                    <span className="profile-env-key">{envVar.key}</span>
                    <span className="text-theme-border-hover dark:text-stone-600">
                      =
                    </span>
                    <input
                      type="password"
                      value={editingValue}
                      onChange={(e) => setEditingValue(e.target.value)}
                      placeholder={t("envVars.newValuePlaceholder")}
                      aria-label={t("envVars.newValuePlaceholder")}
                      className="profile-input flex-1"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveEdit();
                        if (e.key === "Escape") cancelEdit();
                      }}
                    />
                    <button
                      aria-label={t("common.save")}
                      onClick={saveEdit}
                      disabled={saving || !editingValue.trim()}
                      className="profile-icon-button text-theme-success disabled:opacity-40"
                    >
                      {saving ? (
                        <LoadingSpinner
                          size="xs"
                          color="text-theme-success dark:text-green-400"
                        />
                      ) : (
                        <Check size={12} />
                      )}
                    </button>
                    <button
                      aria-label={t("common.cancel")}
                      onClick={cancelEdit}
                      className="profile-icon-button"
                    >
                      <X size={12} />
                    </button>
                  </>
                ) : (
                  <>
                    <span className="profile-env-key">{envVar.key}</span>
                    <span className="text-theme-border-hover dark:text-stone-600">
                      =
                    </span>
                    <span className="flex-1 min-w-0 text-12 font-mono text-theme-text-tertiary dark:text-stone-500 select-none">
                      ••••••••
                    </span>
                    <div className="shrink-0 flex items-center gap-1">
                      {canWrite && (
                        <button
                          onClick={() => startEdit(envVar.key)}
                          className="profile-icon-button"
                          title={t("envVars.edit")}
                        >
                          <Pencil size={12} />
                        </button>
                      )}
                      {canDelete && (
                        <button
                          onClick={() => handleDelete(envVar.key)}
                          className="profile-icon-button !text-theme-error"
                          title={t("envVars.delete")}
                        >
                          <Trash2 size={12} />
                        </button>
                      )}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        )}

        {vars.length > 0 && (
          <div className="mt-2 text-right text-10 text-theme-text-tertiary dark:text-stone-500">
            {t("envVars.count", { count: vars.length })}
          </div>
        )}
      </div>
    </div>
  );
}
