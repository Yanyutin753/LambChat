/**
 * LambChat 本地沙箱 —— Tauri 壳 invoke 封装。
 *
 * 仅在桌面壳（Tauri）内可用；纯网页环境调用会抛出明确错误，
 * 由调用方降级（隐藏入口或展示"需要桌面端"提示）。
 *
 * 注意：`@tauri-apps/api/core` 只在壳内存在注入，这里用动态 import
 * 避免网页构建期解析失败。
 */
import { isNativeAppRuntime } from "../api/config";

/** 当前是否运行在桌面壳内（复用运行时探测，不缓存以便测试注入）。 */
export function isShellAvailable(): boolean {
  return isNativeAppRuntime();
}

async function invokeInShell<T>(
  command: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!isShellAvailable()) {
    throw new Error(
      "sandboxShell: this API is only available inside the LambChat desktop shell",
    );
  }
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<T>(command, args);
}

export interface SavePairingOptions {
  /** 服务端地址，如 http://127.0.0.1:8000。 */
  serverUrl: string;
  /** 配对得到的 PAT。 */
  pat: string;
  /** 确认策略：all | commands | none。 */
  confirmPolicy: string;
}

/** 写入配对凭据（~/.lambchat/pat）与 daemon 配置（~/.lambchat/sandbox.json）。 */
export function savePairing(opts: SavePairingOptions): Promise<void> {
  return invokeInShell("save_pairing", {
    serverUrl: opts.serverUrl,
    pat: opts.pat,
    confirmPolicy: opts.confirmPolicy,
  }).then(() => undefined);
}

/** 重启托管的 daemon（stop → start）。 */
export function restartDaemon(): Promise<void> {
  return invokeInShell("restart_daemon").then(() => undefined);
}

/** 查询 daemon 进程状态：running | stopped | unsupported。 */
export async function daemonProcessStatus(): Promise<string> {
  return invokeInShell<string>("daemon_process_status");
}

/**
 * 打开本地目录（仅限 ~/.lambchat/workspaces 与 ~/.lambchat/audit，
 * Rust 侧做白名单校验）。
 */
export function openLocalPath(path: string): Promise<void> {
  return invokeInShell("open_local_path", { path }).then(() => undefined);
}
