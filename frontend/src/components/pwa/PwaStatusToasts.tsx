import { useEffect, useRef } from "react";
import { RefreshCw, WifiOff, X } from "lucide-react";
import { toast } from "react-hot-toast";
import { useTranslation } from "react-i18next";
import {
  type LambChatPwaUpdateEventDetail,
  activateWaitingLambChatPwaUpdate,
} from "../../pwa";
import { ImageWithSkeleton } from "../chat/ChatMessage/ImageWithSkeleton";
import { PWA_UPDATE_AVAILABLE_EVENT } from "../../pwaGuards";
import {
  PWA_OFFLINE_TOAST_ID,
  PWA_ONLINE_RESTORED_TOAST_ID,
  PWA_UPDATE_TOAST_ID,
  getInitialOnlineStatus,
  shouldShowRestoredConnectionToast,
} from "../../pwaStatus";

function PwaStatusToast({
  titleKey,
  bodyKey,
  tone,
  actionLabelKey,
  dismissLabelKey,
  onAction,
  onDismiss,
}: {
  titleKey: string;
  bodyKey: string;
  tone: "update" | "offline";
  actionLabelKey?: string;
  dismissLabelKey?: string;
  onAction?: () => void;
  onDismiss?: () => void;
}) {
  const { t } = useTranslation();

  return (
    <div
      className={`pwa-status-toast font-serif pwa-status-toast--${tone}`}
      role="status"
    >
      <div className="pwa-status-toast__icon" aria-hidden="true">
        {tone === "offline" ? (
          <WifiOff size={17} />
        ) : (
          <ImageWithSkeleton
            src="/icons/icon.svg"
            alt=""
            skipUrlResolve
            inline
            className="rounded"
            style={{ width: 18, height: 18 }}
          />
        )}
      </div>
      <div className="pwa-status-toast__content">
        <span className="pwa-status-toast__title">{t(titleKey)}</span>
        {bodyKey && (
          <span className="pwa-status-toast__body"> {t(bodyKey)}</span>
        )}
      </div>
      {actionLabelKey && onAction && (
        <button
          className="pwa-status-toast__action"
          type="button"
          onClick={onAction}
        >
          <RefreshCw size={14} aria-hidden="true" />
          <span>{t(actionLabelKey)}</span>
        </button>
      )}
      {dismissLabelKey && onDismiss && (
        <button
          className="pwa-status-toast__dismiss"
          type="button"
          aria-label={t(dismissLabelKey)}
          onClick={onDismiss}
        >
          <X size={14} aria-hidden="true" />
        </button>
      )}
    </div>
  );
}

function showOfflineToast(titleKey: string, bodyKey: string) {
  toast.custom(
    <PwaStatusToast titleKey={titleKey} bodyKey={bodyKey} tone="offline" />,
    {
      id: PWA_OFFLINE_TOAST_ID,
      duration: Infinity,
      position: "top-center",
    },
  );
}

export function PwaStatusToasts() {
  const { t } = useTranslation();
  const isOnlineRef = useRef(
    getInitialOnlineStatus(
      typeof navigator === "undefined" ? undefined : navigator,
    ),
  );

  useEffect(() => {
    const handleUpdateAvailable = (event: Event) => {
      const registration = (event as CustomEvent<LambChatPwaUpdateEventDetail>)
        .detail?.registration;

      if (!registration) return;

      toast.custom(
        <PwaStatusToast
          titleKey="pwaStatus.updateReadyTitle"
          bodyKey="pwaStatus.updateReadyBody"
          tone="update"
          actionLabelKey="common.refresh"
          onAction={() => {
            if (activateWaitingLambChatPwaUpdate(registration)) {
              toast.dismiss(PWA_UPDATE_TOAST_ID);
            }
          }}
          dismissLabelKey="pwaStatus.dismiss"
          onDismiss={() => toast.dismiss(PWA_UPDATE_TOAST_ID)}
        />,
        {
          id: PWA_UPDATE_TOAST_ID,
          duration: Infinity,
          position: "top-center",
        },
      );
    };

    window.addEventListener(PWA_UPDATE_AVAILABLE_EVENT, handleUpdateAvailable);

    return () => {
      window.removeEventListener(
        PWA_UPDATE_AVAILABLE_EVENT,
        handleUpdateAvailable,
      );
    };
  }, [t]);

  useEffect(() => {
    if (!isOnlineRef.current) {
      showOfflineToast("pwaStatus.offlineTitle", "pwaStatus.offlineBody");
    }

    const handleOffline = () => {
      isOnlineRef.current = false;
      toast.dismiss(PWA_ONLINE_RESTORED_TOAST_ID);
      showOfflineToast("pwaStatus.offlineTitle", "pwaStatus.offlineBody");
    };

    const handleOnline = () => {
      const wasOnline = isOnlineRef.current;
      isOnlineRef.current = true;
      toast.dismiss(PWA_OFFLINE_TOAST_ID);

      if (
        shouldShowRestoredConnectionToast({
          wasOnline,
          isOnline: true,
        })
      ) {
        toast.success(t("pwaStatus.backOnline"), {
          id: PWA_ONLINE_RESTORED_TOAST_ID,
          duration: 2500,
        });
      }
    };

    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);

    return () => {
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
      toast.dismiss(PWA_OFFLINE_TOAST_ID);
    };
  }, [t]);

  return null;
}
