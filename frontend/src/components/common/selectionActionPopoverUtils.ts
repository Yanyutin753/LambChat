export type SelectionAction = "ask" | "explain";

export const SELECTION_ACTION_EVENT = "lambchat:selection-action";
const PENDING_SELECTION_PROMPT_KEY = "lambchat:pending-selection-action-prompt";

export interface SelectionActionEventDetail {
  prompt: string;
}

export interface SelectionRectLike {
  left: number;
  right: number;
  top: number;
  bottom: number;
  width: number;
  height: number;
}

export interface SelectionPopoverPositionInput {
  selectionRect: SelectionRectLike;
  viewportWidth: number;
  viewportHeight: number;
  menuWidth: number;
  menuHeight: number;
  scrollX?: number;
  scrollY?: number;
  gap?: number;
  margin?: number;
}

export function getSelectionPopoverPosition({
  selectionRect,
  viewportWidth,
  viewportHeight,
  menuWidth,
  menuHeight,
  gap = 8,
  margin = 8,
}: SelectionPopoverPositionInput): { left: number; top: number } {
  const selectedCenter = selectionRect.left + selectionRect.width / 2;
  const maxLeft = Math.max(margin, viewportWidth - menuWidth - margin);
  const left = Math.min(
    Math.max(selectedCenter - menuWidth / 2, margin),
    maxLeft,
  );

  const belowTop = selectionRect.bottom + gap;
  const fitsBelow = belowTop + menuHeight + margin <= viewportHeight;
  const top = fitsBelow
    ? belowTop
    : Math.max(margin, selectionRect.top - menuHeight - gap);

  return {
    left: Math.round(left),
    top: Math.round(top),
  };
}

export function buildSelectionActionPrompt({
  action,
  selectedText,
  templates,
}: {
  action: SelectionAction;
  selectedText: string;
  templates: Record<SelectionAction, string>;
}): string {
  const trimmedText = selectedText.trim();
  const longestBacktickRun =
    Math.max(
      ...Array.from(trimmedText.matchAll(/`+/g), (match) => match[0].length),
      2,
    ) + 1;
  const fence = "`".repeat(longestBacktickRun);
  const codeBlock = `${fence}\n${trimmedText}\n${fence}`;

  return templates[action]
    .replace("{{codeBlock}}", codeBlock)
    .replace("{{text}}", trimmedText);
}

export function dispatchSelectionActionPrompt(prompt: string): void {
  window.dispatchEvent(
    new CustomEvent<SelectionActionEventDetail>(SELECTION_ACTION_EVENT, {
      detail: { prompt },
    }),
  );
}

export function storePendingSelectionActionPrompt(prompt: string): void {
  sessionStorage.setItem(PENDING_SELECTION_PROMPT_KEY, prompt);
}

export function consumePendingSelectionActionPrompt(): string | null {
  const prompt = sessionStorage.getItem(PENDING_SELECTION_PROMPT_KEY);
  if (prompt) {
    sessionStorage.removeItem(PENDING_SELECTION_PROMPT_KEY);
  }
  return prompt;
}
