export type ProjectPreviewMode = "sidebar" | "center";

interface FullscreenCapableElement {
  requestFullscreen?: () => Promise<void> | void;
}

interface FullscreenCapableDocument {
  exitFullscreen?: () => Promise<void> | void;
  fullscreenElement?: Element | null;
}

export async function requestProjectPreviewFullscreen(input: {
  element: FullscreenCapableElement | null | undefined;
}): Promise<boolean> {
  const { element } = input;
  if (!element?.requestFullscreen) return false;

  try {
    await element.requestFullscreen();
    return true;
  } catch {
    return false;
  }
}

export async function exitProjectPreviewFullscreen(input?: {
  doc?: FullscreenCapableDocument | null | undefined;
}): Promise<void> {
  const doc = input?.doc ?? document;
  if (!doc?.exitFullscreen || !doc.fullscreenElement) return;
  await doc.exitFullscreen();
}

export function isProjectPreviewFullscreen(input: {
  element: Element | null | undefined;
  doc?: FullscreenCapableDocument | null | undefined;
}): boolean {
  const doc = input.doc ?? document;
  return !!input.element && doc?.fullscreenElement === input.element;
}

export function resolveProjectPreviewMode(
  currentMode: ProjectPreviewMode,
  fullscreenEntered: boolean,
): ProjectPreviewMode {
  return fullscreenEntered ? currentMode : "center";
}
