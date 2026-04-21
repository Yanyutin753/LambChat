export type SubagentPanelStatus =
  | "pending"
  | "running"
  | "complete"
  | "error"
  | "cancelled";

export function shouldAutoOpenSubagentPanel({
  status,
  anyPanelOpen,
}: {
  status: SubagentPanelStatus;
  anyPanelOpen: boolean;
}): boolean {
  return status === "running" && !anyPanelOpen;
}
