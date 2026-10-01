import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";
import { useDialogFocus } from "./useDialogFocus";
import "./modalSurface.css";

/** Shared positioning, dismissal and mobile gesture boundary for modal content. */
export function ModalSurface({
  open,
  onClose,
  children,
  dismissible = true,
  className = "",
  labelledBy,
  label,
  layer = 300,
}: {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  dismissible?: boolean;
  className?: string;
  labelledBy?: string;
  label?: string;
  layer?: number;
}) {
  const titleId = useId();
  const handleRef = useRef<HTMLDivElement>(null);
  const surfaceRef = useSwipeToClose({
    onClose,
    enabled: open && dismissible,
    dragHandleRef: handleRef,
  });
  useBodyScrollLock(open);
  useEffect(() => {
    if (!open) return;
    const surface = surfaceRef.current;
    const heading = surface?.querySelector<HTMLElement>("h1,h2,h3");
    if (!label && !labelledBy && heading && surface) {
      heading.id ||= titleId;
      surface.setAttribute("aria-labelledby", heading.id);
    }
  }, [open, surfaceRef, label, labelledBy, titleId]);
  useDialogFocus({ open, onClose, surfaceRef, dismissible });
  if (!open) return null;
  return createPortal(
    <div
      data-yields-sidebar
      style={{ zIndex: layer }}
      className="safe-area-viewport-padding-top modal-overlay"
    >
      <div
        data-dialog-backdrop
        className="modal-backdrop"
        onClick={dismissible ? onClose : undefined}
      />
      <div
        ref={surfaceRef as React.RefObject<HTMLDivElement>}
        data-modal-surface
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        aria-label={label}
        tabIndex={-1}
        className={`modal-surface ${className}`}
      >
        {dismissible && (
          <div
            ref={handleRef}
            data-modal-handle
            className="modal-handle"
            aria-hidden="true"
          >
            <span />
          </div>
        )}
        {children}
      </div>
    </div>,
    document.body,
  );
}
