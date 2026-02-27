/**
 * 角色管理页面组件
 */

import { useState, useEffect, useCallback } from "react";
import {
  Shield,
  Plus,
  Search,
  Edit,
  Trash2,
  X,
  AlertCircle,
  Lock,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { roleApi, authApi } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type {
  Role,
  RoleCreate,
  RoleUpdate,
  PermissionGroup,
  PermissionInfo,
} from "../../types";

// 角色表单模态框 - 底部弹出式设计
interface RoleFormModalProps {
  role?: Role | null;
  onSave: (data: RoleCreate | RoleUpdate) => Promise<void>;
  onClose: () => void;
  isLoading: boolean;
  permissionGroups: PermissionGroup[];
  permissionLabels: Record<string, string>;
}

function RoleFormModal({
  role,
  onSave,
  onClose,
  isLoading,
  permissionGroups,
  permissionLabels,
}: RoleFormModalProps) {
  const { t } = useTranslation();
  const [name, setName] = useState(role?.name || "");
  const [description, setDescription] = useState(role?.description || "");
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>(
    role?.permissions || [],
  );
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!role;
  const isSystem = role?.is_system || false;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // 验证
    if (!name.trim()) {
      setError(t("roles.validation.enterName"));
      return;
    }
    if (selectedPermissions.length === 0) {
      setError(t("roles.validation.selectPermission"));
      return;
    }

    try {
      const data: RoleCreate | RoleUpdate = {
        name: name.trim(),
        description: description.trim() || undefined,
        permissions: selectedPermissions as Permission[],
      };
      await onSave(data);
      onClose();
    } catch (err) {
      setError((err as Error).message || t("roles.operationFailed"));
    }
  };

  const togglePermission = (permission: string) => {
    setSelectedPermissions((prev) =>
      prev.includes(permission)
        ? prev.filter((p) => p !== permission)
        : [...prev, permission],
    );
  };

  const toggleGroup = (
    groupPermissions: PermissionInfo[],
    checked: boolean,
  ) => {
    const permValues = groupPermissions.map((p) => p.value);
    setSelectedPermissions((prev) => {
      if (checked) {
        return [...new Set([...prev, ...permValues])];
      } else {
        return prev.filter((p) => !permValues.includes(p));
      }
    });
  };

  const isGroupChecked = (groupPermissions: PermissionInfo[]) => {
    return groupPermissions.every((p) => selectedPermissions.includes(p.value));
  };

  const isGroupIndeterminate = (groupPermissions: PermissionInfo[]) => {
    const checkedCount = groupPermissions.filter((p) =>
      selectedPermissions.includes(p.value),
    ).length;
    return checkedCount > 0 && checkedCount < groupPermissions.length;
  };

  return (
    <>
      <div className="fixed inset-0 z-40 sm:hidden" onClick={onClose} />
      <div
        className="modal-bottom-sheet"
        onClick={(e) => {
          if (e.target === e.currentTarget) onClose();
        }}
      >
        <div className="modal-bottom-sheet-content">
          <div className="bottom-sheet-handle sm:hidden" />
          {/* Header */}
          <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4 dark:border-stone-800">
            <h2 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
              {isEditing ? t("roles.editRole") : t("roles.createRole")}
            </h2>
            <button onClick={onClose} className="btn-icon">
              <X size={20} />
            </button>
          </div>

          {isSystem && (
            <div className="mx-6 mt-4 flex items-center gap-2 rounded-xl bg-yellow-50 p-3 text-sm text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400">
              <AlertCircle size={18} />
              <span>{t("roles.systemRoleHint")}</span>
            </div>
          )}

          <form
            onSubmit={handleSubmit}
            className="flex-1 overflow-y-auto px-2 sm:px-6 py-4 space-y-2"
          >
            {error && (
              <div className="flex items-center gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">
                <AlertCircle size={18} />
                <span>{error}</span>
              </div>
            )}

            {/* 角色名称 */}
            <div>
              <label className="mb-1.5 block text-sm font-medium text-stone-700 dark:text-stone-300">
                {t("roles.roleName")}
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                disabled={isSystem}
                className="w-full rounded-lg border border-stone-200 bg-white px-4 py-2 text-sm text-stone-900 placeholder:text-stone-400 focus:border-stone-400 focus:outline-none focus:ring-2 focus:ring-stone-400/20 disabled:bg-stone-100 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:placeholder:text-stone-500 dark:focus:border-stone-500 dark:focus:ring-stone-500/20 dark:disabled:bg-stone-700"
                placeholder={t("roles.roleNamePlaceholder")}
              />
            </div>

            {/* 描述 */}
            <div>
              <label className="mb-1.5 block text-sm font-medium text-stone-700 dark:text-stone-300">
                {t("roles.description")}
              </label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                className="w-full rounded-lg border border-stone-200 bg-white px-4 py-2 text-sm text-stone-900 placeholder:text-stone-400 focus:border-stone-400 focus:outline-none focus:ring-2 focus:ring-stone-400/20 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100 dark:placeholder:text-stone-500 dark:focus:border-stone-500 dark:focus:ring-stone-500/20"
                placeholder={t("roles.descriptionPlaceholder")}
              />
            </div>

            {/* 权限选择 */}
            <div>
              <label className="mb-2 block text-sm font-medium text-stone-700 dark:text-stone-300">
                {t("roles.permissions")}
              </label>
              <div className="space-y-3 rounded-xl border border-stone-200 bg-stone-50 p-4 mb-2 dark:border-stone-700 dark:bg-stone-800/50">
                {permissionGroups.map((group) => (
                  <div key={group.name} className="space-y-2">
                    {/* 组标题 */}
                    <label className="flex cursor-pointer items-center gap-2">
                      <input
                        type="checkbox"
                        checked={isGroupChecked(group.permissions)}
                        ref={(el) => {
                          if (el)
                            el.indeterminate = isGroupIndeterminate(
                              group.permissions,
                            );
                        }}
                        onChange={(e) =>
                          toggleGroup(group.permissions, e.target.checked)
                        }
                        className="h-4 w-4 rounded border-stone-300 text-stone-900 focus:ring-stone-500 dark:border-stone-600 dark:bg-stone-700 dark:text-stone-300 dark:focus:ring-stone-500"
                      />
                      <span className="text-sm font-medium text-stone-700 dark:text-stone-300">
                        {group.name}
                      </span>
                    </label>
                    {/* 组内权限 */}
                    <div className="ml-6 space-y-1">
                      {group.permissions.map((permission) => (
                        <label
                          key={permission.value}
                          className="flex cursor-pointer items-center gap-2"
                        >
                          <input
                            type="checkbox"
                            checked={selectedPermissions.includes(
                              permission.value,
                            )}
                            onChange={() => togglePermission(permission.value)}
                            className="h-4 w-4 rounded border-stone-300 text-stone-900 focus:ring-stone-500 dark:border-stone-600 dark:bg-stone-700 dark:text-stone-300 dark:focus:ring-stone-500"
                          />
                          <span className="text-sm text-stone-600 dark:text-stone-400">
                            {permissionLabels[permission.value] ||
                              permission.label}
                          </span>
                          <code className="rounded bg-stone-200 px-1 text-xs text-stone-500 dark:bg-stone-700 dark:text-stone-400">
                            {permission.value}
                          </code>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 按钮 */}
            <div className="flex gap-3 pt-2">
              <button
                type="button"
                onClick={onClose}
                className="btn-secondary flex-1"
              >
                {t("common.cancel")}
              </button>
              <button
                type="submit"
                disabled={isLoading}
                className="btn-primary flex-1 disabled:opacity-50"
              >
                {isLoading ? t("roles.saving") : t("common.save")}
              </button>
            </div>
          </form>
        </div>
      </div>
    </>
  );
}

// 删除确认模态框 - 底部弹出式设计
interface DeleteConfirmModalProps {
  roleName: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
  isLoading: boolean;
}

function DeleteConfirmModal({
  roleName,
  onConfirm,
  onClose,
  isLoading,
}: DeleteConfirmModalProps) {
  const { t } = useTranslation();
  return (
    <>
      <div className="fixed inset-0 z-40 sm:hidden" onClick={onClose} />
      <div
        className="modal-bottom-sheet"
        onClick={(e) => {
          if (e.target === e.currentTarget) onClose();
        }}
      >
        <div className="modal-bottom-sheet-content">
          <div className="bottom-sheet-handle sm:hidden" />
          {/* Header */}
          <div className="flex items-center justify-between border-b border-stone-200 px-6 py-4 dark:border-stone-800">
            <h2 className="text-lg font-semibold text-stone-900 dark:text-stone-100">
              {t("roles.confirmDelete")}
            </h2>
            <button onClick={onClose} className="btn-icon">
              <X size={20} />
            </button>
          </div>
          {/* Content */}
          <div className="px-6 py-4">
            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/30">
              <AlertCircle
                size={24}
                className="text-red-600 dark:text-red-400"
              />
            </div>
            <p className="mb-6 text-sm text-stone-500 dark:text-stone-400">
              {t("roles.confirmDeleteMessage", { roleName })}
            </p>
            <div className="flex gap-3">
              <button onClick={onClose} className="btn-secondary flex-1">
                {t("common.cancel")}
              </button>
              <button
                onClick={onConfirm}
                disabled={isLoading}
                className="flex-1 rounded-lg bg-red-600 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {isLoading ? t("roles.deleting") : t("common.delete")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

// 主组件
export function RolesPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [roles, setRoles] = useState<Role[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // 权限数据
  const [permissionGroups, setPermissionGroups] = useState<PermissionGroup[]>(
    [],
  );
  const [permissionLabels, setPermissionLabels] = useState<
    Record<string, string>
  >({});

  // 模态框状态
  const [showFormModal, setShowFormModal] = useState(false);
  const [editingRole, setEditingRole] = useState<Role | null>(null);
  const [deleteRole, setDeleteRole] = useState<Role | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // 权限检查
  const canManage = hasPermission(Permission.ROLE_MANAGE);

  // 加载权限数据
  const loadPermissions = useCallback(async () => {
    try {
      const response = await authApi.getPermissions();
      setPermissionGroups(response.groups);

      // 构建权限标签映射
      const labels: Record<string, string> = {};
      response.all_permissions.forEach((p) => {
        labels[p.value] = p.label;
      });
      setPermissionLabels(labels);
    } catch (err) {
      console.error("Failed to load permissions:", err);
    }
  }, []);

  // 加载数据
  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await roleApi.list();
      setRoles(data);
    } catch (err) {
      const errorMsg = (err as Error).message || t("roles.loadFailed");
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setIsLoading(false);
    }
  }, [t]);

  useEffect(() => {
    loadPermissions();
    loadData();
  }, [loadPermissions, loadData]);

  // 保存角色
  const handleSaveRole = async (data: RoleCreate | RoleUpdate) => {
    setIsSaving(true);
    try {
      if (editingRole) {
        const updated = await roleApi.update(
          editingRole.id,
          data as RoleUpdate,
        );
        setRoles((prev) =>
          prev.map((r) => (r.id === editingRole.id ? updated : r)),
        );
        toast.success(t("roles.updateSuccess"));
      } else {
        const created = await roleApi.create(data as RoleCreate);
        setRoles((prev) => [...prev, created]);
        toast.success(t("roles.createSuccess"));
      }
      setShowFormModal(false);
      setEditingRole(null);
    } catch (error) {
      toast.error((error as Error).message || t("roles.operationFailed"));
    } finally {
      setIsSaving(false);
    }
  };

  // 删除角色
  const handleDeleteRole = async () => {
    if (!deleteRole) return;
    setIsSaving(true);
    try {
      await roleApi.delete(deleteRole.id);
      setRoles((prev) => prev.filter((r) => r.id !== deleteRole.id));
      setDeleteRole(null);
      toast.success(t("roles.deleteSuccess"));
    } catch (error) {
      toast.error((error as Error).message || t("roles.deleteFailed"));
    } finally {
      setIsSaving(false);
    }
  };

  // 过滤角色
  const filteredRoles = roles.filter((r) =>
    r.name.toLowerCase().includes(searchQuery.toLowerCase()),
  );

  // 打开编辑模态框
  const openEditModal = (role: Role) => {
    setEditingRole(role);
    setShowFormModal(true);
  };

  // 打开创建模态框
  const openCreateModal = () => {
    setEditingRole(null);
    setShowFormModal(true);
  };

  // 关闭模态框
  const closeFormModal = () => {
    setShowFormModal(false);
    setEditingRole(null);
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-4 border-stone-400 border-t-transparent dark:border-stone-500"></div>
          <p className="text-stone-500 dark:text-stone-400">
            {t("common.loading")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col min-h-0">
      {/* 头部 */}
      <div className="panel-header">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-xl font-semibold text-stone-900 dark:text-stone-100">
              {t("roles.title")}
            </h1>
            <p className="mt-1 text-sm text-stone-500 dark:text-stone-400">
              {t("roles.subtitle")}
            </p>
          </div>
          {canManage && (
            <button onClick={openCreateModal} className="btn-primary">
              <Plus size={18} />
              {t("roles.createRole")}
            </button>
          )}
        </div>

        {/* 搜索 */}
        <div className="relative mt-3">
          <Search
            size={18}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400 dark:text-stone-500"
          />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="panel-search"
            placeholder={t("roles.searchPlaceholder")}
          />
        </div>
      </div>

      {/* 错误提示 */}
      {error && (
        <div className="mx-4 mt-4 flex items-center gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400 sm:mx-6">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* 角色列表 */}
      <div className="flex-1 overflow-y-auto p-3 sm:p-6">
        {filteredRoles.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <Shield
              size={48}
              className="mb-4 text-stone-300 dark:text-stone-600"
            />
            <p className="text-stone-500 dark:text-stone-400">
              {searchQuery ? t("roles.noMatchingRoles") : t("roles.noRoles")}
            </p>
          </div>
        ) : (
          <div className="grid gap-4">
            {filteredRoles.map((role) => (
              <div key={role.id} className="panel-card">
                <div className="flex items-start justify-between">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-100 dark:bg-purple-900/30">
                        <Lock
                          size={14}
                          className="text-purple-600 dark:text-purple-400"
                        />
                      </div>
                      <div>
                        <div className="flex items-center gap-2">
                          <h3 className="font-medium text-stone-900 dark:text-stone-100">
                            {role.name}
                          </h3>
                          {role.is_system && (
                            <span className="rounded bg-stone-100 px-1.5 py-0.5 text-xs text-stone-500 dark:bg-stone-700 dark:text-stone-400">
                              {t("roles.systemRole")}
                            </span>
                          )}
                        </div>
                        {role.description && (
                          <p className="text-sm text-stone-500 dark:text-stone-400">
                            {role.description}
                          </p>
                        )}
                      </div>
                    </div>

                    {/* 权限标签 */}
                    <div className="mt-3 flex flex-wrap gap-1">
                      {role.permissions.map((permission) => (
                        <span
                          key={permission}
                          className="rounded-full bg-stone-100 px-2 py-0.5 text-xs text-stone-600 dark:bg-stone-700 dark:text-stone-300"
                        >
                          {permissionLabels[permission] || permission}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* 操作按钮 */}
                  {canManage && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => openEditModal(role)}
                        className="btn-icon"
                        title={t("roles.edit")}
                      >
                        <Edit size={18} />
                      </button>
                      {!role.is_system && (
                        <button
                          onClick={() => setDeleteRole(role)}
                          className="btn-icon hover:bg-red-100 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                          title={t("common.delete")}
                        >
                          <Trash2 size={18} />
                        </button>
                      )}
                    </div>
                  )}
                </div>

                {/* 时间信息 */}
                <div className="mt-3 flex items-center gap-4 text-xs text-stone-400 dark:text-stone-500">
                  <span>
                    {t("roles.created")}:{" "}
                    {new Date(role.created_at).toLocaleDateString("zh-CN")}
                  </span>
                  <span>
                    {t("roles.updated")}:{" "}
                    {new Date(role.updated_at).toLocaleDateString("zh-CN")}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* 模态框 */}
      {showFormModal && (
        <RoleFormModal
          role={editingRole}
          onSave={handleSaveRole}
          onClose={closeFormModal}
          isLoading={isSaving}
          permissionGroups={permissionGroups}
          permissionLabels={permissionLabels}
        />
      )}

      {deleteRole && (
        <DeleteConfirmModal
          roleName={deleteRole.name}
          onConfirm={handleDeleteRole}
          onClose={() => setDeleteRole(null)}
          isLoading={isSaving}
        />
      )}
    </div>
  );
}

export default RolesPanel;
