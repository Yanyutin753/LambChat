/**
 * 角色管理页面组件
 */

import { useState, useEffect, useCallback, useRef } from "react";
import {
  Shield,
  Plus,
  Edit,
  Save,
  AlertCircle,
  ShieldCheck,
  ChevronDown,
  Pencil,
  Trash2,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import { PanelHeader } from "../common/PanelHeader";
import { RoleDetailSidebar } from "./RoleDetailSidebar";
import { RolesPanelSkeleton } from "../skeletons";
import { Pagination } from "../common/Pagination";
import { EditorSidebar } from "../common/EditorSidebar";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { Checkbox } from "../common/Checkbox";
import {
  Button,
  IconButton,
  Input,
  PanelFooterActions,
  Textarea,
} from "../common";
import { roleApi, authApi } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type {
  Role,
  RoleCreate,
  RoleUpdate,
  RoleLimits,
  PermissionGroup,
  PermissionInfo,
} from "../../types";

// 角色表单模态框 - 使用 EditorSidebar
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
  const formRef = useRef<HTMLFormElement>(null);
  const [name, setName] = useState(role?.name || "");
  const [description, setDescription] = useState(role?.description || "");
  const [maxChannels, setMaxChannels] = useState<number | "">(
    role?.limits?.max_channels ?? "",
  );
  const [maxConcurrentChats, setMaxConcurrentChats] = useState<number | "">(
    role?.limits?.max_concurrent_chats ?? "",
  );
  const [maxQueuedChats, setMaxQueuedChats] = useState<number | "">(
    role?.limits?.max_queued_chats ?? "",
  );
  const [maxUploadSizeImage, setMaxUploadSizeImage] = useState<number | "">(
    role?.limits?.max_file_size_image ?? "",
  );
  const [maxUploadSizeVideo, setMaxUploadSizeVideo] = useState<number | "">(
    role?.limits?.max_file_size_video ?? "",
  );
  const [maxUploadSizeAudio, setMaxUploadSizeAudio] = useState<number | "">(
    role?.limits?.max_file_size_audio ?? "",
  );
  const [maxUploadSizeDocument, setMaxUploadSizeDocument] = useState<
    number | ""
  >(role?.limits?.max_file_size_document ?? "");
  const [maxUploadFiles, setMaxUploadFiles] = useState<number | "">(
    role?.limits?.max_files ?? "",
  );
  const [showUploadLimits, setShowUploadLimits] = useState(false);
  const [selectedPermissions, setSelectedPermissions] = useState<string[]>(
    role?.permissions || [],
  );
  const [error, setError] = useState<string | null>(null);

  const isEditing = !!role;
  const isSystem = role?.is_system || false;

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
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
      const limits: RoleLimits = {};
      if (
        maxChannels !== "" &&
        maxChannels !== null &&
        maxChannels !== undefined
      ) {
        const numValue = Number(maxChannels);
        if (!isNaN(numValue) && numValue >= 0) {
          limits.max_channels = numValue;
        }
      }
      if (
        maxConcurrentChats !== "" &&
        maxConcurrentChats !== null &&
        maxConcurrentChats !== undefined
      ) {
        const numValue = Number(maxConcurrentChats);
        if (!isNaN(numValue) && numValue >= 0) {
          limits.max_concurrent_chats = numValue;
        }
      }
      if (
        maxQueuedChats !== "" &&
        maxQueuedChats !== null &&
        maxQueuedChats !== undefined
      ) {
        const numValue = Number(maxQueuedChats);
        if (!isNaN(numValue) && numValue >= 0) {
          limits.max_queued_chats = numValue;
        }
      }
      if (
        maxUploadSizeImage !== "" &&
        maxUploadSizeImage !== null &&
        maxUploadSizeImage !== undefined
      ) {
        const numValue = Number(maxUploadSizeImage);
        if (!isNaN(numValue) && numValue >= 0) {
          limits.max_file_size_image = numValue;
        }
      }
      if (
        maxUploadSizeVideo !== "" &&
        maxUploadSizeVideo !== null &&
        maxUploadSizeVideo !== undefined
      ) {
        const numValue = Number(maxUploadSizeVideo);
        if (!isNaN(numValue) && numValue >= 0) {
          limits.max_file_size_video = numValue;
        }
      }
      if (
        maxUploadSizeAudio !== "" &&
        maxUploadSizeAudio !== null &&
        maxUploadSizeAudio !== undefined
      ) {
        const numValue = Number(maxUploadSizeAudio);
        if (!isNaN(numValue) && numValue >= 0) {
          limits.max_file_size_audio = numValue;
        }
      }
      if (
        maxUploadSizeDocument !== "" &&
        maxUploadSizeDocument !== null &&
        maxUploadSizeDocument !== undefined
      ) {
        const numValue = Number(maxUploadSizeDocument);
        if (!isNaN(numValue) && numValue >= 0) {
          limits.max_file_size_document = numValue;
        }
      }
      if (
        maxUploadFiles !== "" &&
        maxUploadFiles !== null &&
        maxUploadFiles !== undefined
      ) {
        const numValue = Number(maxUploadFiles);
        if (!isNaN(numValue) && numValue >= 0) {
          limits.max_files = numValue;
        }
      }
      const data: RoleCreate | RoleUpdate = {
        name: name.trim(),
        description: description.trim() || undefined,
        permissions: selectedPermissions as Permission[],
        limits: Object.keys(limits).length > 0 ? limits : undefined,
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

  return (
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={isEditing ? t("roles.editRole") : t("roles.createRole")}
      icon={isEditing ? <Edit size={16} /> : <Plus size={16} />}
      width="wide"
      footer={
        <PanelFooterActions>
          <Button type="button" onClick={onClose} className="flex-1">
            {t("common.cancel")}
          </Button>
          <Button
            variant="primary"
            type="button"
            onClick={() => handleSubmit()}
            loading={isLoading}
            leftIcon={<Save size={16} />}
            className="flex-1"
          >
            {t("common.save")}
          </Button>
        </PanelFooterActions>
      }
    >
      {isSystem && (
        <div className="es-callout">
          <div className="es-callout-icon">
            <AlertCircle size={14} />
          </div>
          <span
            className="text-sm"
            style={{ color: "var(--theme-text-secondary)" }}
          >
            {t("roles.systemRoleHint")}
          </span>
        </div>
      )}

      <form ref={formRef} onSubmit={handleSubmit} className="es-form">
        {error && (
          <div className="es-error">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {/* 角色名称 */}
        <div className="es-field">
          <label className="es-label">{t("roles.roleName")}</label>
          <Input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={isSystem}
            className="es-input px-3"
            placeholder={t("roles.roleNamePlaceholder")}
          />
        </div>

        {/* 描述 */}
        <div className="es-field">
          <label className="es-label">{t("roles.description")}</label>
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={2}
            className="es-textarea"
            placeholder={t("roles.descriptionPlaceholder")}
          />
        </div>

        {/* 最大渠道数量 */}
        <div className="es-field">
          <label className="es-label">{t("roles.maxChannels")}</label>
          <Input
            type="number"
            min="0"
            value={maxChannels}
            onChange={(e) =>
              setMaxChannels(
                e.target.value === "" ? "" : Number(e.target.value),
              )
            }
            className="es-input px-3"
            placeholder={t("roles.maxChannelsPlaceholder")}
          />
          <p className="es-hint">{t("roles.maxChannelsHint")}</p>
        </div>

        {/* 并发限制 */}
        <div className="es-section">
          <div className="es-section-title">
            {t("roles.concurrentChatsTitle")}
          </div>
          <div className="es-row es-row-2">
            <div className="es-field">
              <label className="es-label">
                {t("roles.maxConcurrentChats")}
              </label>
              <Input
                type="number"
                min="0"
                value={maxConcurrentChats}
                onChange={(e) =>
                  setMaxConcurrentChats(
                    e.target.value === "" ? "" : Number(e.target.value),
                  )
                }
                className="es-input px-3"
                placeholder="5"
              />
            </div>
            <div className="es-field">
              <label className="es-label">{t("roles.maxQueuedChats")}</label>
              <Input
                type="number"
                min="0"
                value={maxQueuedChats}
                onChange={(e) =>
                  setMaxQueuedChats(
                    e.target.value === "" ? "" : Number(e.target.value),
                  )
                }
                className="es-input px-3"
                placeholder="10"
              />
            </div>
          </div>
          <p className="es-hint">{t("roles.concurrentChatsHint")}</p>
        </div>

        {/* 上传限制 */}
        <div>
          <button
            type="button"
            onClick={() => setShowUploadLimits(!showUploadLimits)}
            className="es-section-title cursor-pointer w-full"
          >
            {t("roles.uploadLimitsTitle")}
            <ChevronDown
              size={14}
              className={`ml-auto transition-transform ${
                showUploadLimits ? "rotate-180" : ""
              }`}
            />
          </button>
          {showUploadLimits && (
            <div className="es-section mt-2">
              <p className="es-hint">{t("roles.uploadLimitsHint")}</p>
              {[
                {
                  label: "maxUploadSizeImage",
                  value: maxUploadSizeImage,
                  setter: setMaxUploadSizeImage,
                },
                {
                  label: "maxUploadSizeVideo",
                  value: maxUploadSizeVideo,
                  setter: setMaxUploadSizeVideo,
                },
                {
                  label: "maxUploadSizeAudio",
                  value: maxUploadSizeAudio,
                  setter: setMaxUploadSizeAudio,
                },
                {
                  label: "maxUploadSizeDocument",
                  value: maxUploadSizeDocument,
                  setter: setMaxUploadSizeDocument,
                },
                {
                  label: "maxFiles",
                  value: maxUploadFiles,
                  setter: setMaxUploadFiles,
                },
              ].map(({ label, value, setter }) => (
                <div key={label} className="es-field">
                  <label className="es-label">{t(`roles.${label}`)}</label>
                  <Input
                    type="number"
                    min="0"
                    value={value}
                    onChange={(e) =>
                      setter(
                        e.target.value === "" ? "" : Number(e.target.value),
                      )
                    }
                    className="es-input px-3"
                    placeholder={t("roles.maxChannelsPlaceholder")}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 权限选择 */}
        <div className="es-field">
          <label className="es-label">{t("roles.permissions")}</label>
          <div className="es-section">
            {permissionGroups.map((group) => (
              <div key={group.name} className="space-y-1.5">
                {/* 组标题 */}
                <label className="group flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-[var(--theme-bg-subtle)]">
                  <Checkbox
                    size="sm"
                    checked={isGroupChecked(group.permissions)}
                    onChange={() =>
                      toggleGroup(
                        group.permissions,
                        !isGroupChecked(group.permissions),
                      )
                    }
                  />
                  <span className="text-sm font-medium text-theme-text">
                    {group.name}
                  </span>
                </label>
                {/* 组内权限 */}
                <div className="ml-7 space-y-0.5">
                  {group.permissions.map((permission) => (
                    <label
                      key={permission.value}
                      className="group flex cursor-pointer items-center gap-2.5 rounded-lg px-2 py-1.5 transition-colors hover:bg-[var(--theme-bg-subtle)]"
                    >
                      <Checkbox
                        size="sm"
                        checked={selectedPermissions.includes(permission.value)}
                        onChange={() => togglePermission(permission.value)}
                      />
                      <span className="text-sm text-theme-text-secondary">
                        {permissionLabels[permission.value] || permission.label}
                      </span>
                      <code className="es-chip ml-auto">
                        {permission.value}
                      </code>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Hidden submit button so Enter key still works */}
        <button type="submit" className="hidden" />
      </form>
    </EditorSidebar>
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

  // Pagination state
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 20;

  const handleSearchQueryChange = useCallback((query: string) => {
    setPage(1);
    setSearchQuery(query);
  }, []);

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
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);

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
      const data = await roleApi.list({
        skip: (page - 1) * pageSize,
        limit: pageSize,
        q: searchQuery.trim() || undefined,
      });
      setRoles(data.roles);
      setTotal(data.total);
    } catch (err) {
      const errorMsg = (err as Error).message || t("roles.loadFailed");
      setError(errorMsg);
      toast.error(errorMsg);
    } finally {
      setIsLoading(false);
    }
  }, [page, pageSize, searchQuery, t]);

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
        await roleApi.create(data as RoleCreate);
        await loadData();
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
      await loadData();
      setDeleteRole(null);
      toast.success(t("roles.deleteSuccess"));
    } catch (error) {
      toast.error((error as Error).message || t("roles.deleteFailed"));
    } finally {
      setIsSaving(false);
    }
  };

  const filteredRoles = roles;
  const paginatedRoles = roles;

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

  const isInitialLoading =
    isLoading && roles.length === 0 && searchQuery.trim().length === 0;

  if (isInitialLoading) {
    return <RolesPanelSkeleton />;
  }

  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      {/* 头部 */}
      <PanelHeader
        title={t("roles.title")}
        subtitle={t("roles.subtitle")}
        icon={<Shield size={24} className="text-theme-text-secondary" />}
        searchValue={searchQuery}
        onSearchChange={handleSearchQueryChange}
        searchPlaceholder={t("roles.searchPlaceholder")}
        actions={
          canManage && (
            <Button
              variant="primary"
              onClick={openCreateModal}
              leftIcon={<Plus size={16} className="sm:size-[18px]" />}
            >
              <span className="hidden sm:inline">{t("roles.createRole")}</span>
            </Button>
          )
        }
      />

      {/* 错误提示 */}
      {error && (
        <div className="mx-4 mt-4 flex items-center gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/30 dark:text-red-400 sm:mx-6">
          <AlertCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      {/* 角色列表 */}
      <div className="flex-1 overflow-y-auto py-2 sm:py-4 px-4">
        {filteredRoles.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <Shield
              size={48}
              className="mb-4 text-theme-text-secondary opacity-40"
            />
            <p className="text-theme-text-secondary">
              {searchQuery ? t("roles.noMatchingRoles") : t("roles.noRoles")}
            </p>
          </div>
        ) : (
          <div className="grid gap-3 auto-grid-cols">
            {paginatedRoles.map((role) => (
              <div
                key={role.id}
                className="glass-card group relative flex flex-col rounded-xl p-4 sm:p-5 cursor-pointer transition-all duration-200 animate-glass-enter"
                onClick={() => setSelectedRole(role)}
              >
                {/* Header badges */}
                <div className="flex flex-wrap items-center gap-2 mb-2">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium ${
                      role.is_system
                        ? "bg-[var(--theme-primary)]/10 text-[var(--theme-primary)]"
                        : "bg-[var(--glass-bg-subtle)] text-[var(--theme-text-secondary)]"
                    }`}
                  >
                    <ShieldCheck size={11} />
                    {role.is_system
                      ? t("roles.systemRole")
                      : t("roles.customRole")}
                  </span>
                  <span className="text-[11px] text-[var(--theme-text-secondary)]">
                    {t("roles.permissionCount", {
                      count: role.permissions.length,
                    })}
                  </span>
                </div>

                {/* Title & description */}
                <h4 className="truncate text-base font-semibold text-[var(--theme-text)]">
                  {role.name}
                </h4>
                {role.description && (
                  <p className="mt-1 text-sm leading-relaxed text-[var(--theme-text-secondary)] line-clamp-2">
                    {role.description}
                  </p>
                )}

                {/* Permissions preview */}
                <div className="mt-3 mb-2 flex flex-wrap gap-1.5">
                  {role.permissions.slice(0, 3).map((perm) => (
                    <span
                      key={perm}
                      className="inline-flex items-center rounded-md bg-[var(--glass-bg-subtle)] px-2 py-0.5 text-[11px] text-[var(--theme-text-secondary)]"
                    >
                      {permissionLabels[perm] || perm}
                    </span>
                  ))}
                  {role.permissions.length > 3 && (
                    <span className="inline-flex items-center rounded-md bg-[var(--glass-bg-subtle)] px-2 py-0.5 text-[11px] text-[var(--theme-text-secondary)]">
                      +{role.permissions.length - 3}
                    </span>
                  )}
                </div>

                {/* Footer actions */}
                {canManage && (
                  <div className="mt-auto flex items-center gap-2 border-t border-[var(--glass-border)] pt-3 mt-3.5">
                    <div className="ml-auto" />
                    <IconButton
                      aria-label={t("common.edit")}
                      icon={<Pencil size={14} />}
                      onClick={(e) => {
                        e.stopPropagation();
                        openEditModal(role);
                      }}
                      size="sm"
                      className="h-8 w-8 rounded-lg text-[var(--theme-text-secondary)] hover:bg-blue-50 hover:text-blue-600 dark:hover:bg-blue-900/30 dark:hover:text-blue-400"
                      title={t("common.edit")}
                    />
                    {!role.is_system && (
                      <IconButton
                        aria-label={t("common.delete")}
                        icon={<Trash2 size={14} />}
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteRole(role);
                        }}
                        size="sm"
                        className="h-8 w-8 rounded-lg text-[var(--theme-text-secondary)] hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                        title={t("common.delete")}
                      />
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > pageSize && (
        <div className="glass-divider px-3 py-3 sm:px-4">
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
        <RoleFormModal
          role={editingRole}
          onSave={handleSaveRole}
          onClose={closeFormModal}
          isLoading={isSaving}
          permissionGroups={permissionGroups}
          permissionLabels={permissionLabels}
        />
      )}

      <ConfirmDialog
        isOpen={!!deleteRole}
        title={t("roles.confirmDelete")}
        message={t("roles.confirmDeleteMessage", {
          roleName: deleteRole?.name,
        })}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        variant="danger"
        loading={isSaving}
        onConfirm={handleDeleteRole}
        onCancel={() => setDeleteRole(null)}
      />

      {/* 详情侧边栏 */}
      {selectedRole && (
        <RoleDetailSidebar
          role={selectedRole}
          permissionGroups={permissionGroups}
          permissionLabels={permissionLabels}
          onClose={() => setSelectedRole(null)}
          onEdit={(role) => {
            setSelectedRole(null);
            openEditModal(role);
          }}
          onDelete={(role) => setDeleteRole(role)}
        />
      )}
    </div>
  );
}

export default RolesPanel;
