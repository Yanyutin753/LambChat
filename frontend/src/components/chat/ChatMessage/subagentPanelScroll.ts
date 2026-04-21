interface SubagentPanelScrollerLike {
  scrollTop: number;
  clientHeight: number;
  scrollHeight: number;
}

export const SUBAGENT_PANEL_BOTTOM_THRESHOLD_PX = 32;

export function isNearSubagentPanelBottom(
  scroller: SubagentPanelScrollerLike,
  thresholdPx = SUBAGENT_PANEL_BOTTOM_THRESHOLD_PX,
): boolean {
  return (
    scroller.scrollTop + scroller.clientHeight >=
    scroller.scrollHeight - thresholdPx
  );
}

export function shouldAutoScrollSubagentPanel({
  scroller,
  userScrolledUp,
}: {
  scroller: SubagentPanelScrollerLike | null | undefined;
  userScrolledUp: boolean;
}): boolean {
  return !!scroller && !userScrolledUp;
}
