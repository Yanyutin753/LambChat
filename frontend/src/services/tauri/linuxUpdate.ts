/**
 * Linux 桌面端更新安装 —— Tauri 壳 invoke 封装。
 *
 * 对应 Rust 侧 linux_update.rs：安装来源检测（AppImage / deb / rpm /
 * unknown）与「下载 deb/rpm + pkexec 提权安装」。仅桌面壳内可用，
 * 非壳环境由调用方降级（null / 抛错）。
 */

import type { LinuxInstallSource } from "../../types";
import { invokeInShell, isShellAvailable } from "./sandboxShell";

export type { LinuxInstallSource };

/** get_linux_install_source 返回：来源 + 资产命名 arch 段。 */
export interface LinuxInstallInfo {
  source: LinuxInstallSource;
  arch: string | null;
}

/** 检测当前安装来源（非壳环境 null；invoke 失败也 null 走 unknown 兜底）。 */
export async function getLinuxInstallInfo(): Promise<LinuxInstallInfo | null> {
  if (!isShellAvailable()) return null;
  try {
    return await invokeInShell<LinuxInstallInfo>("get_linux_install_source");
  } catch {
    return null;
  }
}

/**
 * 下载 deb/rpm 安装包并以 pkexec 提权安装（成功后调用方 relaunch）。
 * 进度经 linux-update-progress 事件推送（subscribeLinuxUpdateProgress）。
 */
export function installLinuxPackage(
  url: string,
  kind: "deb" | "rpm",
): Promise<void> {
  return invokeInShell("install_linux_package", { url, kind }).then(
    () => undefined,
  );
}

export interface LinuxUpdateProgressEvent {
  downloaded: number;
  contentLength: number;
}

/**
 * 订阅 deb/rpm 下载进度事件（Tauri event `linux-update-progress`）。
 * 非壳环境返回 null（调用方不订阅）；返回的取消函数幂等。
 */
export async function subscribeLinuxUpdateProgress(
  listener: (event: LinuxUpdateProgressEvent) => void,
): Promise<(() => void) | null> {
  if (!isShellAvailable()) {
    return null;
  }
  const { listen } = await import("@tauri-apps/api/event");
  const unlisten = await listen<LinuxUpdateProgressEvent>(
    "linux-update-progress",
    (event) => listener(event.payload),
  );
  let cancelled = false;
  return () => {
    if (cancelled) return;
    cancelled = true;
    void unlisten();
  };
}
