/**
 * 桌面双栏壳的平台判定与共享常量（非组件导出独立成文件，
 * 保 react-refresh 边界）。
 */

import { resolveTitlebarOs } from "../TitleBar/titlebarPlatform";
import { isShellAvailable } from "../../../services/tauri/sandboxShell";

/** 侧栏搜索按钮 → SessionSidebar 内 SearchDialog 的事件桥。 */
export const DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT =
  "lambchat:desktop-sidebar-open-search";

/** TitleBar 折叠/展开按钮 → 桌面壳的事件桥（TitleBar 不感知折叠状态）。 */
export const DESKTOP_SIDEBAR_TOGGLE_EVENT = "lambchat:desktop-sidebar-toggle";

/** TitleBar 新建对话按钮 → 桌面壳的事件桥（复用 AppContent 的 onNewSession）。 */
export const DESKTOP_SIDEBAR_NEW_SESSION_EVENT =
  "lambchat:desktop-sidebar-new-session";

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
