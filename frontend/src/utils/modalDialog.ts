/**
 * Queries for modal dialogs that are actually presented to the user.
 *
 * Inactive right-panel tabs stay in the DOM carrying `hidden`/`inert`/
 * `aria-hidden`, so a bare `[aria-modal="true"]` query treats them as the
 * topmost overlay and suppresses Escape/Tab handling for the visible panel.
 * Visibility is filtered in JS: jsdom's selector engine rejects chained
 * `:not()` compound selectors.
 */
function isAvailable(element: HTMLElement): boolean {
  if (
    !element.isConnected ||
    element.closest('[hidden],[inert],[aria-hidden="true"]') ||
    element.matches(":disabled")
  )
    return false;
  for (
    let node: HTMLElement | null = element;
    node;
    node = node.parentElement
  ) {
    const style = getComputedStyle(node);
    if (style.display === "none" || /hidden|collapse/.test(style.visibility))
      return false;
  }
  return true;
}

export function visibleModalDialogs(): HTMLElement[] {
  return Array.from(
    document.querySelectorAll<HTMLElement>(
      '[role="dialog"][aria-modal="true"]',
    ),
  ).filter(isAvailable);
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
  ).filter(isAvailable);
  return dialogs.length > 0 ? dialogs[dialogs.length - 1] : null;
}

/**
 * Returns to the opener, a surviving dialog/panel, or page navigation after
 * responsive layout changes. Never steals focus already claimed elsewhere.
 */
export function restoreOpenerFocusUnclaimed(
  opener: HTMLElement | null | undefined,
  ownSurface: HTMLElement | null | undefined,
): void {
  const active = document.activeElement as HTMLElement | null;
  if (
    active &&
    active !== document.body &&
    !ownSurface?.contains(active) &&
    isAvailable(active)
  )
    return;
  if (opener && opener !== document.body && isAvailable(opener)) {
    opener.focus({ preventScroll: true });
    if (document.activeElement === opener) return;
  }
  const dialog = Array.from(
    document.querySelectorAll<HTMLElement>('[role="dialog"]'),
  )
    .reverse()
    .find((element) => element !== ownSurface && isAvailable(element));
  const region = opener?.closest<HTMLElement>(
    '[data-panel],main,[role="main"]',
  );
  const scopes = dialog
    ? [dialog]
    : [
        region,
        ...document.querySelectorAll<HTMLElement>(
          'header,[role="banner"],main,[role="main"]',
        ),
      ];
  for (const scope of scopes) {
    if (!scope || !isAvailable(scope) || ownSurface?.contains(scope)) continue;
    const controls = Array.from(
      scope.querySelectorAll<HTMLElement>(
        'button,a[href],input,select,textarea,[contenteditable="true"],[tabindex]',
      ),
    ).filter(
      (element) =>
        isAvailable(element) &&
        (element.tabIndex >= 0 ||
          (element.matches('[contenteditable="true"]') &&
            !element.hasAttribute("tabindex"))),
    );
    const selected = controls.find((element) =>
      element.matches(
        'button[aria-pressed="true"],[role="tab"][aria-selected="true"]',
      ),
    );
    const target = selected ?? controls[0] ?? scope;
    target.focus({ preventScroll: true });
    if (document.activeElement === target) return;
  }
}
