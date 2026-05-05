/**
 * Compute the viewport pixel coordinates of a character position in a textarea.
 * Uses the mirror-div technique to replicate the textarea's layout in a hidden
 * element and measure the target position.
 */
export function getCaretCoordinates(
  textarea: HTMLTextAreaElement,
  position: number,
): { top: number; left: number } | null {
  if (!document.createElement) return null;

  const div = document.createElement("div");
  const style = div.style;

  const computed = window.getComputedStyle(textarea);
  const propsToCopy = [
    "fontFamily",
    "fontSize",
    "fontWeight",
    "fontStyle",
    "letterSpacing",
    "textTransform",
    "wordWrap",
    "whiteSpace",
    "paddingTop",
    "paddingRight",
    "paddingBottom",
    "paddingLeft",
    "borderTopWidth",
    "borderRightWidth",
    "borderBottomWidth",
    "borderLeftWidth",
    "boxSizing",
    "lineHeight",
    "tabSize",
  ] as const;

  for (const prop of propsToCopy) {
    (style as unknown as Record<string, string>)[prop] =
      computed.getPropertyValue(prop);
  }

  style.position = "absolute";
  style.visibility = "hidden";
  style.overflow = "hidden";
  style.width = `${textarea.clientWidth}px`;

  const text = textarea.value.substring(0, position);
  div.textContent = text;

  const span = document.createElement("span");
  span.textContent = "."; // sentinel character to measure
  div.appendChild(span);

  document.body.appendChild(div);

  const spanRect = span.getBoundingClientRect();
  const textareaRect = textarea.getBoundingClientRect();
  const top = spanRect.top - textareaRect.top - textarea.scrollTop;
  const left = spanRect.left - textareaRect.left;

  document.body.removeChild(div);

  return { top, left };
}
