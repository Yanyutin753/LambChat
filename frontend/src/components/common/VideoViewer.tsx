import { useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { X, Download } from "lucide-react";
import { ViewerTopBar } from "./ViewerTopBar";
import { ViewerTopBarButton } from "./ViewerTopBarButton";
import { downloadUrl } from "./viewerDownload";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";

interface VideoViewerProps {
  src: string;
  isOpen: boolean;
  onClose: () => void;
  title?: string;
}

export function VideoViewer({ src, isOpen, onClose, title }: VideoViewerProps) {
  const { t } = useTranslation();
  const videoRef = useRef<HTMLVideoElement>(null);
  useBodyScrollLock(isOpen);

  useEffect(() => {
    if (isOpen && videoRef.current) {
      videoRef.current.currentTime = 0;
    }
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen && videoRef.current) {
      videoRef.current.pause();
    }
  }, [isOpen]);

  const handleBackgroundClick = useCallback(
    (e: React.MouseEvent) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  if (!isOpen) return null;

  return createPortal(
    <div
      data-yields-sidebar
      className="safe-area-x fixed inset-0 z-[300] flex flex-col bg-black"
      onClick={handleBackgroundClick}
    >
      <ViewerTopBar className="bg-black/80 shrink-0">
        <ViewerTopBarButton
          onClick={onClose}
          aria-label={t("common.close")}
          icon={<X size={20} className="text-white/70" />}
          iconOnly
        />
        {title && (
          <span className="text-sm text-white/70 truncate max-w-[60vw] hidden sm:block">
            {title}
          </span>
        )}
        <ViewerTopBarButton
          onClick={() => downloadUrl(src)}
          aria-label={t("imageViewer.download")}
          icon={<Download size={18} className="text-white/70" />}
        >
          <span className="hidden sm:inline">{t("imageViewer.download")}</span>
        </ViewerTopBarButton>
      </ViewerTopBar>

      <div className="safe-area-bottom flex-1 overflow-hidden flex items-center justify-center">
        <video
          ref={videoRef}
          controls
          autoPlay={false}
          className="max-w-full max-h-full"
          src={src}
          onClick={(e) => e.stopPropagation()}
        >
          {t("documents.videoNotSupported")}
        </video>
      </div>
    </div>,
    document.body,
  );
}
