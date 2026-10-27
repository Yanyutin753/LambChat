import { useMemo } from "react";
import toast from "react-hot-toast";
import { Ban } from "lucide-react";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";
import { ImageViewer } from "../common";
import {
  resolveImageListNavigation,
  type ImageListEntry,
} from "../common/imageListNavigation";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { ContactAdminDialog } from "../common/ContactAdminDialog";
import { getFullUrl } from "../../services/api";
import type { MessageAttachment } from "../../types";

interface ChatInputDialogLayerProps {
  stopConfirmOpen: boolean;
  onConfirmStop: () => void;
  onCancelStop: () => void;
  contactAdminOpen: boolean;
  onCloseContactAdmin: () => void;
  imageViewerSrc: string | null;
  onCloseImageViewer: () => void;
  /** 当前输入框里的附件：灯箱在其中的图片之间左右切换 */
  imageViewerAttachments?: readonly MessageAttachment[];
  onImageViewerChange?: (src: string) => void;
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
  imageViewerAttachments,
  onImageViewerChange,
}: ChatInputDialogLayerProps) {
  const { t } = useTranslation();
  // src 与 ChatInputAttachments 打开灯箱时同一解析，才能在列表里对上位置
  const imageEntries = useMemo<ImageListEntry[]>(
    () =>
      (imageViewerAttachments ?? []).flatMap((attachment) =>
        attachment.mimeType?.startsWith("image/") && attachment.url
          ? [{ src: getFullUrl(attachment.url) ?? "", alt: attachment.name }]
          : [],
      ),
    [imageViewerAttachments],
  );
  const navigation = resolveImageListNavigation(imageEntries, imageViewerSrc);
  const goTo = (entry: ImageListEntry | null) => {
    if (entry) onImageViewerChange?.(entry.src);
  };
  return (
    <>
      {imageViewerSrc &&
        createPortal(
          <ImageViewer
            src={imageViewerSrc}
            alt={navigation.current?.alt}
            isOpen={!!imageViewerSrc}
            onClose={onCloseImageViewer}
            onPrevious={() => goTo(navigation.previous)}
            onNext={() => goTo(navigation.next)}
            hasPrevious={!!navigation.previous}
            hasNext={!!navigation.next}
            positionLabel={navigation.positionLabel}
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
              toast(t("chat.status.cancelled"), {
                icon: (
                  <Ban
                    size={16}
                    className="shrink-0 text-theme-primary"
                    aria-hidden="true"
                  />
                ),
              });
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
