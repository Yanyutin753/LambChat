import { getFullUrl } from "../services/api/config";
import { createContext } from "react";
import type { WorkspaceSelection } from "../components/chat/workspaceSelection";

export interface WorkspaceMediaBinding {
  sessionId: string | null | undefined;
  cloud: boolean;
  machineId?: string;
  selection?: WorkspaceSelection | null;
}

// Absent in shared chats: local files require an authenticated workspace.
export const WorkspaceMediaContext =
  createContext<WorkspaceMediaBinding | null>(null);

export function workspaceMediaPath(
  source: string,
  binding: WorkspaceMediaBinding,
): string {
  let path = source;
  if (/^file:\/\//i.test(path)) {
    const file = new URL(path);
    if (file.hostname && file.hostname !== "localhost")
      throw new Error("Unsupported file host");
    path = decodeURIComponent(file.pathname).replace(/^\/([A-Za-z]:\/)/, "$1");
  }
  path = path.replace(/^\\\\\?\\/, "").replace(/\\/g, "/");
  const selection =
    !binding.cloud && binding.selection?.machineId === binding.machineId
      ? binding.selection
      : null;
  const roots = [`/workspace/${binding.sessionId}`];
  if (selection)
    roots.push(
      `/workspace/.selected/${selection.id}`,
      selection.path
        .replace(/^\\\\\?\\/, "")
        .replace(/\\/g, "/")
        .replace(/\/$/, ""),
    );
  for (const root of roots) {
    const windows = /^[A-Za-z]:\//.test(root);
    const matches = windows
      ? path.toLowerCase().startsWith(`${root.toLowerCase()}/`)
      : path.startsWith(`${root}/`);
    if (!matches) continue;
    const relative = path.slice(root.length + 1);
    if (
      !relative ||
      relative.split("/").some((part) => part === "..") ||
      relative.includes(":") ||
      relative.includes("\0")
    )
      break;
    return relative;
  }
  throw new Error("Media path is outside the bound workspace");
}

/** Recover selected POSIX files even when a media renderer already resolved their URL. */
export function workspaceMediaSource(
  source: string | undefined,
  binding: WorkspaceMediaBinding | null,
): string | undefined {
  const selection =
    binding &&
    !binding.cloud &&
    binding.selection?.machineId === binding.machineId
      ? binding.selection
      : null;
  if (!source || !selection || !selection.path.startsWith("/")) return source;
  const root = selection.path.replace(/\/$/, "") + "/";
  for (const prefix of [root, getFullUrl(root)]) {
    if (!prefix || !source.startsWith(prefix)) continue;
    const path = root + source.slice(prefix.length);
    const file = new URL("file:///");
    file.pathname = path;
    return file.href;
  }
  return source;
}
