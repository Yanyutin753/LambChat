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
  nativeMediaControls = false,
}: {
  open: boolean;
  onClose: () => void;
  surfaceRef: RefObject<HTMLElement | null>;
  dismissible?: boolean;
  nativeMediaControls?: boolean;
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
    let backwards = false;
    const controls = () =>
      Array.from(
        surface?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),input:not(:disabled),select:not(:disabled),textarea:not(:disabled),a[href],[contenteditable="true"],[tabindex]',
        ) ?? [],
      ).filter(
        (el) =>
          el.getClientRects().length &&
          (el.tabIndex >= 0 ||
            (el.matches('[contenteditable="true"]') &&
              !el.hasAttribute("tabindex"))) &&
          !el.closest('[inert],[aria-hidden="true"]'),
      );
    const containMediaFocus = () => {
      if (!ownsTopLayer(surface) || surface?.contains(document.activeElement))
        return;
      const targets = controls();
      (backwards ? targets[targets.length - 1] : targets[0])?.focus();
    };
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
      backwards = event.shiftKey;
      // Native media has internal tab stops absent from querySelectorAll.
      if (
        nativeMediaControls &&
        document.activeElement?.matches("video[controls],audio[controls]")
      )
        return;
      const targets = controls();
      const first = targets[0],
        last = targets[targets.length - 1];
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
    if (nativeMediaControls)
      document.addEventListener("focusin", containMediaFocus);
    return () => {
      document.removeEventListener("keydown", keyboard);
      if (nativeMediaControls)
        document.removeEventListener("focusin", containMediaFocus);
      const restore = () => {
        if (previous?.isConnected)
          restoreOpenerFocusUnclaimed(previous, surface);
      };
      // The background lock cleans up after this effect; native inert blocks focus.
      if (previous?.closest("[inert]")) queueMicrotask(restore);
      else restore();
    };
  }, [open, surfaceRef, nativeMediaControls]);
}
