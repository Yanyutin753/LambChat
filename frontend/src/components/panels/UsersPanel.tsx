/**
 * 用户管理页面组件
 */

import { useState, useEffect, useCallback } from "react";
import {
  Users,
  Plus,
  Edit,
  Trash2,
  X,
  AlertCircle,
  Check,
  Save,
  User,
  Mail,
  Lock,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { EditorSidebar } from "../common/EditorSidebar";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { Checkbox } from "../common/Checkbox";
import { UsersPanelSkeleton } from "../skeletons";
import { Pagination } from "../common/Pagination";
import { userApi, roleApi } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type {
  User as UserType,
  UserCreate,
  UserUpdate,
  Role,
} from "../../types";

// User avatar display component
interface UserAvatarProps {
  user: UserType;
  size?: "sm" | "md";
}

function UserAvatar({ user, size = "sm" }: UserAvatarProps) {
  const sizeClasses = size === "sm" ? "h-8 w-8 text-sm" : "h-10 w-10 text-base";
  const [imgError, setImgError] = useState(false);

  if (user.avatar_url && !imgError) {
    return (
      <img
        src={user.avatar_url}
        alt={user.username}
        className={`rounded-full object-cover ${sizeClasses}`}
        onError={() => setImgError(true)}
      />
    );
  }

  // Fallback to initial letter
  const initial = user.username.charAt(0).toUpperCase();
  return (
    <div
      className={`flex items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30 text-amber-600 dark:text-amber-400 font-medium ${sizeClasses}`}
    >
      {initial}
    </div>
  );
}

// Debounce hook for search
function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debouncedValue;
}

// 用户表单侧边栏
interface UserFormModalProps {
  user?: UserType | null;
  roles: Role[];
  onSave: (data: UserCreate | UserUpdate) => Promise<void>;
  onClose: () => void;
  isLoading: boolean;
}

