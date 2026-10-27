export const WORKSPACE_OPTION = "sandbox_workspace";
export const WORKSPACE_OPTION_KEYS = new Set([
  "sandbox",
  "sandbox_machine_id",
  WORKSPACE_OPTION,
]);

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
      selection.machineId.length > 0 &&
      selection.machineId.length <= 256 &&
      typeof selection.path === "string" &&
      selection.path.length > 0 &&
      selection.path.length <= 4096
    ) {
      return selection;
    }
  } catch {
    /* Older sessions have no directory selection. */
  }
  return null;
}

/** Machine and directory must be persisted and applied as one selection. */
export function workspaceOptionPatch(
  key: string,
  value: boolean | string | number,
): Record<string, boolean | string | number> {
  if (key === WORKSPACE_OPTION) {
    const selection = parseWorkspaceSelection(value);
    if (selection)
      return {
        sandbox: "local",
        sandbox_machine_id: selection.machineId,
        [key]: value,
      };
  }
  if (key === "sandbox_machine_id")
    return { [key]: value, [WORKSPACE_OPTION]: "" };
  if (key === "sandbox" && value === "cloud")
    return {
      [key]: value,
      sandbox_machine_id: "",
      [WORKSPACE_OPTION]: "",
    };
  return { [key]: value };
}

export function isCurrentWorkspaceMachine(
  mode: unknown,
  selected: string | null | undefined,
  current: string | null | undefined,
): boolean {
  return mode === "local" && !!current && current === selected;
}
