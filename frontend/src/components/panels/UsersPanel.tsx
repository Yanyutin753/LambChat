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
  User,
  Mail,
  Lock,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { LoadingSpinner } from "../common/LoadingSpinner";
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
import { useSwipeToClose } from "../../hooks/useSwipeToClose";

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

// 用户表单模态框
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

  const swipeRef = useSwipeToClose({
    onClose,
    enabled: true,
  });

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
    <>
      <div
        className="fixed inset-0 z-[299] bg-black/50 sm:bg-transparent"
        onClick={onClose}
      />
      <div
        className="modal-bottom-sheet sm:modal-centered-wrapper"
        onClick={onClose}
      >
        <div
          ref={swipeRef as React.RefObject<HTMLDivElement>}
          className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-[72rem]"
        >
          <div className="bottom-sheet-handle sm:hidden" />
          {/* Header */}
          <div className="flex items-center justify-between glass-divider px-6 py-4">
            <h2 className="text-xl font-semibold text-stone-900 dark:text-stone-100 font-serif">
              {isEditing ? t("users.editUser") : t("users.createUser")}
            </h2>
            <button onClick={onClose} className="btn-icon">
              <X size={20} />
            </button>
          </div>

          {/* Content */}
          <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 space-y-2">
            <form onSubmit={handleSubmit} className="space-y-4">
              {error && (
                <div className="flex items-center gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400">
                  <AlertCircle size={18} />
                  <span>{error}</span>
                </div>
              )}

              {/* 用户名 */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-stone-700 dark:text-stone-300">
                  {t("users.username")}
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-stone-400 dark:text-stone-500">
                    <User size={18} />
                  </div>
                  <input
                    type="text"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="glass-input w-full rounded-xl py-2 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/20 dark:text-stone-100"
                    placeholder={t("users.usernamePlaceholder")}
                  />
                </div>
              </div>

              {/* 邮箱 */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-stone-700 dark:text-stone-300">
                  {t("users.email")}
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-stone-400 dark:text-stone-500">
                    <Mail size={18} />
                  </div>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="glass-input w-full rounded-xl py-2 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/20 dark:text-stone-100"
                    placeholder={t("users.emailPlaceholder")}
                  />
                </div>
              </div>

              {/* 密码 */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-stone-700 dark:text-stone-300">
                  {t("users.password")} {isEditing && t("users.passwordHint")}
                </label>
                <div className="relative">
                  <div className="pointer-events-none absolute inset-y-0 left-0 flex items-center pl-3 text-stone-400 dark:text-stone-500">
                    <Lock size={18} />
                  </div>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="glass-input w-full rounded-xl py-2 pl-10 pr-4 text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/20 dark:text-stone-100"
                    placeholder={
                      isEditing
                        ? t("users.passwordPlaceholderEdit")
                        : t("users.passwordPlaceholder")
                    }
                  />
                </div>
              </div>

              {/* 角色 */}
              <div>
                <label className="mb-1.5 block text-sm font-medium text-stone-700 dark:text-stone-300">
                  {t("users.roles")}
                </label>
                <div className="relative">
                  <div className="overflow-y-auto rounded-xl border border-[var(--glass-border)] bg-[var(--theme-bg-card)] py-2 pl-5 pr-4">
                    {roles.length === 0 ? (
                      <p className="text-sm text-stone-500 dark:text-stone-400">
                        {t("users.noRolesAvailable")}
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {roles.map((role) => (
                          <label
                            key={role.id}
                            className="flex cursor-pointer items-center gap-2"
                          >
                            <input
                              type="checkbox"
                              checked={selectedRoles.includes(role.name)}
                              onChange={() => toggleRole(role.name)}
                              className=""
                            />
                            <span className="text-sm text-stone-700 dark:text-stone-300">
                              {role.name}
                            </span>
                            {role.is_system && (
                              <span className="rounded bg-[var(--glass-bg-subtle)] px-1.5 py-0.5 text-xs text-stone-500 dark:text-stone-400">
                                {t("users.system")}
                              </span>
                            )}
                          </label>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              </div>

              {/* 状态 */}
              {isEditing && (
                <div>
                  <label className="flex cursor-pointer items-center gap-2">
                    <input
                      type="checkbox"
                      checked={isActive}
                      onChange={(e) => setIsActive(e.target.checked)}
                      className=""
                    />
                    <span className="text-sm text-stone-700 dark:text-stone-300">
                      {t("users.enableAccount")}
                    </span>
                  </label>
                </div>
              )}

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
                  {isLoading ? t("users.saving") : t("common.save")}
                </button>
              </div>
            </form>
          </div>
        </div>
      </div>
    </>
  );
}

// 删除确认模态框
interface DeleteConfirmModalProps {
  username: string;
  onConfirm: () => Promise<void>;
  onClose: () => void;
  isLoading: boolean;
}

function DeleteConfirmModal({
  username,
  onConfirm,
  onClose,
  isLoading,
}: DeleteConfirmModalProps) {
  const { t } = useTranslation();
  const swipeRef = useSwipeToClose({
    onClose,
    enabled: true,
  });
  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <div className="modal-bottom-sheet sm:modal-centered-wrapper">
        <div
          ref={swipeRef as React.RefObject<HTMLDivElement>}
          className="modal-bottom-sheet-content sm:modal-centered-content sm:max-w-[72rem]"
        >
          <div className="bottom-sheet-handle sm:hidden" />
          {/* Header */}
          <div className="flex items-center justify-between glass-divider px-6 py-4">
            <h2 className="text-xl font-semibold text-stone-900 dark:text-stone-100 font-serif">
              {t("users.confirmDelete")}
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
              {t("users.confirmDeleteMessage", { username })}
            </p>
            <div className="flex gap-3">
              <button onClick={onClose} className="btn-secondary flex-1">
                {t("common.cancel")}
              </button>
              <button
                onClick={onConfirm}
                disabled={isLoading}
                className="flex-1 rounded-xl bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
              >
                {isLoading ? t("users.deleting") : t("common.delete")}
              </button>
            </div>
          </div>
        </div>
      </div>
    </>
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
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <LoadingSpinner size="lg" className="mx-auto mb-4" />
          <p className="text-stone-500 dark:text-stone-400">
            {t("common.loading")}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      {/* 头部 */}
      <PanelHeader
        title={t("users.title")}
        subtitle={t("users.subtitle")}
        icon={
          <Users size={24} className="text-stone-600 dark:text-stone-400" />
        }
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
      <div className="flex-1 overflow-y-auto p-3 sm:p-6">
        {users.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <Users
              size={48}
              className="mb-4 text-stone-300 dark:text-stone-600"
            />
            <p className="text-stone-500 dark:text-stone-400">
              {debouncedSearch
                ? t("users.noMatchingUsers")
                : t("users.noUsers")}
            </p>
          </div>
        ) : (
          <>
            {/* Desktop table view */}
            <div className="hidden overflow-hidden glass-card rounded-xl sm:block">
              <table className="min-w-full divide-y divide-[var(--glass-border)]">
                <thead className="bg-[var(--glass-bg-subtle)]">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-stone-500 dark:text-stone-400">
                      {t("users.user")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-stone-500 dark:text-stone-400">
                      {t("users.email")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-stone-500 dark:text-stone-400">
                      {t("users.roles")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-stone-500 dark:text-stone-400">
                      {t("users.status")}
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium uppercase tracking-wider text-stone-500 dark:text-stone-400">
                      {t("users.createdAt")}
                    </th>
                    {(canEdit || canDelete) && (
                      <th className="px-6 py-3 text-right text-xs font-medium uppercase tracking-wider text-stone-500 dark:text-stone-400">
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
                          <span className="font-medium text-stone-900 dark:text-stone-100">
                            {user.username}
                          </span>
                        </div>
                      </td>
                      <td className="whitespace-nowrap px-6 py-4 text-sm text-stone-500 dark:text-stone-400">
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
                      <td className="whitespace-nowrap px-6 py-4 text-sm text-stone-500 dark:text-stone-400">
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
                      <p className="truncate font-medium text-stone-900 dark:text-stone-100">
                        {user.username}
                      </p>
                      <p className="truncate text-sm text-stone-500 dark:text-stone-400">
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
                      <span className="text-xs text-stone-400 dark:text-stone-500">
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

      {deleteUser && (
        <DeleteConfirmModal
          username={deleteUser.username}
          onConfirm={handleDeleteUser}
          onClose={() => setDeleteUser(null)}
          isLoading={isSaving}
        />
      )}
    </div>
  );
}

export default UsersPanel;
