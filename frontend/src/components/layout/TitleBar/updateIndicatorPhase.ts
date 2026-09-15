import type { UpdateState } from "../../../types";

/** 标题栏更新指示器的呈现阶段（决定图标形态与 popover 主体） */
export type UpdateIndicatorPhase =
  | "downloading"
  | "ready"
  | "error"
  | "available";

export function updateIndicatorPhase(
  state: UpdateState,
): UpdateIndicatorPhase {
  if (state.downloading) return "downloading";
  if (state.readyToInstall) return "ready";
  if (state.error) return "error";
  return "available";
}
