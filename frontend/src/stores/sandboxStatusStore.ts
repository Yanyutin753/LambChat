/**
 * 沙箱 daemon 状态全局单例 store：全 App 一个轮询源 + WS presence 推送直更。
 *
 * - 订阅引用计数：首个 attach 启动刷新器（首拉 + 定时对账），归零停止；
 * - WS 健康时节拍 60s（presence 推送是事实的加速信号，轮询只做对账兜底），
 *   WS 断开回落 10s；
 * - visibilitychange：后台暂停打点，回前台立即补拉；
 * - presence 快照（`applySandboxPresence`）直接更新 machines/默认机，旧
 *   revision 丢弃；离线→在线翻转派发 `SANDBOX_ONLINE_CHANGED_EVENT`
 *   （默认本地档逻辑据此自动切档）。
 */

import { createSingletonStore } from "../components/chat/ChatMessage/items/createSingletonStore";
import { SANDBOX_ONLINE_CHANGED_EVENT } from "../components/layout/AppContent/useAgentOptions";
import {
  sandboxApi,
  sandboxApiMachines,
  type SandboxMachine,
  type SandboxStatus,
} from "../services/api/sandbox";
import { readMachineId } from "../services/tauri/sandboxShell";

export const SANDBOX_STATUS_REFRESH_EVENT = "sandbox-status-refresh";

/** 状态请求失败原因：401（会话失效）与普通失败区分，设置页据此走配对引导。 */
export type SandboxStatusError = "unauthorized" | "failed" | null;

function toStatusError(err: unknown): SandboxStatusError {
  const withStatus = err as { status?: number };
  if (withStatus?.status === 401) return "unauthorized";
  if ((err as Error)?.message === "Unauthorized") return "unauthorized";
  return "failed";
}

const POLL_WS_HEALTHY_MS = 60 * 1000;
const POLL_WS_DOWN_MS = 10 * 1000;

export interface SandboxStatusStoreState {
  status: SandboxStatus | null;
  statusError: SandboxStatusError;
  machines: SandboxMachine[];
  defaultMachineId: string | null;
  /** 本机 machine_id（壳内读 ~/.lambchat/sandbox.json）；web 端/未配对为 null。 */
  currentMachineId: string | null;
  wsHealthy: boolean;
  lastSyncedAt: number | null;
}

const store = createSingletonStore<SandboxStatusStoreState>({
  status: null,
  statusError: null,
  machines: [],
  defaultMachineId: null,
  currentMachineId: null,
  wsHealthy: false,
  lastSyncedAt: null,
});

let refCount = 0;
let timer: ReturnType<typeof setInterval> | null = null;
let inFlight = false;
let pendingRefresh = false;
let lastPresenceRevision: number | null = null;
let wasOnline = false;

export function getSandboxStatusStoreState(): SandboxStatusStoreState {
  return store.get();
}

export function subscribeSandboxStatus(listener: () => void): () => void {
  return store.subscribe(listener);
}

/** 在线判定（双保险）：/status 在线，或机器列表里任一机器在线。 */
export function isSandboxOnline(state: SandboxStatusStoreState): boolean {
  return !!state.status?.online || state.machines.some((m) => m.online !== false);
}

function emitOnlineTransition(): boolean {
  const online = isSandboxOnline(store.get());
  const transitioned = online && !wasOnline;
  if (transitioned) {
    window.dispatchEvent(new Event(SANDBOX_ONLINE_CHANGED_EVENT));
  }
  wasOnline = online;
  return transitioned;
}

export async function refreshSandboxStatus(): Promise<void> {
  // 在途去重：撞上的刷新记一笔，结束后补拉，不并发不丢
  if (inFlight) {
    pendingRefresh = true;
    return;
  }
  inFlight = true;
  try {
    const [statusResult, machinesResult] = await Promise.allSettled([
      sandboxApi.getStatus(),
      sandboxApiMachines.listMachines(),
    ]);
    const next: Partial<SandboxStatusStoreState> = {};
    // 各自防御非法 fulfilled 值（undefined/形态不符）：单边脏数据不打崩整轮刷新
    if (statusResult.status === "fulfilled") {
      const value = statusResult.value as SandboxStatus | null | undefined;
      if (value && typeof value === "object") {
        next.status = value;
        next.statusError = null;
      }
    } else {
      // 静默失败：保留上次状态，仅记录错误类别
      next.statusError = toStatusError(statusResult.reason);
    }
    if (machinesResult.status === "fulfilled") {
      const value = machinesResult.value as
        | { machines?: SandboxMachine[]; default_machine_id?: string | null }
        | null
        | undefined;
      if (value && typeof value === "object") {
        next.machines = Array.isArray(value.machines) ? value.machines : [];
        next.defaultMachineId = value.default_machine_id ?? null;
      }
    }
    next.lastSyncedAt = Date.now();
    store.set({ ...store.get(), ...next });
    emitOnlineTransition();
    // 本机身份对账（壳内本地文件读，随刷新节拍自愈：daemon 首启落盘后下一轮带上）
    void syncCurrentMachineId();
  } finally {
    inFlight = false;
    if (pendingRefresh) {
      pendingRefresh = false;
      void refreshSandboxStatus();
    }
  }
}

