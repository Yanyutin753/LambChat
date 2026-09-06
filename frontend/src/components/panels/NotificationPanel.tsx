/**
 * 通知管理面板 - Admin CRUD panel for notifications
 */

import { useState, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import toast from "react-hot-toast";
import {
  Plus,
  Pencil,
  Trash2,
  Bell,
  AlertCircle,
  ChevronDown,
  Save,
} from "lucide-react";
import { PanelHeader } from "../common/PanelHeader";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { PanelLoadingState } from "../common/PanelLoadingState";
import { Pagination } from "../common/Pagination";
import { StatusBadge } from "../common/StatusBadge";
import type { StatusColor } from "../common/StatusBadge";
import {
  Button,
  IconButton,
  Input,
  PanelFooterActions,
  Textarea,
} from "../common";
import { EditorSidebar } from "../common/EditorSidebar";
import { ToggleSwitch } from "./AgentPanel/shared";
import { notificationApi } from "../../services/api/notification";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import type {
  Notification,
  NotificationCreate,
} from "../../types/notification";
import type { I18nText } from "../../types/notification";
import { formatDateTimeShort, parseDate } from "../../utils/datetime";

const LOCALE_KEYS: Array<{ key: keyof I18nText; label: string }> = [
  { key: "en", label: "English" },
  { key: "zh", label: "中文" },
  { key: "ja", label: "日本語" },
  { key: "ko", label: "한국어" },
  { key: "ru", label: "Русский" },
];

const emptyI18n: I18nText = { en: "", zh: "", ja: "", ko: "", ru: "" };

/** Convert ISO datetime string to datetime-local input value (YYYY-MM-DDTHH:mm) */
function toDatetimeLocal(value: string | null): string {
  if (!value) return "";
  const d = parseDate(value);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

/** Convert datetime-local input value to ISO string */
function fromDatetimeLocal(value: string): string | null {
  if (!value) return null;
  return new Date(value).toISOString();
}

/** Compute display status based on is_active and schedule */
function getNotificationStatus(
  notification: Notification,
): "active" | "inactive" | "scheduled" | "expired" {
  const now = Date.now();
  if (!notification.is_active) return "inactive";
  if (
    notification.end_time &&
    parseDate(notification.end_time).getTime() < now
  ) {
    return "expired";
  }
  if (
    notification.start_time &&
    parseDate(notification.start_time).getTime() > now
  ) {
    return "scheduled";
  }
  return "active";
}

const NOTIFICATION_STATUS_COLOR: Record<string, StatusColor> = {
  active: "emerald",
  inactive: "stone",
  scheduled: "blue",
  expired: "red",
};

/** Create/Edit modal */
function NotificationFormModal({
  notification,
  onSave,
  onClose,
}: {
  notification: Notification | null;
  onSave: (data: NotificationCreate) => Promise<void>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const isEdit = !!notification;

  const [titleI18n, setTitleI18n] = useState<I18nText>(
    notification?.title_i18n ?? { ...emptyI18n },
  );
  const [contentI18n, setContentI18n] = useState<I18nText>(
    notification?.content_i18n ?? { ...emptyI18n },
  );
  const [startTime, setStartTime] = useState(
    toDatetimeLocal(notification?.start_time ?? null),
  );
  const [endTime, setEndTime] = useState(
    toDatetimeLocal(notification?.end_time ?? null),
  );
  const [isActive, setIsActive] = useState(notification?.is_active ?? true);
  const [notifType, setNotifType] = useState<string>(
    notification?.type ?? "info",
  );
  const [isSaving, setIsSaving] = useState(false);

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const data: NotificationCreate = {
        title_i18n: titleI18n,
        content_i18n: contentI18n,
        type: notifType as NotificationCreate["type"],
        start_time: fromDatetimeLocal(startTime),
        end_time: fromDatetimeLocal(endTime),
        is_active: isActive,
      };
      await onSave(data);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <EditorSidebar
      open={true}
      onClose={onClose}
      title={isEdit ? t("notification.edit") : t("notification.create")}
      icon={isEdit ? <Pencil size={16} /> : <Plus size={16} />}
      footer={
        <PanelFooterActions>
          <Button onClick={onClose}>{t("common.cancel")}</Button>
          <Button
            variant="primary"
            onClick={handleSave}
            loading={isSaving}
            leftIcon={<Save size={16} />}
          >
            {t("common.save")}
          </Button>
        </PanelFooterActions>
      }
    >
      <div className="es-form">
        {/* Title fields for each language */}
        <div className="es-section">
          <div className="es-section-title">{t("notification.titleLabel")}</div>
          <div className="space-y-3">
            {LOCALE_KEYS.map(({ key, label }) => (
              <div key={key} className="es-field">
                <label className="es-label">{label}</label>
                <Input
                  type="text"
                  value={titleI18n[key]}
                  onChange={(e) =>
                    setTitleI18n((prev) => ({
                      ...prev,
                      [key]: e.target.value,
                    }))
                  }
                  aria-label={`${t("notification.titleLabel")} - ${label}`}
                  placeholder={`${label} title`}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Content fields for each language */}
        <div className="es-section">
          <div className="es-section-title">
            {t("notification.contentLabel")}
          </div>
          <div className="space-y-3">
            {LOCALE_KEYS.map(({ key, label }) => (
              <div key={key} className="es-field">
                <label className="es-label">{label}</label>
                <Textarea
                  value={contentI18n[key]}
                  onChange={(e) =>
                    setContentI18n((prev) => ({
                      ...prev,
                      [key]: e.target.value,
                    }))
                  }
                  rows={3}
                  aria-label={`${t("notification.contentLabel")} - ${label}`}
                  placeholder={`${label} content`}
                />
              </div>
            ))}
          </div>
        </div>

        {/* Type selector */}
        <div className="es-field">
          <label className="es-label">{t("notification.typeLabel")}</label>
          <div className="flex flex-wrap gap-2">
            {(["info", "success", "warning", "maintenance"] as const).map(
              (nt) => (
                <button
                  key={nt}
                  type="button"
                  onClick={() => setNotifType(nt)}
                  className={`rounded-lg border px-3 py-2 text-xs font-medium transition-all ${
                    notifType === nt
                      ? nt === "info"
                        ? "border-blue-400 bg-blue-50 text-blue-700 dark:border-blue-500 dark:bg-blue-900/30 dark:text-blue-300"
                        : nt === "success"
                          ? "border-emerald-400 bg-emerald-50 text-emerald-700 dark:border-emerald-500 dark:bg-emerald-900/30 dark:text-emerald-300"
                          : nt === "warning"
                            ? "border-amber-400 bg-amber-50 text-amber-700 dark:border-amber-500 dark:bg-amber-900/30 dark:text-amber-300"
                            : "border-orange-400 bg-orange-50 text-orange-700 dark:border-orange-500 dark:bg-orange-900/30 dark:text-orange-300"
                      : "border-stone-200 bg-stone-50 text-stone-500 hover:border-stone-300 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-400 dark:hover:border-stone-600"
                  }`}
                >
                  {t(
                    `notification.type${
                      nt.charAt(0).toUpperCase() + nt.slice(1)
                    }`,
                  )}
                </button>
              ),
            )}
          </div>
        </div>

        {/* Schedule */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="es-field">
            <label className="es-label">{t("notification.startTime")}</label>
            <Input
              type="datetime-local"
              value={startTime}
              onChange={(e) => setStartTime(e.target.value)}
            />
          </div>
          <div className="es-field">
            <label className="es-label">{t("notification.endTime")}</label>
            <Input
              type="datetime-local"
              value={endTime}
              onChange={(e) => setEndTime(e.target.value)}
            />
          </div>
        </div>

        {/* Active toggle */}
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-theme-text-secondary">
            {t("notification.isActive")}
          </span>
          <ToggleSwitch
            enabled={isActive}
            onToggle={() => setIsActive(!isActive)}
            ariaLabel={t("notification.isActive")}
          />
        </div>
      </div>
    </EditorSidebar>
  );
}

export function NotificationPanel() {
  const { t, i18n } = useTranslation();
  const { hasPermission } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [total, setTotal] = useState(0);
  const [skip, setSkip] = useState(0);
  const [limit] = useState(20);
  const [deleteTarget, setDeleteTarget] = useState<Notification | null>(null);
  const [editingNotification, setEditingNotification] =
    useState<Notification | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  const canManage = hasPermission(Permission.NOTIFICATION_MANAGE);

  // Fetch notifications
  const fetchNotifications = useCallback(async () => {
    setIsLoading(true);
    try {
      const response = await notificationApi.list(skip, limit);
      setNotifications(response.items);
      setTotal(response.total);
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.loadFailed");
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }, [skip, limit, t]);

  // Initial load
  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  // Handle create
  const handleCreate = async (data: NotificationCreate) => {
    try {
      await notificationApi.create(data);
      toast.success(t("notification.createdSuccess"));
      setIsCreating(false);
      fetchNotifications();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.saveFailed");
      toast.error(message);
    }
  };

  // Handle update
  const handleUpdate = async (data: NotificationCreate) => {
    if (!editingNotification) return;
    try {
      await notificationApi.update(editingNotification.id, data);
      toast.success(t("notification.updatedSuccess"));
      setEditingNotification(null);
      fetchNotifications();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.saveFailed");
      toast.error(message);
    }
  };

  // Handle delete
  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await notificationApi.delete(deleteTarget.id);
      toast.success(t("notification.deletedSuccess"));
      setDeleteTarget(null);
      fetchNotifications();
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("common.deleteFailed");
      toast.error(message);
    }
  };

  // Get localized title with fallback
  const getLocalizedTitle = (notification: Notification): string => {
    const locale = (i18n.language || "en").split("-")[0];
    return (
      notification.title_i18n[locale as keyof I18nText] ||
      notification.title_i18n.en ||
      ""
    );
  };

  // Get localized content with fallback
  const getLocalizedContent = (notification: Notification): string => {
    const locale = (i18n.language || "en").split("-")[0];
    return (
      notification.content_i18n[locale as keyof I18nText] ||
      notification.content_i18n.en ||
      ""
    );
  };

  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Format schedule info
  const formatSchedule = (notification: Notification): string => {
    if (notification.start_time && notification.end_time) {
      return `${formatDateTimeShort(
        notification.start_time,
      )} - ${formatDateTimeShort(notification.end_time)}`;
    }
    if (notification.start_time) {
      return `${t("notification.startTime")}: ${formatDateTimeShort(
        notification.start_time,
      )}`;
    }
    if (notification.end_time) {
      return `${t("notification.endTime")}: ${formatDateTimeShort(
        notification.end_time,
      )}`;
    }
    return "";
  };

  // Permission denied
  if (!canManage) {
    return (
      <div className="glass-shell flex h-full flex-col items-center justify-center gap-4 p-8">
        <div className="flex h-16 w-16 items-center justify-center rounded-full bg-stone-100 dark:bg-stone-800">
          <AlertCircle
            size={32}
            className="text-stone-400 dark:text-stone-500"
          />
        </div>
        <p className="text-lg font-medium font-serif text-stone-700 dark:text-stone-300">
          {t("common.accessDenied")}
        </p>
        <p className="text-sm text-stone-500 dark:text-stone-400">
          {t("common.permissionRequired")}
        </p>
      </div>
    );
  }

  return (
    <div className="glass-shell flex h-full flex-col min-h-0">
      {/* Header */}
      <PanelHeader
        title={t("notification.title")}
        icon={<Bell size={20} className="text-stone-600 dark:text-stone-400" />}
        actions={
          <Button
            variant="primary"
            onClick={() => setIsCreating(true)}
            leftIcon={<Plus size={16} />}
          >
            <span>{t("notification.create")}</span>
          </Button>
        }
      />

      {/* Notification List */}
      <div className="flex-1 overflow-y-auto px-4 py-2 sm:p-6 lg:px-8">
        {isLoading && notifications.length === 0 ? (
          <PanelLoadingState />
        ) : !isLoading && notifications.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-stone-100 dark:bg-stone-800">
              <Bell size={32} className="text-stone-400 dark:text-stone-500" />
            </div>
            <p className="text-lg font-medium font-serif text-stone-700 dark:text-stone-300">
              {t("notification.noNotifications")}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {notifications.map((notification) => {
              const status = getNotificationStatus(notification);
              const schedule = formatSchedule(notification);
              const content = getLocalizedContent(notification);
              const isExpanded = expandedId === notification.id;
              const hasContent = content.length > 0;

              return (
                <div
                  key={notification.id}
                  className="glass-card overflow-hidden rounded-xl transition-colors hover:border-stone-300 dark:hover:border-stone-600"
                >
                  <div className="flex flex-col">
                    <div className="flex items-start justify-between gap-3 p-4 sm:p-5">
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-nowrap items-center gap-2 sm:gap-3">
                          <span
                            className={`inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-11 font-semibold uppercase leading-none ${
                              notification.type === "info"
                                ? "bg-blue-500/15 text-blue-600 dark:text-blue-300"
                                : notification.type === "success"
                                  ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300"
                                  : notification.type === "warning"
                                    ? "bg-amber-500/15 text-amber-600 dark:text-amber-300"
                                    : "bg-orange-500/15 text-orange-600 dark:text-orange-300"
                            }`}
                          >
                            {t(
                              `notification.type${
                                notification.type.charAt(0).toUpperCase() +
                                notification.type.slice(1)
                              }`,
                            )}
                          </span>
                          <p className="min-w-0 flex-1 truncate text-sm font-medium leading-6 text-stone-900 dark:text-stone-100 sm:text-15">
                            {getLocalizedTitle(notification)}
                          </p>
                          <StatusBadge
                            color={NOTIFICATION_STATUS_COLOR[status] ?? "stone"}
                            label={t(`notification.${status}`)}
                          />
                        </div>
                        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-stone-500 dark:text-stone-400">
                          {schedule && <span>{schedule}</span>}
                          <span>
                            {formatDateTimeShort(notification.created_at)}
                          </span>
                        </div>
                      </div>

                      <div className="flex flex-shrink-0 items-center gap-1">
                        {hasContent && (
                          <IconButton
                            aria-label={
                              isExpanded
                                ? t("notification.collapse")
                                : t("notification.expand")
                            }
                            icon={
                              <ChevronDown
                                size={16}
                                className={`transition-transform duration-200 ${
                                  isExpanded ? "rotate-180" : ""
                                }`}
                              />
                            }
                            onClick={() =>
                              setExpandedId(isExpanded ? null : notification.id)
                            }
                            className={`h-9 w-9 rounded-lg ${
                              isExpanded
                                ? "text-stone-600 bg-stone-100 dark:text-stone-300 dark:bg-stone-800"
                                : "text-stone-400 hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-800 dark:hover:text-stone-300"
                            }`}
                            title={
                              isExpanded
                                ? t("notification.collapse")
                                : t("notification.expand")
                            }
                          />
                        )}
                        <IconButton
                          aria-label={t("notification.edit")}
                          icon={<Pencil size={16} />}
                          onClick={() => setEditingNotification(notification)}
                          className="h-9 w-9 rounded-lg text-stone-400 hover:bg-stone-100 hover:text-stone-600 dark:hover:bg-stone-800 dark:hover:text-stone-300"
                          title={t("notification.edit")}
                        />
                        <IconButton
                          aria-label={t("notification.delete")}
                          icon={<Trash2 size={16} />}
                          onClick={() => setDeleteTarget(notification)}
                          className="h-9 w-9 rounded-lg text-stone-400 hover:bg-red-50 hover:text-red-500 dark:hover:bg-red-900/30 dark:hover:text-red-400"
                          title={t("notification.delete")}
                        />
                      </div>
                    </div>

                    {hasContent && (
                      <div
                        className={`border-t px-4 pb-4 sm:px-5 sm:pb-5 ${
                          isExpanded ? "pt-3 sm:pt-4" : "pt-0"
                        }`}
                        style={{ borderColor: "var(--theme-border)" }}
                      >
                        <div
                          className={`overflow-hidden transition-all duration-200 ${
                            isExpanded
                              ? "max-h-96 opacity-100"
                              : "max-h-0 opacity-0"
                          }`}
                        >
                          <div className="w-full text-xs leading-relaxed text-stone-600 dark:text-stone-400">
                            <div className="w-full break-words whitespace-pre-wrap">
                              {content}
                            </div>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Pagination */}
      {total > limit && (
        <div className="glass-divider bg-transparent px-4 py-4 sm:px-6 lg:px-8">
          <Pagination
            page={Math.floor(skip / limit) + 1}
            pageSize={limit}
            total={total}
            onChange={(page) => setSkip((page - 1) * limit)}
          />
        </div>
      )}

      {/* Create Modal */}
      {isCreating && (
        <NotificationFormModal
          notification={null}
          onSave={handleCreate}
          onClose={() => setIsCreating(false)}
        />
      )}

      {/* Edit Modal */}
      {editingNotification && (
        <NotificationFormModal
          notification={editingNotification}
          onSave={handleUpdate}
          onClose={() => setEditingNotification(null)}
        />
      )}

      {/* Delete Confirmation Modal */}
      <ConfirmDialog
        isOpen={!!deleteTarget}
        title={t("notification.deleteConfirm")}
        message={t("common.confirmAction")}
        confirmText={t("notification.delete")}
        cancelText={t("notification.cancel")}
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
        variant="danger"
      />
    </div>
  );
}
