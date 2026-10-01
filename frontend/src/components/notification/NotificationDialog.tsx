import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Info, CheckCircle, AlertTriangle, Wrench, Check } from "lucide-react";
import { notificationApi } from "../../services/api/notification";
import { surfaceAppAnnouncementNotifications } from "../../services/notifications/announcementNotifications";
import {
  SelectorModalHeader,
  SelectorModalPortal,
  SelectorModalShell,
} from "../selectors/shared";
import type { Notification, NotificationType } from "../../types/notification";
import { SceneIllustration } from "../common/SceneIllustration";
import { formatDateTimeShort } from "../../utils/datetime";

const TYPE_CONFIG: Record<
  NotificationType,
  { icon: typeof Info; labelKey: string; dotClass: string }
> = {
  info: {
    icon: Info,
    labelKey: "notification.typeInfo",
    dotClass: "bg-blue-500",
  },
  success: {
    icon: CheckCircle,
    labelKey: "notification.typeSuccess",
    dotClass: "bg-emerald-500",
  },
  warning: {
    icon: AlertTriangle,
    labelKey: "notification.typeWarning",
    dotClass: "bg-theme-warning",
  },
  maintenance: {
    icon: Wrench,
    labelKey: "notification.typeMaintenance",
    dotClass: "bg-theme-warning",
  },
};

interface NotificationDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onDismissed: () => void;
}

export function NotificationDialog({
  isOpen,
  onClose,
  onDismissed,
}: NotificationDialogProps) {
  const { t, i18n } = useTranslation();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [dismissingId, setDismissingId] = useState<string | null>(null);

  const fetchNotifications = useCallback(() => {
    notificationApi.getActive().then((items) => {
      setNotifications(items);
      const lang = (i18n.language?.split("-")[0] ||
        "en") as keyof Notification["title_i18n"];
      surfaceAppAnnouncementNotifications(items, lang);
    });
  }, [i18n.language]);

  useEffect(() => {
    if (!isOpen) return;
    fetchNotifications();
  }, [isOpen, fetchNotifications]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [isOpen, onClose]);

  const handleDismiss = async (id: string) => {
    setDismissingId(id);
    setNotifications((prev) => prev.filter((n) => n.id !== id));
    try {
      await notificationApi.dismiss(id);
    } catch {
      // keep local state removal even if API fails
    }
    setDismissingId(null);
    onDismissed();
  };

  if (!isOpen) return null;

  const lang = (i18n.language?.split("-")[0] ||
    "en") as keyof Notification["title_i18n"];

  return (
    <SelectorModalPortal open={isOpen} onClose={onClose}>
      <SelectorModalShell
        role="dialog"
        aria-modal="true"
        aria-label={t("nav.notifications")}
      >
        <SelectorModalHeader
          className="shrink-0"
          icon={
            <SceneIllustration
              scene="notification"
              className="notification-illustration"
            />
          }
          title={<span className="font-serif">{t("nav.notifications")}</span>}
          onClose={onClose}
        />

        {/* List */}
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 py-1 sm:px-6 sm:py-2">
          {notifications.length === 0 ? (
            <div className="flex min-h-48 flex-col items-center justify-center gap-3">
              <SceneIllustration scene="message" />
              <p
                className="text-14"
                style={{ color: "var(--theme-text-secondary)" }}
              >
                {t("notification.noNotifications")}
              </p>
            </div>
          ) : (
            notifications.map((n) => {
              const title = n.title_i18n[lang] || n.title_i18n.en;
              const content = n.content_i18n[lang] || n.content_i18n.en;
              const config = TYPE_CONFIG[n.type] || TYPE_CONFIG.info;
              const Icon = config.icon;
              const schedule =
                n.start_time && n.end_time
                  ? `${formatDateTimeShort(
                      n.start_time,
                    )} - ${formatDateTimeShort(n.end_time)}`
                  : n.start_time
                    ? formatDateTimeShort(n.start_time)
                    : n.end_time
                      ? formatDateTimeShort(n.end_time)
                      : "";

              return (
                <div
                  key={n.id}
                  className="py-3"
                  style={{
                    borderBottom: "1px solid var(--theme-border)",
                  }}
                >
                  {/* Top row */}
                  <div className="flex items-start sm:items-center justify-between gap-2 mb-1 flex-wrap">
                    <div className="flex items-center gap-2 min-w-0">
                      <span
                        className={`shrink-0 h-2 w-2 rounded-full ${config.dotClass}`}
                      />
                      <span
                        className="text-12 font-medium"
                        style={{ color: "var(--theme-text-secondary)" }}
                      >
                        {t(config.labelKey)}
                      </span>
                    </div>
                    <button
                      onClick={() => handleDismiss(n.id)}
                      disabled={dismissingId === n.id}
                      className="flex items-center gap-1 shrink-0 min-h-11 sm:min-h-6 rounded-lg px-3 text-12 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:opacity-50"
                      style={{ color: "var(--theme-text-secondary)" }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.backgroundColor =
                          "var(--theme-bg-hover, rgba(0,0,0,0.05))";
                        e.currentTarget.style.color = "var(--theme-text)";
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.backgroundColor = "transparent";
                        e.currentTarget.style.color =
                          "var(--theme-text-secondary)";
                      }}
                    >
                      <Check size={12} />
                      {t("notification.dismiss")}
                    </button>
                  </div>
                  {/* Title */}
                  <p
                    className="font-serif font-semibold text-16 leading-relaxed [overflow-wrap:anywhere]"
                    style={{ color: "var(--theme-text)" }}
                  >
                    {title}
                  </p>
                  {/* Content */}
                  {content && (
                    <p
                      className="text-14 mt-1 leading-6 whitespace-pre-wrap [overflow-wrap:anywhere]"
                      style={{ color: "var(--theme-text-secondary)" }}
                    >
                      {content}
                    </p>
                  )}
                  {/* Schedule */}
                  {schedule && (
                    <div
                      className="flex items-center gap-1.5 mt-2.5 pt-2 border-t"
                      style={{ borderColor: "var(--theme-border)" }}
                    >
                      <Icon
                        size={11}
                        style={{
                          color: "var(--theme-text-secondary)",
                          opacity: 0.5,
                        }}
                      />
                      <p
                        className="text-11"
                        style={{
                          color: "var(--theme-text-secondary)",
                          opacity: 0.7,
                        }}
                      >
                        {schedule}
                      </p>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </SelectorModalShell>
    </SelectorModalPortal>
  );
}