/**
 * 读本机 machine_id（read_machine_id invoke 读 ~/.lambchat/sandbox.json）：
 * 非壳环境/命令缺失/未配对均静默降级为无当前设备标识；值未变化不写 store，
 * 避免 60s 对账节拍引起订阅方无谓重渲染。
 */
async function syncCurrentMachineId(): Promise<void> {
  try {
    const id = await readMachineId();
    if (id && id !== store.get().currentMachineId) {
      store.set({ ...store.get(), currentMachineId: id });
    }
  } catch {
    // 非壳 / 旧壳未实现该命令 / 文件不可读：无当前设备标识，不阻塞刷新
  }
}

function currentIntervalMs(): number {
  return store.get().wsHealthy ? POLL_WS_HEALTHY_MS : POLL_WS_DOWN_MS;
}

function startTimer(): void {
  if (timer !== null) return;
  timer = setInterval(() => {
    void refreshSandboxStatus();
  }, currentIntervalMs());
}

function stopTimer(): void {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }
}

export function setSandboxWsHealthy(healthy: boolean): void {
  const prev = store.get().wsHealthy;
  store.set({ ...store.get(), wsHealthy: healthy });
  if (refCount > 0) {
    stopTimer();
    startTimer(); // 节拍切换（重设 interval）
  }
  if (healthy && !prev) {
    void refreshSandboxStatus(); // WS 恢复：立即对账一次
  }
}

interface PresenceMachineLike {
  machine_id?: unknown;
  name?: unknown;
  platform?: unknown;
  version?: unknown;
  confirm_policy?: unknown;
  online?: unknown;
  last_seen?: unknown;
}

export interface SandboxPresencePayload {
  machines?: PresenceMachineLike[];
  default_machine_id?: unknown;
  legacy_online?: unknown;
  revision?: unknown;
}

function sanitizePresenceMachines(
  raw: PresenceMachineLike[] | undefined,
): SandboxMachine[] | null {
  if (!Array.isArray(raw)) return null;
  const machines: SandboxMachine[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") return null;
    if (typeof item.machine_id !== "string" || !item.machine_id) return null;
    machines.push({
      machine_id: item.machine_id,
      name: typeof item.name === "string" ? item.name : item.machine_id,
      platform: typeof item.platform === "string" ? item.platform : "",
      version: typeof item.version === "string" ? item.version : "",
      confirm_policy:
        typeof item.confirm_policy === "string" ? item.confirm_policy : "",
      online: item.online !== false,
      last_seen: typeof item.last_seen === "number" ? item.last_seen : null,
    });
  }
  return machines;
}

export function applySandboxPresence(data: SandboxPresencePayload): void {
  if (!data || typeof data !== "object") return;
  if (typeof data.revision !== "number") return;
  if (
    lastPresenceRevision !== null &&
    data.revision <= lastPresenceRevision
  ) {
    return; // 乱序旧事件：丢弃
  }
  const machines = sanitizePresenceMachines(data.machines);
  if (machines === null) return; // 非法载荷：丢弃，等对账兜底
  lastPresenceRevision = data.revision;
  store.set({
    ...store.get(),
    machines,
    defaultMachineId:
      typeof data.default_machine_id === "string" ? data.default_machine_id : null,
  });
  const transitioned = emitOnlineTransition();
  // 仅离线→在线翻转时补拉一次 /status：确认策略等元数据跟进（presence 不携带）；
  // 持续在线的常规推送不再打 API（推送直达是对账的替代，不是触发器）
  if (transitioned) {
    void refreshSandboxStatus();
  }
}

let lastVisibility: string | null = null;

function onVisibilityChange(): void {
  const visibility = document.visibilityState;
  if (visibility === lastVisibility) return; // 只响应转换（部分浏览器重复派发）
  lastVisibility = visibility;
  if (visibility === "hidden") {
    stopTimer();
  } else if (refCount > 0) {
    void refreshSandboxStatus();
    stopTimer();
    startTimer();
  }
}

function onManualRefresh(): void {
  void refreshSandboxStatus();
}

export function attachSandboxStatusStore(): () => void {
  refCount += 1;
  if (refCount === 1) {
    void refreshSandboxStatus();
    startTimer();
    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener(SANDBOX_STATUS_REFRESH_EVENT, onManualRefresh);
  }
  return () => {
    refCount -= 1;
    if (refCount === 0) {
      stopTimer();
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener(SANDBOX_STATUS_REFRESH_EVENT, onManualRefresh);
    }
  };
}

/** 测试专用：清空单例状态与定时器（避免用例间泄漏）。 */
export function _resetSandboxStatusStoreForTests(): void {
  stopTimer();
  refCount = 0;
  inFlight = false;
  pendingRefresh = false;
  lastPresenceRevision = null;
  wasOnline = false;
  store.set({
    status: null,
    statusError: null,
    machines: [],
    defaultMachineId: null,
    currentMachineId: null,
    wsHealthy: false,
    lastSyncedAt: null,
  });
}
