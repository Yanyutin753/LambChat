import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Trash2, Braces, Pencil, X, Check } from "lucide-react";
import { toast } from "react-hot-toast";
import { envvarApi } from "../../../services/api/envvar";
import type { EnvVarResponse } from "../../../services/api/envvar";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types/auth";
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
    try {
      const res = await envvarApi.list();
      setVars(res.variables);
    } catch {
      toast.error(t("envVars.fetchFailed"));
    } finally {
      setLoading(false);
    }
  }, [canRead, t]);

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
      <div className="flex items-center justify-center py-12 text-stone-400 dark:text-stone-500 text-sm">
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
      <div className="rounded-2xl bg-stone-50 dark:bg-stone-700/40 p-4 border border-stone-200/60 dark:border-stone-600/40">
        <div className="flex items-center gap-2 mb-3">
          <Braces size={15} className="text-amber-500 dark:text-amber-400" />
          <h3 className="text-xs font-semibold uppercase tracking-wide text-stone-400 dark:text-stone-500">
            {t("envVars.title")}
          </h3>
        </div>
        <p className="text-xs text-stone-500 dark:text-stone-400 mb-3">
          {t("envVars.description")}
        </p>

        {/* 添加新变量 */}
        {canWrite && (
          <div className="flex gap-2 mb-3">
            <input
              type="text"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder={t("envVars.keyPlaceholder")}
              className="flex-1 min-w-0 px-3 py-1.5 text-xs rounded-lg bg-white dark:bg-stone-800 border border-stone-200 dark:border-stone-600 text-stone-800 dark:text-stone-200 placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none focus:ring-1 focus:ring-amber-400"
              onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            />
            <input
              type="password"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              placeholder={t("envVars.valuePlaceholder")}
              className="flex-1 min-w-0 px-3 py-1.5 text-xs rounded-lg bg-white dark:bg-stone-800 border border-stone-200 dark:border-stone-600 text-stone-800 dark:text-stone-200 placeholder:text-stone-400 dark:placeholder:text-stone-500 focus:outline-none focus:ring-1 focus:ring-amber-400"
              onKeyDown={(e) => e.key === "Enter" && handleAdd()}
            />
            <button
              onClick={handleAdd}
              disabled={adding || !newKey.trim() || !newValue.trim()}
              className="shrink-0 p-1.5 rounded-lg bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {adding ? <LoadingSpinner size="xs" /> : <Plus size={14} />}
            </button>
          </div>
        )}

        {/* 变量列表 */}
        {loading ? (
          <div className="flex justify-center py-6">
            <LoadingSpinner size="sm" />
          </div>
        ) : vars.length === 0 ? (
          <div className="text-center py-6 text-xs text-stone-400 dark:text-stone-500">
            {t("envVars.empty")}
          </div>
        ) : (
          <div className="space-y-1.5">
            {vars.map((envVar) => (
              <div
                key={envVar.key}
                className="flex items-center gap-2 px-3 py-2 rounded-lg bg-white dark:bg-stone-800 border border-stone-100 dark:border-stone-600/60 group"
              >
                {editingKey === envVar.key ? (
                  <>
                    <span className="text-xs font-mono font-medium text-stone-700 dark:text-stone-200 shrink-0">
                      {envVar.key}
                    </span>
                    <span className="text-stone-300 dark:text-stone-600">
                      =
                    </span>
                    <input
                      type="password"
                      value={editingValue}
                      onChange={(e) => setEditingValue(e.target.value)}
                      placeholder={t("envVars.newValuePlaceholder")}
                      className="flex-1 min-w-0 px-2 py-0.5 text-xs font-mono rounded bg-stone-50 dark:bg-stone-700 border border-stone-200 dark:border-stone-600 text-stone-800 dark:text-stone-200 placeholder:text-stone-400 focus:outline-none focus:ring-1 focus:ring-amber-400"
                      autoFocus
                      onKeyDown={(e) => {
                        if (e.key === "Enter") saveEdit();
                        if (e.key === "Escape") cancelEdit();
                      }}
                    />
                    <button
                      onClick={saveEdit}
                      disabled={saving || !editingValue.trim()}
                      className="shrink-0 p-1 rounded hover:bg-stone-100 dark:hover:bg-stone-700 text-green-600 transition-colors disabled:opacity-40"
                    >
                      {saving ? (
                        <LoadingSpinner size="xs" />
                      ) : (
                        <Check size={12} />
                      )}
                    </button>
                    <button
                      onClick={cancelEdit}
                      className="shrink-0 p-1 rounded hover:bg-stone-100 dark:hover:bg-stone-700 text-stone-400 transition-colors"
                    >
                      <X size={12} />
                    </button>
                  </>
                ) : (
                  <>
                    <span className="text-xs font-mono font-medium text-stone-700 dark:text-stone-200 shrink-0 max-w-[40%] truncate">
                      {envVar.key}
                    </span>
                    <span className="text-stone-300 dark:text-stone-600">
                      =
                    </span>
                    <span className="flex-1 min-w-0 text-xs font-mono text-stone-400 dark:text-stone-500 select-none">
                      ••••••••
                    </span>
                    <div className="shrink-0 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      {canWrite && (
                        <button
                          onClick={() => startEdit(envVar.key)}
                          className="p-1 rounded hover:bg-stone-100 dark:hover:bg-stone-700 text-stone-400 transition-colors"
                          title={t("envVars.edit")}
                        >
                          <Pencil size={12} />
                        </button>
                      )}
                      {canDelete && (
                        <button
                          onClick={() => handleDelete(envVar.key)}
                          className="p-1 rounded hover:bg-stone-100 dark:hover:bg-stone-700 text-red-400 hover:text-red-500 transition-colors"
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
          <div className="mt-2 text-right text-[10px] text-stone-400 dark:text-stone-500">
            {t("envVars.count", { count: vars.length })}
          </div>
        )}
      </div>
    </div>
  );
}
