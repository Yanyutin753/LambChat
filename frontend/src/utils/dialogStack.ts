/** Mounted but hidden panel tabs must not own foreground keyboard events. */
export function getTopDialog(): HTMLElement | undefined {
  return Array.from(document.querySelectorAll<HTMLElement>('[role="dialog"]'))
    .filter(
      (dialog) => !dialog.closest('[hidden], [inert], [aria-hidden="true"]'),
    )
    .at(-1);
}
