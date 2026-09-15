/**
 * 自绘标题栏的平台判定（仅桌面 Tauri 壳生效）。
 *
 * - Windows / Linux：`decorations: false`，完全自绘（品牌 + 导航 + 窗口控制）
 * - macOS：`titleBarStyle: Overlay`，原生红绿灯叠加在标题栏行左侧，
 *   自绘部分不含品牌与窗口控制按钮
 * - Web / PWA / Capacitor 移动端：不出标题栏
 */

export type DesktopOs = "windows" | "linux" | "mac";

/** 从 WebView UA 识别桌面操作系统；移动端与未知 UA 返回 null */
export function detectDesktopOs(userAgent: string): DesktopOs | null {
  // Android WebView UA 含 "Linux; Android"（iPad 桌面态 UA 含 Macintosh），
  // 它们都跑 Capacitor 而非 Tauri，但判定函数自身先排除避免误用
  if (/android|iphone|ipad|ipod/i.test(userAgent)) return null;
  if (/windows nt/i.test(userAgent)) return "windows";
  if (/macintosh|mac os x/i.test(userAgent)) return "mac";
  if (/linux/i.test(userAgent)) return "linux";
  return null;
}

/** Tauri 运行时 + 桌面 OS 同时满足时才渲染自绘标题栏 */
export function resolveTitlebarOs(win: {
  __TAURI__?: unknown;
  __TAURI_INTERNALS__?: unknown;
  navigator?: { userAgent?: string };
}): DesktopOs | null {
  if (!win.__TAURI__ && !win.__TAURI_INTERNALS__) return null;
  return detectDesktopOs(win.navigator?.userAgent ?? "");
}
