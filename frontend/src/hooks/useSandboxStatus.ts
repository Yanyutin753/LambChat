// 本地沙箱 daemon 在线状态：全局单例 store（sandboxStatusStore）的薄壳。
//
// 历史演进：最初每个 hook 实例独立轮询（设置页+聊天区同挂 = 6 请求/10s），
// 现收敛为全 App 一个轮询源——订阅引用计数启动/停止，WS presence 推送直达
// 更新，WS 健康时轮询降频为 60s 对账、断线回升 10s；后台 tab 暂停打点。
// 对外 API 形状不变（status/statusError/online/machines/defaultMachineId/
// currentMachineId/refresh），既有消费方零改动。
import { useCallback, useEffect, useSyncExternalStore } from "react";
import type { SandboxMachine, SandboxStatus } from "../services/api/sandbox";
import {
  attachSandboxStatusStore,
  getSandboxStatusStoreState,
  isSandboxOnline,
  refreshSandboxStatus,
  subscribeSandboxStatus,
  type SandboxStatusError,
} from "../stores/sandboxStatusStore";

export {
  SANDBOX_STATUS_REFRESH_EVENT,
} from "../stores/sandboxStatusStore";
export type { SandboxStatusError } from "../stores/sandboxStatusStore";
export { SANDBOX_ONLINE_CHANGED_EVENT } from "../components/layout/AppContent/useAgentOptions";

const EMPTY_SUBSCRIBE = () => () => {};

export interface UseSandboxStatusOptions {
  /**
   * 订阅门控：false 时不订阅 store、不参与轮询引用计数，返回空占位状态
   * （RunModePopover 这类仅展开时展示状态点的消费方传 `enabled: open`；
   * 聊天输入区等常驻消费方保持默认 true）。false→true 切换时立即重订阅，
   * 首个订阅会触发一次共享刷新。
   */
  enabled?: boolean;
}

export function useSandboxStatus(options?: UseSandboxStatusOptions): {
  status: SandboxStatus | null;
  statusError: SandboxStatusError;
  online: boolean;
  machines: SandboxMachine[];
  defaultMachineId: string | null;
  /** 本机 machine_id（壳内）；web 端 null，用于"当前设备"标识。 */
  currentMachineId: string | null;
  refresh: () => void;
} {
  const enabled = options?.enabled ?? true;

  useEffect(() => {
    if (!enabled) return;
    return attachSandboxStatusStore();
  }, [enabled]);

  const state = useSyncExternalStore(
    enabled ? subscribeSandboxStatus : EMPTY_SUBSCRIBE,
    getSandboxStatusStoreState,
  );

  const refresh = useCallback(() => {
    void refreshSandboxStatus();
  }, []);

  if (!enabled) {
    return {
      status: null,
      statusError: null,
      online: false,
      machines: [],
      defaultMachineId: null,
      currentMachineId: null,
      refresh,
    };
  }

  return {
    status: state.status,
    statusError: state.statusError,
    online: isSandboxOnline(state),
    machines: state.machines,
    defaultMachineId: state.defaultMachineId,
    currentMachineId: state.currentMachineId,
    refresh,
  };
}

/** 配对/重启/策略写盘完成后派发，store 收到即共享刷新一次。 */
export function notifySandboxStatusRefresh() {
  window.dispatchEvent(new Event("sandbox-status-refresh"));
}
