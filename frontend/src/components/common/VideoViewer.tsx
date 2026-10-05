import {
  useEffect,
  useLayoutEffect,
  useCallback,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { X, Download, RefreshCw } from "lucide-react";
import { ViewerTopBar } from "./ViewerTopBar";
import { ViewerTopBarButton } from "./ViewerTopBarButton";
import { downloadUrl } from "./viewerDownload";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import { restoreOpenerFocusUnclaimed } from "../../utils/modalDialog";
import { SceneIllustration } from "./SceneIllustration";
import { useDialogFocus } from "./useDialogFocus";

interface VideoViewerProps {
  src: string;
  isOpen: boolean;
  onClose: () => void;
  title?: string;
}

export function VideoViewer({ src, isOpen, onClose, title }: VideoViewerProps) {
  const { t } = useTranslation();
  const surfaceRef = useRef<HTMLDialogElement | HTMLDivElement>(null);
  const nativeModal =
    typeof HTMLDialogElement !== "undefined" &&
    typeof HTMLDialogElement.prototype.showModal === "function";
  const Surface = nativeModal ? "dialog" : "div";
  const [hasError, setHasError] = useState(false);
  const [retryAttempt, setRetryAttempt] = useState(0);
  useDialogFocus({
    open: isOpen && !nativeModal,
    onClose,
    surfaceRef,
    nativeMediaControls: true,
  });
  useBodyScrollLock(isOpen, !nativeModal, !nativeModal);
  useLayoutEffect(() => {
    if (!isOpen || !nativeModal) return;
    const dialog = surfaceRef.current as HTMLDialogElement;
    const opener = document.activeElement as HTMLElement | null;
    dialog.showModal();
    return () => {
      dialog.close();
      queueMicrotask(() => restoreOpenerFocusUnclaimed(opener, dialog));
    };
  }, [isOpen, nativeModal]);

  useEffect(() => {
    setHasError(false);
    setRetryAttempt(0);
  }, [isOpen, src]);

  const handleBackgroundClick = useCallback(
    (e: React.MouseEvent<HTMLElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  if (!isOpen) return null;

  return createPortal(
    <Surface
      ref={(element: HTMLDialogElement | HTMLDivElement | null) => {
        surfaceRef.current = element;
      }}
      role="dialog"
      aria-modal="true"
      aria-label={title || t("fileLibrary.types.video")}
      tabIndex={-1}
      className="safe-area-x fixed inset-0 z-[300] flex flex-col bg-black backdrop:bg-black video-viewer m-0 w-full max-w-none max-h-none border-0 p-0"
      style={{
        height: "var(--app-viewport-height, 100dvh)",
        transform: "translate3d(0, var(--app-viewport-offset-top, 0px), 0)",
      }}
      onClick={handleBackgroundClick}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
      onKeyDown={(event) => {
        if (
          event.key === "Escape" &&
          (event.nativeEvent.isComposing || event.keyCode === 229)
        )
          event.preventDefault();
      }}
    >
      <ViewerTopBar>
        <ViewerTopBarButton
          onClick={onClose}
          aria-label={t("common.close")}
          icon={<X size={20} className="text-white/70" />}
          iconOnly
        />
        {title && (
          <span className="rounded-md bg-black/70 px-2.5 py-1 text-14 text-white/70 truncate max-w-[60vw] hidden sm:block">
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

      <div
        className="viewer-stage safe-area-bottom min-h-0 flex-1 overflow-hidden flex items-center justify-center"
        onClick={handleBackgroundClick}
      >
        <video
          key={`${src}:${retryAttempt}`}
          controls
          tabIndex={0}
          aria-label={title || t("fileLibrary.types.video")}
          autoPlay={false}
          playsInline
          hidden={hasError}
          preload="metadata"
          className="max-w-full max-h-full"
          src={src}
          onError={() => {
            if (surfaceRef.current?.contains(document.activeElement))
              surfaceRef.current.focus();
            setHasError(true);
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {t("documents.videoNotSupported")}
        </video>
        {hasError && (
          <div className="flex flex-col items-center gap-3 px-6 text-center text-white/80">
            <SceneIllustration scene="files" />
            <p role="alert" className="text-14">
              {t("documents.videoLoadFailed")}
            </p>
            <ViewerTopBarButton
              icon={<RefreshCw size={18} />}
              onClick={() => {
                surfaceRef.current?.focus();
                setHasError(false);
                setRetryAttempt((attempt) => attempt + 1);
              }}
            >
              {t("common.retry")}
            </ViewerTopBarButton>
          </div>
        )}
      </div>
    </Surface>,
    document.body,
  );
}
