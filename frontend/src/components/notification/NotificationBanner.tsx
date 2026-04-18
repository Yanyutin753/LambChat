import { useEffect, useState, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Info, CheckCircle, AlertTriangle, Wrench, X } from "lucide-react";
import { notificationApi } from "../../services/api/notification";
import type { Notification, NotificationType } from "../../types/notification";

const TYPE_CONFIG: Record<
  NotificationType,
  { icon: typeof Info; labelKey: string; tagClass: string }
> = {
  info: {
    icon: Info,
    labelKey: "notification.typeInfo",
    tagClass: "bg-blue-500/15 text-blue-600 dark:text-blue-300",
  },
  success: {
    icon: CheckCircle,
    labelKey: "notification.typeSuccess",
    tagClass: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-300",
  },
  warning: {
    icon: AlertTriangle,
    labelKey: "notification.typeWarning",
    tagClass: "bg-amber-500/15 text-amber-600 dark:text-amber-300",
  },
  maintenance: {
    icon: Wrench,
    labelKey: "notification.typeMaintenance",
    tagClass: "bg-orange-500/15 text-orange-600 dark:text-orange-300",
  },
};

function NotificationCard({
  notification,
  onDismiss,
  style,
}: {
  notification: Notification;
  onDismiss: () => void;
  style: React.CSSProperties;
}) {
  const { t, i18n } = useTranslation();
  const lang = (i18n.language?.split("-")[0] ||
    "en") as keyof typeof notification.title_i18n;
  const title = notification.title_i18n[lang] || notification.title_i18n.en;
  const content =
    notification.content_i18n[lang] || notification.content_i18n.en;
  const config = TYPE_CONFIG[notification.type] || TYPE_CONFIG.info;
  const Icon = config.icon;

  return (
    <div
      className="mx-3 sm:mx-4 flex items-start gap-3 rounded-xl border px-3 py-2.5 backdrop-blur-xl transition-all duration-300"
      style={{
        backgroundColor: "var(--theme-bg-card)",
        borderColor: "var(--theme-border)",
        ...style,
      }}
    >
      <div className="flex flex-1 flex-col gap-1.5 min-w-0">
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold uppercase leading-none ${config.tagClass}`}
          >
            <Icon size={11} />
            {t(config.labelKey)}
          </span>
        </div>
        <p
          className="text-sm leading-snug"
          style={{ color: "var(--theme-text)" }}
        >
          {title}
          {content ? ` — ${content}` : ""}
        </p>
      </div>
      <button
        onClick={onDismiss}
        className="mt-0.5 shrink-0 flex h-5 w-5 items-center justify-center rounded-md transition-colors"
        style={{ color: "var(--theme-text-secondary)" }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = "var(--theme-text)";
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = "var(--theme-text-secondary)";
        }}
      >
        <X size={13} />
      </button>
    </div>
  );
}

export function NotificationBanner() {
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    notificationApi.getActive().then(setNotifications);
  }, []);

  const handleDismiss = useCallback(async (id: string) => {
    setDismissedIds((prev) => new Set(prev).add(id));
    try {
      await notificationApi.dismiss(id);
    } catch {
      // silently fail
    }
  }, []);

  const visible = notifications.filter((n) => !dismissedIds.has(n.id));
  if (visible.length === 0) return null;

  return (
    <div className="shrink-0 flex flex-col gap-1.5 py-2 relative z-30">
      {visible.map((n) => (
        <NotificationCard
          key={n.id}
          notification={n}
          onDismiss={() => handleDismiss(n.id)}
          style={{ animation: "fadeSlideIn 0.3s ease-out both" }}
        />
      ))}
    </div>
  );
}
