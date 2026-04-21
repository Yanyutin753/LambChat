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

export function NotificationBanner() {
  const { t, i18n } = useTranslation();
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

  const lang = (i18n.language?.split("-")[0] ||
    "en") as keyof (typeof notifications)[number]["title_i18n"];

  return (
    <div className="flex flex-col gap-1.5 mb-3">
      {visible.map((n) => {
        const title = n.title_i18n[lang] || n.title_i18n.en;
        const content = n.content_i18n[lang] || n.content_i18n.en;
        const config = TYPE_CONFIG[n.type] || TYPE_CONFIG.info;
        const Icon = config.icon;

        return (
          <div
            key={n.id}
            className="flex items-center gap-2 rounded-lg border px-3 py-2 text-xs transition-all duration-300"
            style={{
              backgroundColor: "var(--theme-bg-card)",
              borderColor: "var(--theme-border)",
              animation: "fadeSlideIn 0.3s ease-out both",
            }}
          >
            <span
              className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase leading-none shrink-0 ${config.tagClass}`}
            >
              <Icon size={10} />
              {t(config.labelKey)}
            </span>
            <p
              className="leading-snug min-w-0 break-words"
              style={{ color: "var(--theme-text)" }}
            >
              {content ? `${title} — ${content}` : title}
            </p>
            <button
              onClick={() => handleDismiss(n.id)}
              className="shrink-0 p-0.5 rounded-md transition-colors"
              style={{ color: "var(--theme-text-secondary)" }}
              onMouseEnter={(e) => {
                e.currentTarget.style.color = "var(--theme-text)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.color = "var(--theme-text-secondary)";
              }}
            >
              <X size={12} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
