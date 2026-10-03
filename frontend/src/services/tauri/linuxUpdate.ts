/**
 * Linux 桌面端更新安装 —— Tauri 壳 invoke 封装。
 *
 * 对应 Rust 侧 linux_update.rs：安装来源检测（AppImage / deb / rpm /
 * unknown）、「缓存下载 deb/rpm + pkcon/pkexec 提权安装」。仅桌面壳内
 * 可用，非壳环境由调用方降级（null / 抛错）。
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
 * 下载 deb/rpm 更新包到版本化缓存（Rust 侧 `~/.cache/lambchat/updates/`，
 * `.part` 原子落盘——终名文件存在即完整包）。缓存命中（该版本已下载过）
 * 不发网络请求、直接推终值进度，返回 false；真实下载返回 true。
 * 进度经 linux-update-progress 事件推送（subscribeLinuxUpdateProgress）。
 */
export function downloadLinuxPackage(
  url: string,
  assetName: string,
): Promise<boolean> {
  return invokeInShell("download_linux_package", { url, assetName });
}

/**
 * 从缓存安装 deb/rpm 更新包（pkcon → pkexec apt|dnf → dpkg/rpm 三级回退，
 * 成功后 Rust 清空缓存；调用方随后 relaunch 进新版）。
 * 包未在缓存中时抛错——安装前先走 downloadLinuxPackage。
 */
export function installLinuxPackage(
  assetName: string,
  kind: "deb" | "rpm",
): Promise<void> {
  return invokeInShell("install_linux_package", {
    assetName,
    kind,
  }).then(() => undefined);
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