function UserFormModal({
  user,
  roles,
  onSave,
  onClose,
  isLoading,
}: UserFormModalProps) {
  const { t } = useTranslation();
  const [username, setUsername] = useState(user?.username || "");
  const [email, setEmail] = useState(user?.email || "");
  const [password, setPassword] = useState("");
  const [selectedRoles, setSelectedRoles] = useState<string[]>(
    user?.roles || [],
  );
  const [isActive, setIsActive] = useState(user?.is_active ?? true);
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!user;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    // 验证
    if (!username.trim()) {
      setError(t("users.validation.enterUsername"));
      return;
    }
    if (!email.trim()) {
      setError(t("users.validation.enterEmail"));
      return;
    }
    if (!isEditing && !password) {
      setError(t("users.validation.enterPassword"));
      return;
    }
    if (!isEditing && password.length < 6) {
      setError(t("users.validation.passwordMinLength"));
      return;
    }

    try {
      if (isEditing) {
        const updateData: UserUpdate = {
          username: username.trim(),
          email: email.trim(),
          roles: selectedRoles,
          is_active: isActive,
        };
        if (password) {
          updateData.password = password;
        }
        await onSave(updateData);
      } else {
        const createData: UserCreate = {
          username: username.trim(),
          email: email.trim(),
          password,
          roles: selectedRoles,
        };
        await onSave(createData);
      }
      onClose();
    } catch (err) {
      setError((err as Error).message || t("users.operationFailed"));
    }
  };

  const toggleRole = (roleName: string) => {
    setSelectedRoles((prev) =>
      prev.includes(roleName)
        ? prev.filter((r) => r !== roleName)
        : [...prev, roleName],
    );
  };

  return (
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={isEditing ? t("users.editUser") : t("users.createUser")}
      subtitle={
        isEditing
          ? t("users.editUserDesc", "修改用户信息")
          : t("users.createUserDesc", "创建新用户账号")
      }
      icon={isEditing ? <Edit size={16} /> : <Plus size={16} />}
      width="wide"
      footer={
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onClose}
            className="btn-secondary flex-1"
          >
            {t("common.cancel")}
          </button>
          <button
            type="submit"
            form="user-form"
            disabled={isLoading}
            className="btn-primary flex-1 disabled:opacity-50"
          >
            {isLoading ? <LoadingSpinner size="sm" /> : <Save size={16} />}
            {t("common.save")}
          </button>
        </div>
      }
    >
      <form id="user-form" onSubmit={handleSubmit} className="es-form">
        {error && (
          <div className="es-error">
            <AlertCircle size={18} />
            <span>{error}</span>
          </div>
        )}

        {/* 用户名 */}
        <div className="es-field">
          <label className="es-label">{t("users.username")}</label>
          <div className="relative">
            <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-theme-text-secondary">
              <User size={16} />
            </div>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="glass-input es-input pl-10"
              placeholder={t("users.usernamePlaceholder")}
            />
          </div>
        </div>

        {/* 邮箱 */}
        <div className="es-field">
          <label className="es-label">{t("users.email")}</label>
          <div className="relative">
            <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-theme-text-secondary">
              <Mail size={16} />
            </div>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="glass-input es-input pl-10"
              placeholder={t("users.emailPlaceholder")}
            />
          </div>
        </div>

        {/* 密码 */}
        <div className="es-field">
          <label className="es-label">
            {t("users.password")} {isEditing && t("users.passwordHint")}
          </label>
          <div className="relative">
            <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-theme-text-secondary">
              <Lock size={16} />
            </div>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="glass-input es-input pl-10"
              placeholder={
                isEditing
                  ? t("users.passwordPlaceholderEdit")
                  : t("users.passwordPlaceholder")
              }
            />
          </div>
        </div>

        {/* 角色 */}
        <div className="es-field">
          <label className="es-label">{t("users.roles")}</label>
          <div className="es-section">
            {roles.length === 0 ? (
              <p className="es-hint">{t("users.noRolesAvailable")}</p>
            ) : (
              <div className="space-y-1">
                {roles.map((role) => (
                  <label
                    key={role.id}
                    className="group flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-[var(--theme-primary-light)]/40"
                  >
                    <Checkbox
                      size="sm"
                      checked={selectedRoles.includes(role.name)}
                      onChange={() => toggleRole(role.name)}
                    />
                    <span className="text-sm text-theme-text">{role.name}</span>
                    {role.is_system && (
                      <span className="es-chip">{t("users.system")}</span>
                    )}
                  </label>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* 状态 */}
        {isEditing && (
          <div className="es-field">
            <label className="group flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-[var(--theme-primary-light)]/40">
              <Checkbox
                size="sm"
                checked={isActive}
                onChange={() => setIsActive(!isActive)}
              />
              <span className="es-label">{t("users.enableAccount")}</span>
            </label>
          </div>
        )}
      </form>
    </EditorSidebar>
  );
}

// 主组件
export function UsersPanel() {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();
  const [users, setUsers] = useState<UserType[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Pagination state
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  // Debounced search
  const debouncedSearch = useDebounce(searchQuery, 300);

  // 模态框状态
  const [showFormModal, setShowFormModal] = useState(false);
  const [editingUser, setEditingUser] = useState<UserType | null>(null);
  const [deleteUser, setDeleteUser] = useState<UserType | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  // 权限检查
  const canCreate = hasPermission(Permission.USER_WRITE);
  const canEdit = hasPermission(Permission.USER_WRITE);
  const canDelete = hasPermission(Permission.USER_DELETE);

  // 加载数据
  const loadData = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const skip = (page - 1) * pageSize;
      const response = await userApi.list({
        skip,
        limit: pageSize,
        search: debouncedSearch || undefined,
      });
      setUsers(response.users);
      setTotal(response.total);
    } catch (err) {
      const errorMsg = (err as Error).message || t("users.loadFailed");
      setError(errorMsg);
      toast.error(errorMsg);
    }

    // 角色列表单独加载,失败不影响用户列表
    try {
      const rolesData = await roleApi.list();
      setRoles(rolesData);
    } catch (err) {
      console.error("Failed to load roles:", err);
      // 角色加载失败不显示错误,只是角色列表为空
    }

    setIsLoading(false);
  }, [page, debouncedSearch, t]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Reset to page 1 when search changes
  useEffect(() => {
    setPage(1);
  }, [debouncedSearch]);

  // 保存用户
  const handleSaveUser = async (data: UserCreate | UserUpdate) => {
    setIsSaving(true);
    try {
      if (editingUser) {
        await userApi.update(editingUser.id, data as UserUpdate);
        toast.success(t("users.updateSuccess"));
      } else {
        await userApi.create(data as UserCreate);
        toast.success(t("users.createSuccess"));
      }
      setShowFormModal(false);
      setEditingUser(null);
      loadData();
    } catch (error) {
      toast.error((error as Error).message || t("users.operationFailed"));
    } finally {
      setIsSaving(false);
    }
  };

  // 删除用户
  const handleDeleteUser = async () => {
    if (!deleteUser) return;
    setIsSaving(true);
    try {
      await userApi.delete(deleteUser.id);
      setDeleteUser(null);
      toast.success(t("users.deleteSuccess"));
      loadData();
    } catch (error) {
      toast.error((error as Error).message || t("users.deleteFailed"));
    } finally {
      setIsSaving(false);
    }
  };

  // 打开编辑模态框
  const openEditModal = (user: UserType) => {
    setEditingUser(user);
    setShowFormModal(true);
  };

  // 打开创建模态框
  const openCreateModal = () => {
    setEditingUser(null);
    setShowFormModal(true);
  };

  // 关闭模态框
  const closeFormModal = () => {
    setShowFormModal(false);
    setEditingUser(null);
  };

  if (isLoading) {
    return <UsersPanelSkeleton />;
  }

  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      {/* 头部 */}
      <PanelHeader
        title={t("users.title")}
        subtitle={t("users.subtitle")}
        icon={<Users size={24} className="text-theme-text-secondary" />}
        searchValue={searchQuery}
        onSearchChange={setSearchQuery}
        searchPlaceholder={t("users.searchPlaceholder")}
        actions={
          canCreate && (
            <button onClick={openCreateModal} className="btn-primary">
              <Plus size={16} className="sm:size-[18px]" />
              <span className="hidden sm:inline">{t("users.createUser")}</span>
            </button>
          )
        }
      />

      {/* 错误提示 */}
      {error && (
        <div className="mx-3 mt-4 flex items-center gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400 sm:mx-6">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* 用户列表 */}
      <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4">
        {users.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <Users
              size={48}
              className="mb-4 text-theme-text-secondary opacity-40"
            />
            <p className="text-theme-text-secondary">
              {debouncedSearch
                ? t("users.noMatchingUsers")
                : t("users.noUsers")}
            </p>
          </div>
        ) : (
          <>
            {/* Desktop table view */}
            <div className="hidden overflow-x-auto glass-card rounded-xl sm:block">
              <table className="min-w-full divide-y divide-[var(--glass-border)]">
                <thead className="bg-[var(--glass-bg-subtle)]">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-theme-text-secondary">
                      {t("users.user")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-theme-text-secondary">
                      {t("users.email")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-theme-text-secondary">
                      {t("users.roles")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-theme-text-secondary">
                      {t("users.status")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-theme-text-secondary">
                      {t("users.createdAt")}
                    </th>
                    {(canEdit || canDelete) && (
                      <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-theme-text-secondary">
                        {t("users.actions")}
                      </th>
                    )}
                  </tr>
                </thead>
                <tbody className="divide-y divide-[var(--glass-border)]">
                  {users.map((user) => (
                    <tr
                      key={user.id}
                      className="hover:bg-[var(--glass-bg-subtle)]"
                    >
                      <td className="whitespace-nowrap px-6 py-4">
                        <div className="flex items-center gap-3">
                          <UserAvatar user={user} />
                          <span className="font-medium text-theme-text">
                            {user.username}
                          </span>
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm text-theme-text-secondary">
                        {user.email}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4">
                        <div className="flex flex-wrap gap-1">
                          {user.roles.map((roleName: string) => {
                            const role = roles.find((r) => r.name === roleName);
                            return (
                              <span key={roleName} className="tag tag-default">
                                {role ? role.name : roleName}
                              </span>
                            );
                          })}
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-6 py-4">
                        {user.is_active ? (
                          <span className="tag tag-success">
                            <Check size={12} />
                            {t("users.enabled")}
                          </span>
                        ) : (
                          <span className="tag tag-error">
                            <X size={12} />
                            {t("users.disabled")}
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm text-theme-text-secondary">
                        {new Date(user.created_at).toLocaleDateString("zh-CN")}
                      </td>
                      {(canEdit || canDelete) && (
                        <td className="whitespace-nowrap px-6 py-4 text-right">
                          <div className="flex items-center justify-end gap-2">
                            {canEdit && (
                              <button
                                onClick={() => openEditModal(user)}
                                className="btn-icon"
                                title={t("users.edit")}
                              >
                                <Edit size={18} />
                              </button>
                            )}
                            {canDelete && (
                              <button
                                onClick={() => setDeleteUser(user)}
                                className="btn-icon hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                                title={t("common.delete")}
                              >
                                <Trash2 size={18} />
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Mobile card view */}
            <div className="space-y-3 sm:hidden">
              {users.map((user) => (
                <div key={user.id} className="panel-card">
                  {/* User info: avatar, username, email */}
                  <div className="flex items-start gap-3">
                    <UserAvatar user={user} size="md" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-medium text-theme-text">
                        {user.username}
                      </p>
                      <p className="truncate text-sm text-theme-text-secondary">
                        {user.email}
                      </p>
                    </div>
                  </div>

                  {/* Roles tags */}
                  <div className="mt-3 flex flex-wrap gap-1">
                    {user.roles.map((roleName: string) => (
                      <span key={roleName} className="tag tag-default">
                        {roles.find((r) => r.name === roleName)?.name ||
                          roleName}
                      </span>
                    ))}
                  </div>

                  {/* Status and date */}
                  <div className="mt-3 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      {user.is_active ? (
                        <span className="tag tag-success">
                          <Check size={12} />
                          {t("users.enabled")}
                        </span>
                      ) : (
                        <span className="tag tag-error">
                          <X size={12} />
                          {t("users.disabled")}
                        </span>
                      )}
                      <span className="text-xs text-theme-text-secondary opacity-60">
                        {new Date(user.created_at).toLocaleDateString("zh-CN")}
                      </span>
                    </div>

                    {/* Edit/Delete buttons */}
                    {(canEdit || canDelete) && (
                      <div className="flex items-center gap-1">
                        {canEdit && (
                          <button
                            onClick={() => openEditModal(user)}
                            className="btn-icon"
                            title={t("users.edit")}
                          >
                            <Edit size={18} />
                          </button>
                        )}
                        {canDelete && (
                          <button
                            onClick={() => setDeleteUser(user)}
                            className="btn-icon hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                            title={t("common.delete")}
                          >
                            <Trash2 size={18} />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Pagination */}
      {total > pageSize && (
        <div className="glass-divider px-3 py-3 sm:px-6">
          <Pagination
            page={page}
            pageSize={pageSize}
            total={total}
            onChange={setPage}
          />
        </div>
      )}

      {/* 模态框 */}
      {showFormModal && (
        <UserFormModal
          user={editingUser}
          roles={roles}
          onSave={handleSaveUser}
          onClose={closeFormModal}
          isLoading={isSaving}
        />
      )}

      <ConfirmDialog
        isOpen={!!deleteUser}
        title={t("users.confirmDelete")}
        message={t("users.confirmDeleteMessage", {
          username: deleteUser?.username,
        })}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        variant="danger"
        loading={isSaving}
        onConfirm={handleDeleteUser}
        onCancel={() => setDeleteUser(null)}
      />
    </div>
  );
}

export default UsersPanel;
