const GLOBAL_FILE_DROP_IGNORE_SELECTOR =
  "[data-disable-global-file-drop='true']";

type DropTargetLike = {
  closest?: (selector: string) => unknown;
};

type DragEventLike = {
  target: EventTarget | null;
  composedPath?: () => EventTarget[];
};

function isIgnoredDropTarget(target: EventTarget | null): boolean {
  if (!target || typeof target !== "object") return false;

  const candidate = target as DropTargetLike;
  return !!candidate.closest?.(GLOBAL_FILE_DROP_IGNORE_SELECTOR);
}

export function shouldHandleGlobalFileDrop(event: DragEventLike): boolean {
  if (isIgnoredDropTarget(event.target)) {
    return false;
  }

  const path = event.composedPath?.() ?? [];
  return !path.some((target) => isIgnoredDropTarget(target));
}

export { GLOBAL_FILE_DROP_IGNORE_SELECTOR };
