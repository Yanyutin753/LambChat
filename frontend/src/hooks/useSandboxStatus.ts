// 本地沙箱 daemon 在线状态：挂载拉取 + 10s 轮询 + 事件立即刷新，失败静默
// （`enabled: false` 可整体门控，见 UseSandboxStatusOptions）。
// 配对/重启完成后由 LocalSandboxSection 派发 sandbox-status-refresh 立即重拉；
// 聊天输入区的沙箱选择器也消费该状态做动态适配（纯 web 仅在线时渲染本地档）。
import { useCallback, useEffect, useRef, useState } from "react";
import {
  sandboxApi,
  sandboxApiMachines,
  type SandboxMachine,
  type SandboxStatus,
} from "../services/api/sandbox";

const REFRESH_INTERVAL_MS = 10 * 1000;
export const SANDBOX_STATUS_REFRESH_EVENT = "sandbox-status-refresh";

/** 状态请求失败原因：401（会话失效）与普通失败区分，设置页据此走配对引导。 */
export type SandboxStatusError = "unauthorized" | "failed" | null;

function toStatusError(err: unknown): SandboxStatusError {
  const withStatus = err as { status?: number };
  if (withStatus?.status === 401) return "unauthorized";
  if ((err as Error)?.message === "Unauthorized") return "unauthorized";
  return "failed";
}

export interface UseSandboxStatusOptions {
  /**
   * 轮询门控（M4 T8）：false 时不拉取、不轮询、不响应刷新事件。
   * 默认 true（选择器等常驻消费方保持 always-on）；RunModePopover 这类
   * 仅在浮层展开时才展示状态点的消费方传 `enabled: open`，关闭期间
   * 不再空转 10s 轮询。false→true 切换时立即补拉一次（effect 重跑）。
   */
  enabled?: boolean;
}

export function useSandboxStatus(
  options?: UseSandboxStatusOptions,
): {
  status: SandboxStatus | null;
  statusError: SandboxStatusError;
  online: boolean;
  machines: SandboxMachine[];
  defaultMachineId: string | null;
  refresh: () => void;
} {
  const enabled = options?.enabled ?? true;
  const [status, setStatus] = useState<SandboxStatus | null>(null);
  const [statusError, setStatusError] = useState<SandboxStatusError>(null);
  const [machines, setMachines] = useState<SandboxMachine[]>([]);
  const [defaultMachineId, setDefaultMachineId] = useState<string | null>(null);
  const inFlight = useRef(false);
  const pending = useRef(false);

  const fetchStatus = useCallback(async () => {
    // 在途去重：撞上的刷新记一笔，结束后补拉，不并发不丢
    if (inFlight.current) {
      pending.current = true;
      return;
    }
    inFlight.current = true;
    try {
      const data = await sandboxApi.getStatus();
      setStatus(data);
      setStatusError(null);
    } catch (err) {
      // 静默失败：保留上次状态，仅记录错误类别
      setStatusError(toStatusError(err));
    } finally {
      inFlight.current = false;
      if (pending.current) {
        pending.current = false;
        void fetchStatus();
      }
    }
  }, []);

  // 机器列表与状态同一节拍拉取（多机 daemon）；失败静默——单机/旧后端用户
  // 的机器选择器自然隐藏，不影响既有 status 消费方。
  const fetchMachines = useCallback(async () => {
    try {
      const data = await sandboxApiMachines.listMachines();
      setMachines(data.machines);
      setDefaultMachineId(data.default_machine_id);
    } catch {
      // 静默：machines 是附加能力，不污染 status 错误通道
    }
  }, []);

  useEffect(() => {
    if (!enabled) return;
    fetchStatus();
    fetchMachines();
    const timer = setInterval(() => {
      fetchStatus();
      fetchMachines();
    }, REFRESH_INTERVAL_MS);
    const onRefresh = () => {
      fetchStatus();
      fetchMachines();
    };
    window.addEventListener(SANDBOX_STATUS_REFRESH_EVENT, onRefresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener(SANDBOX_STATUS_REFRESH_EVENT, onRefresh);
    };
  }, [fetchStatus, fetchMachines, enabled]);

  return {
    status,
    statusError,
    online: !!status?.online,
    machines,
    defaultMachineId,
    refresh: fetchStatus,
  };
}

/** 配对/重启/策略写盘完成后派发，所有 useSandboxStatus 实例立即重拉。 */
export function notifySandboxStatusRefresh() {
  window.dispatchEvent(new Event(SANDBOX_STATUS_REFRESH_EVENT));
}
