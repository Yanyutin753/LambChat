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

/** 会话切换：自动开面板的标记/静音记录不跨会话存活 */
export function clearSubagentPanelAutoOpenState(): void {
  autoOpenedKeys.clear();
  dismissedKeys.clear();
}

export function shouldAutoOpenSubagentPanel({
  status,
  laneOccupied,
  alreadyAutoOpened,
  autoOpenDismissed,
  userReadingHistory = false,
}: {
  status: SubagentPanelStatus;
  laneOccupied: boolean;
  alreadyAutoOpened: boolean;
  autoOpenDismissed: boolean;
  /** 用户上滑阅读历史中：自动弹面板会挤压聊天列宽打断阅读 */
  userReadingHistory?: boolean;
}): boolean {
  return (
    status === "running" &&
    !laneOccupied &&
    !alreadyAutoOpened &&
    !autoOpenDismissed &&
    !userReadingHistory
  );
}

export function shouldExpandSubagentProcessByDefault(
  status: SubagentPanelStatus | undefined,
): boolean {
  return status === "running";
}
