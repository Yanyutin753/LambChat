import { API_BASE } from "../../services/api/config";
import { getStoredServerUrl } from "../../services/api/serverUrlStore";
import {
  parseWorkspaceSelection,
  type WorkspaceSelection,
} from "./workspaceSelection";

function preferenceKey(userId: string, machineId: string) {
  return `localWorkspace:${JSON.stringify([
    getStoredServerUrl() || API_BASE,
    userId,
    machineId,
  ])}`;
}

export function readLastLocalWorkspace(
  userId: string | undefined,
  machineId: string,
): WorkspaceSelection | null {
  if (!userId) return null;
  try {
    const selection = parseWorkspaceSelection(
      localStorage.getItem(preferenceKey(userId, machineId)),
    );
    return selection?.machineId === machineId ? selection : null;
  } catch {
    return null;
  }
}

export function rememberLocalWorkspace(
  userId: string | undefined,
  selection: WorkspaceSelection,
): void {
  if (!userId || !parseWorkspaceSelection(JSON.stringify(selection))) return;
  try {
    localStorage.setItem(
      preferenceKey(userId, selection.machineId),
      JSON.stringify(selection),
    );
  } catch {
    // Storage may be unavailable; the current conversation still uses the selection.
  }
}
