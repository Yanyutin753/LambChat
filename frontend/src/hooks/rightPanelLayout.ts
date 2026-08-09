import type { RightPanelKind } from "../components/common/rightPanelCoordinator";

export type RightPanelPresentation = "docked" | "overlay" | "fullscreen";

export interface RightPanelLayoutSnapshot {
  open: boolean;
  kind: RightPanelKind | null;
  presentation: RightPanelPresentation | null;
  widthPct: number;
  widthPx: number;
  viewportWidth: number;
}

export function getRightPanelPresentation(
  viewportWidth: number,
): RightPanelPresentation {
  if (viewportWidth < 640) return "fullscreen";
  if (viewportWidth < 1200) return "overlay";
  return "docked";
}

export function shouldAllowAutomaticRightPanel({
  presentation,
  laneOccupied,
}: {
  presentation: RightPanelPresentation;
  laneOccupied: boolean;
}): boolean {
  return presentation === "docked" && !laneOccupied;
}

export function sanitizePanelWidthPct(
  raw: string | null | undefined,
  fallback: number,
): number {
  const parsed = Number.parseInt(raw ?? "", 10);
  return Number.isFinite(parsed) ? parsed : fallback;
}

export function clampPanelWidthPct({
  requestedPct,
  viewportWidth,
  minPanelPx,
  minMainPx,
}: {
  requestedPct: number;
  viewportWidth: number;
  minPanelPx: number;
  minMainPx: number;
}): number {
  const minimum = Math.ceil((minPanelPx / viewportWidth) * 100);
  const maximum = Math.floor(
    ((viewportWidth - minMainPx) / viewportWidth) * 100,
  );
  return Math.round(
    Math.min(Math.max(requestedPct, minimum), Math.max(minimum, maximum)),
  );
}

export function resizePanelWidthPct(options: {
  currentPct: number;
  viewportWidth: number;
  minPanelPx: number;
  minMainPx: number;
  defaultPct: number;
  key: string;
  shiftKey: boolean;
}): number | null {
  const step = options.shiftKey ? 5 : 1;
  const requested =
    options.key === "Home"
      ? options.defaultPct
      : options.key === "ArrowLeft"
        ? options.currentPct - step
        : options.key === "ArrowRight"
          ? options.currentPct + step
          : null;

  return requested === null
    ? null
    : clampPanelWidthPct({ ...options, requestedPct: requested });
}
