/**
 * LambChat 本地沙箱 —— Tauri 壳 invoke 封装。
 *
 * 仅在桌面壳（Tauri）内可用；纯网页环境调用会抛出明确错误，
 * 由调用方降级（隐藏入口或展示"需要桌面端"提示）。
 *
 * 注意：`@tauri-apps/api/core` 只在壳内存在注入，这里用动态 import
 * 避免网页构建期解析失败。
 */

interface ShellLocationLike {
  protocol?: string;
  hostname?: string;
}

interface ShellGlobalLike {
  __TAURI__?: unknown;
  __TAURI_INTERNALS__?: unknown;
}

/**
 * 当前是否运行在 Tauri 桌面壳内。
 *
 * 只认 Tauri 标记（`__TAURI__` / `__TAURI_INTERNALS__` 注入，或
 * `tauri:` 协议 / `tauri.localhost` origin），不能复用 isNativeAppRuntime()——
 * 后者对 Capacitor 移动端同样返回 true，会导致移动端渲染壳内配对表单，
 * 提交后服务端已铸出 PAT 而 savePairing invoke 必然失败（PAT 泄漏累积）。
 * 不缓存结果以便测试注入。
 */
export function isShellAvailable(): boolean {
  const globalObject =
    typeof globalThis !== "undefined"
      ? (globalThis as unknown as ShellGlobalLike)
      : null;
  if (globalObject?.__TAURI__ || globalObject?.__TAURI_INTERNALS__) {
    return true;
  }

  const location: ShellLocationLike | null | undefined =
    typeof window !== "undefined" ? window.location : null;
  const protocol = location?.protocol?.toLowerCase() || "";
  const hostname = location?.hostname?.toLowerCase() || "";
  return protocol === "tauri:" || hostname === "tauri.localhost";
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
  /** 配对回执（PAT 记录 id），落盘 sandbox.json 供回读/取消配对。 */
  patId?: string;
}

/** 写入配对凭据（~/.lambchat/pat）与 daemon 配置（~/.lambchat/sandbox.json）。 */
export function savePairing(opts: SavePairingOptions): Promise<void> {
  const args: Record<string, unknown> = {
    serverUrl: opts.serverUrl,
    pat: opts.pat,
    confirmPolicy: opts.confirmPolicy,
  };
  if (opts.patId !== undefined) {
    args.patId = opts.patId;
  }
  return invokeInShell("save_pairing", args).then(() => undefined);
}

/**
 * 只写确认策略（sandbox.json 的 confirm_policy，保留其余字段）。
 * 策略切换专用——不重铸 PAT、不碰凭据文件，避免永久凭据累积。
 */
export function writeConfirmPolicy(policy: string): Promise<void> {
  return invokeInShell("write_confirm_policy", { policy }).then(() => undefined);
}

/**
 * 取消配对：停 daemon + 删 ~/.lambchat/pat + 移除 sandbox.json 的 pat_id
 * （服务端 PAT 吊销由调用方先用 readPairingPat 的结果调自删端点完成）。
 */
export function clearPairing(): Promise<void> {
  return invokeInShell("clear_pairing").then(() => undefined);
}

/** 读回配对 PAT（未配对时 null）。 */
export function readPairingPat(): Promise<string | null> {
  return invokeInShell<string | null>("read_pairing_pat");
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
