/**
 * Queries for modal dialogs that are actually presented to the user.
 *
 * Inactive right-panel tabs stay in the DOM carrying `hidden`/`inert`/
 * `aria-hidden`, so a bare `[aria-modal="true"]` query treats them as the
 * topmost overlay and suppresses Escape/Tab handling for the visible panel.
 * Visibility is filtered in JS: jsdom's selector engine rejects chained
 * `:not()` compound selectors.
 */
function isVisibleDialog(el: Element): el is HTMLElement {
  return (
    !(el as HTMLElement).hidden &&
    !el.hasAttribute("inert") &&
    el.getAttribute("aria-hidden") !== "true"
  );
}

export function visibleModalDialogs(): HTMLElement[] {
  return Array.from(
    document.querySelectorAll<HTMLElement>(
      '[role="dialog"][aria-modal="true"]',
    ),
  ).filter(isVisibleDialog);
}

export function hasVisibleModalDialog(): boolean {
  return visibleModalDialogs().length > 0;
}

export function topmostVisibleModalDialog(): HTMLElement | null {
  const dialogs = visibleModalDialogs();
  return dialogs.length > 0 ? dialogs[dialogs.length - 1] : null;
}

/**
 * Like {@link topmostVisibleModalDialog} but includes non-modal dialogs
 * (mobile drawers use `role="dialog"` without `aria-modal`); hidden panels
 * stay excluded so inactive tabs never shadow the active layer.
 */
export function topmostVisibleDialog(): HTMLElement | null {
  const dialogs = Array.from(
    document.querySelectorAll<HTMLElement>('[role="dialog"]'),
  ).filter(isVisibleDialog);
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
