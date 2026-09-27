/**
 * 桌面双栏壳的平台判定与共享常量（非组件导出独立成文件，
 * 保 react-refresh 边界）。
 */

import { resolveTitlebarOs } from "../TitleBar/titlebarPlatform";
import { isShellAvailable } from "../../../services/tauri/sandboxShell";

/** ActivityRail 搜索按钮 → SessionSidebar 内 SearchDialog 的事件桥。 */
export const DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT =
  "lambchat:desktop-sidebar-open-search";

export type DesktopSidebarView = "chat" | "files";

/** Tauri 桌面壳环境（web/移动端 false）。 */
export function isDesktopShell(): boolean {
  if (typeof window === "undefined") return false;
  return resolveTitlebarOs(window) !== null;
}

/** 与 isDesktopShell 的区别：包含非桌面 Tauri 场景的保守判定（壳可用即壳）。 */
export function shouldUseDesktopShellGate(): boolean {
  return isShellAvailable() && isDesktopShell();
}
