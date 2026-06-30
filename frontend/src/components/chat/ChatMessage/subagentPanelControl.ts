export type SubagentPanelStatus =
  | "pending"
  | "running"
  | "complete"
  | "error"
  | "cancelled";

let subagentPanelAutoOpenDismissed = false;

export function isSubagentPanelAutoOpenDismissed(): boolean {
  return subagentPanelAutoOpenDismissed;
}

export function dismissSubagentPanelAutoOpen(): void {
  subagentPanelAutoOpenDismissed = true;
}

export function resetSubagentPanelAutoOpenDismissal(): void {
  subagentPanelAutoOpenDismissed = false;
}

export function shouldAutoOpenSubagentPanel({
  status,
  anyPanelOpen,
  autoOpenDismissed = false,
}: {
  status: SubagentPanelStatus;
  anyPanelOpen: boolean;
  autoOpenDismissed?: boolean;
}): boolean {
  return status === "running" && !anyPanelOpen && !autoOpenDismissed;
}

export function shouldExpandSubagentProcessByDefault(
  status: SubagentPanelStatus | undefined,
): boolean {
  return status === "running";
}
