export const WORKSPACE_OPTION = "sandbox_workspace";

export interface WorkspaceSelection {
  id: string;
  machineId: string;
  path: string;
}

export function parseWorkspaceSelection(
  value: unknown,
): WorkspaceSelection | null {
  if (typeof value !== "string") return null;
  try {
    const selection = JSON.parse(value);
    if (
      selection &&
      /^local-[0-9a-f]{32}$/.test(selection.id) &&
      typeof selection.machineId === "string" &&
      typeof selection.path === "string"
    ) {
      return selection;
    }
  } catch {
    /* Older sessions have no directory selection. */
  }
  return null;
}

export function isCurrentWorkspaceMachine(
  mode: unknown,
  selected: string | null | undefined,
  current: string | null | undefined,
  online: boolean,
): boolean {
  return mode === "local" && !!current && current === selected && online;
}
