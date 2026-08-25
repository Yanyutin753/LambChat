import toast from "react-hot-toast";
import { Ban } from "lucide-react";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";
import { ImageViewer } from "../common";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { ContactAdminDialog } from "../common/ContactAdminDialog";

interface ChatInputDialogLayerProps {
  stopConfirmOpen: boolean;
  onConfirmStop: () => void;
  onCancelStop: () => void;
  contactAdminOpen: boolean;
  onCloseContactAdmin: () => void;
  imageViewerSrc: string | null;
  onCloseImageViewer: () => void;
}

/**
 * Chat-input dialogs rendered at body level. The expanded composer paints at
 * body level (z-280), so these dialogs must portal to document.body as well —
 * left inside the app shell their z-index is trapped by ancestor stacking
 * contexts and the composer would cover them.
 */
export function ChatInputDialogLayer({
  stopConfirmOpen,
  onConfirmStop,
  onCancelStop,
  contactAdminOpen,
  onCloseContactAdmin,
  imageViewerSrc,
  onCloseImageViewer,
}: ChatInputDialogLayerProps) {
  const { t } = useTranslation();
  return (
    <>
      {imageViewerSrc &&
        createPortal(
          <ImageViewer
            src={imageViewerSrc}
            isOpen={!!imageViewerSrc}
            onClose={onCloseImageViewer}
          />,
          document.body,
        )}

      {stopConfirmOpen &&
        createPortal(
          <ConfirmDialog
            isOpen={stopConfirmOpen}
            title={t("chat.stopConfirmTitle")}
            message={t("chat.stopConfirmMessage")}
            confirmText={t("chat.stop")}
            cancelText={t("common.cancel")}
            variant="warning"
            onConfirm={() => {
              onConfirmStop();
              toast.custom(() => (
                <div
                  className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium"
                  style={{
                    background:
                      "color-mix(in srgb, var(--theme-primary) 10%, transparent)",
                    border:
                      "1px solid color-mix(in srgb, var(--theme-primary) 20%, transparent)",
                    color: "var(--theme-primary)",
                  }}
                >
                  <Ban size={16} className="shrink-0" />
                  <span>{t("chat.status.cancelled")}</span>
                </div>
              ));
            }}
            onCancel={onCancelStop}
          />,
          document.body,
        )}

      {contactAdminOpen &&
        createPortal(
          <ContactAdminDialog
            isOpen={contactAdminOpen}
            onClose={onCloseContactAdmin}
            reason="noPermission"
          />,
          document.body,
        )}
    </>
  );
}
