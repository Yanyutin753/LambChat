import { useEffect, useState, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Bell, Calendar, X } from "lucide-react";
import { notificationApi } from "../../services/api/notification";
import { surfaceAppAnnouncementNotifications } from "../../services/notifications/announcementNotifications";
import type { Notification } from "../../types/notification";

const AUTO_PLAY_INTERVAL = 5000;

/** A compact auto-playing notification card pinned to the welcome page bottom. */
export function NotificationBanner() {
  const { t, i18n } = useTranslation();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  const [currentIndex, setCurrentIndex] = useState(0);
  const [selectedNotification, setSelectedNotification] =
    useState<Notification | null>(null);
  const [slideDirection, setSlideDirection] = useState<
    "left" | "right" | "none"
  >("none");
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const lang = (i18n.language?.split("-")[0] ||
    "en") as keyof Notification["title_i18n"];

  // ── Fetch notifications ──────────────────────────────────────────
  useEffect(() => {
    notificationApi.getActive().then((items) => {
      setNotifications(items);
      surfaceAppAnnouncementNotifications(items, lang);
    });
  }, [i18n.language, lang]);

  const visible = notifications.filter((n) => !dismissedIds.has(n.id));

  // ── Auto-play timer ───────────────────────────────────────────────
  const resetTimer = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current);
    if (visible.length > 1) {
      timerRef.current = setInterval(() => {
        setSlideDirection("left");
        setCurrentIndex((i) => (i + 1) % visible.length);
      }, AUTO_PLAY_INTERVAL);
    }
  }, [visible.length]);

  useEffect(() => {
    resetTimer();
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [resetTimer]);

  useEffect(() => {
    if (!selectedNotification) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelectedNotification(null);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [selectedNotification]);

  // Keep index in bounds when visible changes
  useEffect(() => {
    if (visible.length === 0) setCurrentIndex(0);
    else if (currentIndex >= visible.length) setCurrentIndex(0);
  }, [visible.length, currentIndex]);

  const current = visible[currentIndex];

  const goTo = useCallback(
    (index: number) => {
      if (index === currentIndex) return;
      setSlideDirection(index > currentIndex ? "left" : "right");
      setCurrentIndex(index);
      resetTimer();
    },
    [currentIndex, resetTimer],
  );

  const openSelectedNotification = useCallback(() => {
    setSelectedNotification(current);
  }, [current]);

  const closeSelectedNotification = useCallback(() => {
    setSelectedNotification(null);
  }, []);

  const handleDismiss = useCallback(async (id: string) => {
    setDismissedIds((prev) => new Set(prev).add(id));
    try {
      await notificationApi.dismiss(id);
    } catch {
      // silently fail
    }
  }, []);

  // ── Touch swipe support ───────────────────────────────────────────
  const touchStartX = useRef(0);
  const SWIPE_THRESHOLD = 40;

  const onTouchStart = useCallback((e: React.TouchEvent) => {
    touchStartX.current = e.touches[0].clientX;
  }, []);

  const onTouchEnd = useCallback(
    (e: React.TouchEvent) => {
      if (visible.length <= 1) return;
      const delta = e.changedTouches[0].clientX - touchStartX.current;
      if (Math.abs(delta) < SWIPE_THRESHOLD) return;
      if (delta < 0) {
        // swipe left → next
        goTo((currentIndex + 1) % visible.length);
      } else {
        // swipe right → prev
        goTo((currentIndex - 1 + visible.length) % visible.length);
      }
    },
    [visible.length, currentIndex, goTo],
  );

  if (visible.length === 0) return null;
  const title = current.title_i18n[lang] || current.title_i18n.en;
  const content = current.content_i18n[lang] || current.content_i18n.en;

  const slideIn =
    slideDirection === "left"
      ? "notification-slide-in-left"
      : slideDirection === "right"
        ? "notification-slide-in-right"
        : "notification-fade-in";

  return (
    <>
      <div className="absolute bottom-4 sm:bottom-6 left-0 right-0 flex justify-center px-[20px] z-0 pointer-events-none">
        <div className="w-full sm:max-w-[44rem] md:max-w-[46rem] lg:max-w-[48rem] xl:max-w-[50rem] 2xl:max-w-[52rem] flex flex-col items-center pointer-events-auto">
          {/* Card */}
          <div className="relative group max-w-full">
            {/* Close button — top-right, visible on hover */}
            <button
              onClick={() => handleDismiss(current.id)}
              className="notification-dismiss-btn absolute top-[-11px] end-[-6px] z-10 size-5 flex items-center justify-center rounded-full invisible group-hover:visible hover:opacity-80 cursor-pointer transition-opacity duration-200"
              style={{
                backgroundColor:
                  "var(--theme-text-tertiary, var(--theme-text-secondary))",
              }}
              aria-label={t("notification.dismiss", "关闭")}
            >
              <X size={14} style={{ color: "#fff" }} />
            </button>

            {/* Content area — slides in/out */}
            <button
              type="button"
              className={`notification-content w-[540px] max-w-full rounded-xl border cursor-pointer text-left transition-all duration-200 ${slideIn}`}
              style={{
                backgroundColor: "var(--theme-bg-card)",
                borderColor: "var(--theme-border)",
                boxShadow:
                  "0 1px 3px color-mix(in srgb, var(--theme-text) 6%, transparent), 0 0 0 0.5px color-mix(in srgb, var(--theme-border) 50%, transparent)",
              }}
              onTouchStart={onTouchStart}
              onTouchEnd={onTouchEnd}
              onClick={openSelectedNotification}
            >
              <div className="flex items-center gap-2 px-4 py-3">
                <div
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg"
                  style={{
                    backgroundColor:
                      "color-mix(in srgb, var(--theme-primary) 12%, transparent)",
                  }}
                >
                  <Bell size={16} style={{ color: "var(--theme-primary)" }} />
                </div>
                <div className="flex min-w-0 flex-1 flex-col gap-1">
                  <p
                    className="text-sm sm:text-[15px] font-semibold font-serif leading-[20px] truncate tracking-[-0.01em]"
                    style={{ color: "var(--theme-text)" }}
                    title={title}
                  >
                    {title}
                  </p>
                  {content && (
                    <p
                      className="text-xs sm:text-[13px] leading-[18px] line-clamp-1"
                      style={{ color: "var(--theme-text-secondary)" }}
                    >
                      {content}
                    </p>
                  )}
                </div>
              </div>
            </button>
          </div>
        </div>
      </div>

      {selectedNotification &&
        createPortal(
          <div
            className="fixed inset-0 z-[320] flex items-center justify-center bg-black/50 p-4"
            onClick={closeSelectedNotification}
          >
            <div
              role="dialog"
              aria-modal="true"
              aria-labelledby="notification-banner-detail-title"
              className="notification-banner-detail w-full max-w-2xl overflow-hidden rounded-2xl border shadow-2xl"
              style={{
                backgroundColor: "var(--theme-bg-card)",
                borderColor: "var(--theme-border)",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between gap-4 border-b px-5 py-4">
                <div className="flex items-center gap-2.5 min-w-0">
                  <div
                    className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg"
                    style={{
                      backgroundColor:
                        "color-mix(in srgb, var(--theme-primary) 12%, transparent)",
                    }}
                  >
                    <Bell size={17} style={{ color: "var(--theme-primary)" }} />
                  </div>
                  <div className="min-w-0">
                    <p
                      id="notification-banner-detail-title"
                      className="text-base font-semibold leading-tight"
                      style={{ color: "var(--theme-text)" }}
                    >
                      {selectedNotification.title_i18n[lang] ||
                        selectedNotification.title_i18n.en}
                    </p>
                    <p
                      className="text-xs"
                      style={{ color: "var(--theme-text-secondary)" }}
                    >
                      {t(
                        `notification.type${
                          selectedNotification.type.charAt(0).toUpperCase() +
                          selectedNotification.type.slice(1)
                        }`,
                      )}
                    </p>
                  </div>
                </div>
                <button
                  onClick={closeSelectedNotification}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg transition-colors"
                  style={{ color: "var(--theme-text-secondary)" }}
                  aria-label={t("common.dismiss", "关闭")}
                >
                  <X size={18} />
                </button>
              </div>

              <div className="space-y-4 px-5 py-5">
                <div className="space-y-2">
                  <p
                    className="text-sm leading-relaxed whitespace-pre-wrap"
                    style={{ color: "var(--theme-text)" }}
                  >
                    {selectedNotification.content_i18n[lang] ||
                      selectedNotification.content_i18n.en}
                  </p>
                </div>

                <div
                  className="flex flex-wrap items-center gap-3 border-t pt-4 text-xs"
                  style={{ borderColor: "var(--theme-border)" }}
                >
                  <span
                    className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1"
                    style={{
                      backgroundColor:
                        "color-mix(in srgb, var(--theme-primary) 10%, transparent)",
                      color: "var(--theme-text-secondary)",
                    }}
                  >
                    <Calendar size={12} />
                    {selectedNotification.created_at.slice(0, 10)}
                  </span>
                  <span
                    className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1"
                    style={{
                      backgroundColor:
                        "color-mix(in srgb, var(--theme-text) 4%, transparent)",
                      color: "var(--theme-text-secondary)",
                    }}
                  >
                    <Bell size={12} />
                    {selectedNotification.is_active
                      ? t("notification.active", "Active")
                      : t("notification.inactive", "Inactive")}
                  </span>
                </div>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}
