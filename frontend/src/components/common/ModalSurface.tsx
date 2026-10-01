import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useBodyScrollLock } from "../../hooks/useBodyScrollLock";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";
import { getTopDialog } from "../../utils/dialogStack";
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
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const handleRef = useRef<HTMLDivElement>(null);
  const surfaceRef = useSwipeToClose({
    onClose,
    enabled: open && dismissible,
    dragHandleRef: handleRef,
  });
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    if (!surfaceRef.current?.contains(document.activeElement))
      surfaceRef.current?.focus();
    return () => queueMicrotask(() => previous?.focus());
  }, [open, surfaceRef]);
  useEffect(() => {
    if (!open) return;
    const surface = surfaceRef.current;
    const heading = surface?.querySelector<HTMLElement>("h1,h2,h3");
    if (!label && !labelledBy && heading && surface) {
      heading.id ||= titleId;
      surface.setAttribute("aria-labelledby", heading.id);
    }
    const keyboard = (event: KeyboardEvent) => {
      if (getTopDialog() !== surface || event.defaultPrevented) return;
      if (event.key === "Escape" && dismissible) {
        event.preventDefault();
        closeRef.current();
      }
      if (event.key !== "Tab" || !surface) return;
      const controls = Array.from(
        surface.querySelectorAll<HTMLElement>(
          'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]',
        ),
      ).filter((el) => el.getClientRects().length);
      const first = controls[0],
        last = controls[controls.length - 1];
      if (!first) event.preventDefault();
      else if (
        event.shiftKey &&
        (document.activeElement === first || document.activeElement === surface)
      ) {
        event.preventDefault();
        last.focus();
      } else if (
        !event.shiftKey &&
        (document.activeElement === last || document.activeElement === surface)
      ) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", keyboard);
    return () => {
      document.removeEventListener("keydown", keyboard);
    };
  }, [open, dismissible, surfaceRef, label, labelledBy, titleId]);
  useBodyScrollLock(open, true);
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
