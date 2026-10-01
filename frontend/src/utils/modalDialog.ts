/**
 * Queries for modal dialogs that are actually presented to the user.
 *
 * Inactive right-panel tabs stay in the DOM carrying `hidden`/`inert`/
 * `aria-hidden`, so a bare `[aria-modal="true"]` query treats them as the
 * topmost overlay and suppresses Escape/Tab handling for the visible panel.
 */
const VISIBLE_MODAL_SELECTOR =
  '[role="dialog"][aria-modal="true"]:not([hidden]):not([inert]):not([aria-hidden="true"])';

export function visibleModalDialogs(): NodeListOf<HTMLElement> {
  return document.querySelectorAll<HTMLElement>(VISIBLE_MODAL_SELECTOR);
}

export function hasVisibleModalDialog(): boolean {
  return document.querySelector(VISIBLE_MODAL_SELECTOR) !== null;
}

export function topmostVisibleModalDialog(): HTMLElement | null {
  const dialogs = visibleModalDialogs();
  return dialogs.length > 0 ? dialogs[dialogs.length - 1] : null;
}

/**
 * Returns focus to the opener after an overlay closes, unless a newer
 * visible overlay has already claimed focus in the same update — closing A
 * while opening B must not let A's cleanup steal focus back from B.
 */
export function restoreOpenerFocusUnclaimed(
  opener: HTMLElement | null | undefined,
  ownSurface: HTMLElement | null | undefined,
): void {
  if (!opener) return;
  const active = document.activeElement as HTMLElement | null;
  const claimedBy = active?.closest?.(
    '[role="dialog"][aria-modal="true"]',
  ) as HTMLElement | null;
  if (claimedBy && claimedBy !== ownSurface) return;
  opener.focus();
}
