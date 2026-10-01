import { useEffect, useRef, type RefObject } from "react";
import {
  restoreOpenerFocusUnclaimed,
  topmostVisibleDialog,
  topmostVisibleModalDialog,
} from "../../utils/modalDialog";

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
  // Focus capture/return must re-run only when `open` flips; other option
  // changes (e.g. dismissible) must not restore focus while still open.
  const dismissibleRef = useRef(dismissible);
  dismissibleRef.current = dismissible;
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const surface = surfaceRef.current;
    if (!surface?.contains(document.activeElement)) surface?.focus();
    const ownsTopLayer = (surface: HTMLElement | null) =>
      surface !== null &&
      (topmostVisibleDialog() === surface ||
        topmostVisibleModalDialog() === surface);
    const keyboard = (event: KeyboardEvent) => {
      if (
        !ownsTopLayer(surface) ||
        event.defaultPrevented ||
        event.isComposing ||
        event.keyCode === 229
      )
        return;
      if (event.key === "Escape" && dismissibleRef.current) {
        event.preventDefault();
        closeRef.current();
      }
      if (event.key !== "Tab" || !surface) return;
      const controls = Array.from(
        surface.querySelectorAll<HTMLElement>(
          'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[contenteditable="true"],[tabindex]',
        ),
      ).filter(
        (el) =>
          el.getClientRects().length &&
          (el.tabIndex >= 0 ||
            (el.matches('[contenteditable="true"]') &&
              !el.hasAttribute("tabindex"))) &&
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
      const restore = () => {
        if (previous?.isConnected)
          restoreOpenerFocusUnclaimed(previous, surface);
      };
      // The background lock cleans up after this effect; native inert blocks focus.
      if (previous?.closest("[inert]")) queueMicrotask(restore);
      else restore();
    };
  }, [open, surfaceRef]);
}
