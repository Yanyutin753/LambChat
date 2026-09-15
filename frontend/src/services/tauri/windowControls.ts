/**
 * 自绘标题栏的窗口控制封装（Tauri 壳专用）。
 *
 * `@tauri-apps/api/window` 只在壳内可注入，这里统一动态 import，
 * 网页构建期不解析、非壳环境调用静默失败（标题栏本身不会在网页渲染）。
 * 组件测试 mock 本模块而非底层 API。
 */

type WindowMethod = "minimize" | "toggleMaximize" | "close";

async function invokeWindowMethod(method: WindowMethod): Promise<void> {
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    await getCurrentWindow()[method]();
  } catch {
    // 窗口操作失败静默（权限缺失等由壳层日志暴露）
  }
}

export function minimizeWindow(): Promise<void> {
  return invokeWindowMethod("minimize");
}

export function toggleMaximizeWindow(): Promise<void> {
  return invokeWindowMethod("toggleMaximize");
}

export function closeWindow(): Promise<void> {
  return invokeWindowMethod("close");
}

/** 查询最大化态；查询失败（非壳/权限）返回 null，调用方保持现值 */
export async function queryWindowMaximized(): Promise<boolean | null> {
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    return await getCurrentWindow().isMaximized();
  } catch {
    return null;
  }
}

/** 订阅窗口尺寸变化（最大化切换）；不可用时返回 no-op 退订 */
export async function subscribeWindowResized(
  handler: () => void,
): Promise<() => void> {
  try {
    const { getCurrentWindow } = await import("@tauri-apps/api/window");
    return await getCurrentWindow().onResized(handler);
  } catch {
    return () => undefined;
  }
}
