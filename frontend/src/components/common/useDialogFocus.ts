import { useEffect, useRef, type RefObject } from "react";

/** Shared keyboard boundary for modal surfaces and mobile navigation. */
export function useDialogFocus({
  open,
  onClose,
  surfaceRef,
  dismissible = true,
}: {
  open: boolean;
  onClose: () => void;
  surfaceRef: RefObject<HTMLElement | null>;
  dismissible?: boolean;
}) {
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const surface = surfaceRef.current;
    if (!surface?.contains(document.activeElement)) surface?.focus();
    const keyboard = (event: KeyboardEvent) => {
      const dialogs = [...document.querySelectorAll('[role="dialog"]')].filter(
        (el) => !el.closest('[inert],[aria-hidden="true"]'),
      );
      if (dialogs[dialogs.length - 1] !== surface || event.defaultPrevented)
        return;
      if (event.key === "Escape" && dismissible) {
        event.preventDefault();
        closeRef.current();
      }
      if (event.key !== "Tab" || !surface) return;
      const controls = Array.from(
        surface.querySelectorAll<HTMLElement>(
          'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[tabindex="0"]',
        ),
      ).filter(
        (el) =>
          el.getClientRects().length &&
          !el.closest('[inert],[aria-hidden="true"]'),
      );
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
      if (previous?.isConnected) previous.focus();
    };
  }, [open, dismissible, surfaceRef]);
}
