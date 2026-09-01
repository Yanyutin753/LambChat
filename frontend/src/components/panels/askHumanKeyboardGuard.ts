/**
 * Whether a keyboard event originates from an editable control (e.g. the
 * ask-human "other opinion" input). Card-level shortcuts such as digit
 * quick-select must yield to native text entry in that case.
 */
export function isEditableEventTarget(target: EventTarget | null): boolean {
  if (!target || typeof HTMLElement === "undefined") return false;
  if (
    target instanceof HTMLInputElement ||
    target instanceof HTMLTextAreaElement ||
    target instanceof HTMLSelectElement
  ) {
    return true;
  }
  return Boolean(target instanceof HTMLElement && target.isContentEditable);
}
