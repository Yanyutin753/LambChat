/**
 * 角色详情侧边栏 — 点击角色卡片后展示完整信息
 */

import { useTranslation } from "react-i18next";
import { Eye, Trash2, Pencil, Clock, Shield, Lock } from "lucide-react";
import { EditorSidebar } from "../common/EditorSidebar";
import { Button, PanelFooterActions } from "../common";
import { useAuth } from "../../hooks/useAuth";
import { formatDate } from "../../utils/datetime";
import { Permission } from "../../types";
import type { Role, PermissionGroup } from "../../types";

interface RoleDetailSidebarProps {
  role: Role;
  permissionGroups: PermissionGroup[];
  permissionLabels: Record<string, string>;
  onClose: () => void;
  onEdit: (role: Role) => void;
  onDelete: (role: Role) => void;
}

export function RoleDetailSidebar({
  role,
  permissionGroups,
  permissionLabels,
  onClose,
  onEdit,
  onDelete,
}: RoleDetailSidebarProps) {
  const { t } = useTranslation();
  const { hasPermission } = useAuth();

  const canManage = hasPermission(Permission.ROLE_MANAGE);

  // 将角色权限按分组归类
  const groupedPermissions = permissionGroups
    .map((group) => ({
      name: group.name,
      permissions: group.permissions.filter((p) =>
        role.permissions.includes(p.value as Permission),
      ),
    }))
    .filter((g) => g.permissions.length > 0);

  // 收集未被分组的权限
  const groupedValues = new Set(
    permissionGroups.flatMap((g) => g.permissions.map((p) => p.value)),
  );
  const ungroupedPermissions = role.permissions.filter(
    (p) => !groupedValues.has(p),
  );

  // 限额条目（仅显示有值的）
  const limitEntries: { label: string; value: string }[] = [];
  if (role.limits) {
    const map: Record<string, string> = {
      max_channels: t("roles.maxChannels"),
      max_concurrent_chats: t("roles.maxConcurrentChats"),
      max_queued_chats: t("roles.maxQueuedChats"),
      max_file_size_image: t("roles.maxUploadSizeImage"),
      max_file_size_video: t("roles.maxUploadSizeVideo"),
      max_file_size_audio: t("roles.maxUploadSizeAudio"),
      max_file_size_document: t("roles.maxUploadSizeDocument"),
      max_files: t("roles.maxFiles"),
    };
    for (const [key, label] of Object.entries(map)) {
      const val = role.limits[key];
      if (val != null) {
        limitEntries.push({ label, value: String(val) });
      }
    }
  }

  return (
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={role.name}
      subtitle={role.is_system ? t("roles.systemRole") : undefined}
      icon={<Eye size={16} />}
      footer={
        <PanelFooterActions align="between">
          {canManage && !role.is_system && (
            <Button
              variant="danger"
              onClick={() => onDelete(role)}
              leftIcon={<Trash2 size={16} />}
            >
              {t("common.delete")}
            </Button>
          )}
          {canManage && !role.is_system && (
            <span className="panel-footer-actions__spacer" />
          )}
          {canManage && (
            <Button
              onClick={() => onEdit(role)}
              leftIcon={<Pencil size={14} />}
            >
              {t("common.edit")}
            </Button>
          )}
          <Button onClick={onClose}>{t("common.close")}</Button>
        </PanelFooterActions>
      }
    >
      <div className="es-form">
        {/* 描述 */}
        {role.description && (
          <>
            <p className="text-sm text-theme-text-secondary leading-relaxed">
              {role.description}
            </p>
            <hr className="es-divider" />
          </>
        )}

        {/* 权限列表 */}
        <div className="es-field">
          <label className="es-label flex items-center gap-1.5">
            <Shield size={14} className="text-theme-text-secondary" />
            {t("roles.permissions")}
          </label>
          <div className="es-section space-y-3">
            {groupedPermissions.map((group) => (
              <div key={group.name}>
                <p className="text-xs font-medium text-theme-text-secondary mb-1.5">
                  {group.name}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {group.permissions.map((p) => (
                    <span key={p.value} className="es-chip">
                      {permissionLabels[p.value] || p.label}
                    </span>
                  ))}
                </div>
              </div>
            ))}
            {ungroupedPermissions.length > 0 && (
              <div>
                <div className="flex flex-wrap gap-1.5">
                  {ungroupedPermissions.map((p) => (
                    <span key={p} className="es-chip">
                      {permissionLabels[p] || p}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 限额信息 */}
        {limitEntries.length > 0 && (
          <>
            <hr className="es-divider" />
            <div className="es-field">
              <label className="es-label flex items-center gap-1.5">
                <Lock size={14} className="text-theme-text-secondary" />
                {t("roles.uploadLimitsTitle")}
              </label>
              <div className="es-section">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-2">
                  {limitEntries.map(({ label, value }) => (
                    <div
                      key={label}
                      className="flex items-center justify-between text-sm"
                    >
                      <span className="text-theme-text-secondary">{label}</span>
                      <span className="font-medium text-theme-text">
                        {value}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </>
        )}

        {/* 时间信息 */}
        <hr className="es-divider" />
        <div className="flex items-center gap-1.5 text-xs text-theme-text-secondary">
          <Clock size={12} />
          <span>
            {t("roles.created")}: {formatDate(role.created_at)}
          </span>
          <span className="mx-1">·</span>
          <span>
            {t("roles.updated")}: {formatDate(role.updated_at)}
          </span>
        </div>
      </div>
    </EditorSidebar>
  );
}
