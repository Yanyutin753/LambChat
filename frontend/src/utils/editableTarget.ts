/**
 * Whether a keyboard event target is an editable field (input, textarea, or
 * contenteditable). Global shortcuts that navigate (e.g. new session) must be
 * suppressed while the user is typing inside a field or an open modal input.
 */
export function isEditableEventTarget(target: EventTarget | null | undefined): boolean {
  if (!target || typeof (target as HTMLElement).tagName !== "string") {
    return false;
  }
  const el = target as HTMLElement;
  const tagName = el.tagName.toLowerCase();
  if (tagName === "input" || tagName === "textarea" || tagName === "select") {
    return true;
  }
  return (
    el.isContentEditable === true ||
    el.getAttribute?.("contenteditable") === "true"
  );
}
