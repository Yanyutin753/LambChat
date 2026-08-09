export type SubagentPanelStatus =
  | "pending"
  | "running"
  | "complete"
  | "error"
  | "cancelled";

const autoOpenedKeys = new Set<string>();
const dismissedKeys = new Set<string>();

export function markSubagentPanelAutoOpened(key: string): void {
  autoOpenedKeys.add(key);
}

export function hasSubagentPanelAutoOpened(key: string): boolean {
  return autoOpenedKeys.has(key);
}

export function dismissSubagentPanelAutoOpen(key: string): void {
  dismissedKeys.add(key);
}

export function isSubagentPanelAutoOpenDismissed(key: string): boolean {
  return dismissedKeys.has(key);
}

export function resetSubagentPanelAutoOpenState(key: string): void {
  autoOpenedKeys.delete(key);
  dismissedKeys.delete(key);
}

export function shouldAutoOpenSubagentPanel({
  status,
  laneOccupied,
  alreadyAutoOpened,
  autoOpenDismissed,
}: {
  status: SubagentPanelStatus;
  laneOccupied: boolean;
  alreadyAutoOpened: boolean;
  autoOpenDismissed: boolean;
}): boolean {
  return (
    status === "running" &&
    !laneOccupied &&
    !alreadyAutoOpened &&
    !autoOpenDismissed
  );
}

export function shouldExpandSubagentProcessByDefault(
  status: SubagentPanelStatus | undefined,
): boolean {
  return status === "running";
}
