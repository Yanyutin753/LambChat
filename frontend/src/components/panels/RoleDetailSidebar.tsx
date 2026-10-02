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
        {role.is_system && (
          <p className="text-12 text-theme-text-secondary">
            {t("roles.systemRole")}
          </p>
        )}
        {/* 描述 */}
        {role.description && (
          <>
            <p className="text-14 text-theme-text-secondary leading-relaxed [overflow-wrap:anywhere]">
              {role.description}
            </p>
            <hr className="es-divider" />
          </>
        )}

        {/* 权限列表 */}
        <div className="es-field">
          <h3 className="es-label flex items-center gap-1.5">
            <Shield size={14} className="shrink-0 text-theme-text-secondary" />
            {t("roles.permissions")}
          </h3>
          <div className="es-section">
            {role.permissions.length === 0 && (
              <p className="text-13 text-theme-text-secondary">
                {t("roles.permissionCount", { count: 0 })}
              </p>
            )}
            {groupedPermissions.map((group) => (
              <div key={group.name}>
                <p className="text-12 font-medium text-theme-text-secondary mb-1.5">
                  {group.name}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {group.permissions.map((p) => (
                    <span
                      key={p.value}
                      className="es-chip max-w-full [overflow-wrap:anywhere]"
                    >
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
                    <span
                      key={p}
                      className="es-chip max-w-full [overflow-wrap:anywhere]"
                    >
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
              <h3 className="es-label flex items-center gap-1.5">
                <Lock
                  size={14}
                  className="shrink-0 text-theme-text-secondary"
                />
                {t("roles.uploadLimitsTitle")}
              </h3>
              <div className="es-section">
                <dl className="grid auto-grid-cols gap-x-4 gap-y-2">
                  {limitEntries.map(({ label, value }) => (
                    <div
                      key={label}
                      className="flex min-w-0 items-baseline justify-between gap-3 text-14"
                    >
                      <dt className="min-w-0 text-theme-text-secondary [overflow-wrap:anywhere]">
                        {label}
                      </dt>
                      <dd className="shrink-0 font-medium tabular-nums text-theme-text">
                        {value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </div>
            </div>
          </>
        )}

        {/* 时间信息 */}
        <hr className="es-divider" />
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-12 text-theme-text-secondary">
          <span className="flex min-w-0 items-center gap-1.5 [overflow-wrap:anywhere]">
            <Clock size={12} className="shrink-0" />
            <span>
              {t("roles.created")}: {formatDate(role.created_at)}
            </span>
          </span>
          <span className="min-w-0 [overflow-wrap:anywhere]">
            {t("roles.updated")}: {formatDate(role.updated_at)}
          </span>
        </div>
      </div>
    </EditorSidebar>
  );
}
