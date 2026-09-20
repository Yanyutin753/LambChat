/**
 * Stream reconcile for useAgent hook
 *
 * 回前台/网络恢复/任务完成通知时的对流对账：
 * - 流式中的 run：查服务端状态。已终结 → 本地落定（缺内容则重载历史）；
 *   仍在跑但传输层死亡/可疑 → 立即强制重连（不等指数退避）。
 * - 空闲会话：比对服务端 current_run_id，发现对话在其他端推进过 → 重载历史。
 * - 看门狗：页面可见但流长时间静默（半开死连接）时主动对账。
 */

import { useCallback, useEffect, useRef } from "react";
import { sessionApi } from "../../services/api";
import type { ConnectionStatus, Message } from "../../types";
import {
  clearReconnectTimeout,
  connectToSSE,
  reconnectSSE,
  settleRemotelyTerminatedRun,
  type SSEConnectionContext,
} from "./sseConnection";

/** 服务端心跳间隔 5s（dual_writer `_SSE_HEARTBEAT_INTERVAL_SECONDS`，
 * 与 xread block 同频）；3 个周期无任何事件视为流静默（半开死连接），
 * 看门狗 5s 一跳 → 最坏 ~20s 自愈。 */
export const STREAM_STALE_THRESHOLD_MS = 15_000;

/** 前台对账最小间隔：visibilitychange/focus/online 常连发，避免抖动 */
export const RECONCILE_MIN_INTERVAL_MS = 3_000;

const WATCHDOG_INTERVAL_MS = 5_000;

export function isStreamActivityStale(
  lastActivityAt: number | null,
  now: number,
): boolean {
  if (lastActivityAt == null) return false;
  return now - lastActivityAt > STREAM_STALE_THRESHOLD_MS;
}

export function shouldReloadOpenSession(input: {
  serverRunId: string | null;
  localRunId: string | null;
}): boolean {
  if (!input.serverRunId) return false;
  return input.serverRunId !== input.localRunId;
}

export type StreamReconcileContext = SSEConnectionContext & {
  sessionIdRef: React.MutableRefObject<string | null>;
  currentRunIdRef: React.MutableRefObject<string | null>;
  isReconnectFromHistoryRef: React.MutableRefObject<boolean>;
};

/**
 * 解析当前流式气泡 ID：与 reconnectSSE 同语义（HITL 续跑换 run id 时
 * 复用最后一条助手消息，续跑事件落在同一气泡里）。
 */
function resolveStreamingMessageId(ctx: StreamReconcileContext): string | null {
  if (ctx.streamingMessageIdRef.current) return ctx.streamingMessageIdRef.current;
  return (
    [...ctx.messagesRef.current]
      .reverse()
      .find((message: Message) => message.role === "assistant")?.id ?? null
  );
}

/**
 * 流式中的 run 对账。返回 true 表示 run 仍在服务端执行。
 * 已终结时本地落定（缺内容经 onStaleRunStateDetected 重载历史）；
 * 仍在跑但传输层不健康（断开/重连中/静默）时立即强制重连。
 */
export async function reconcileActiveStream(
  ctx: StreamReconcileContext,
  opts: { connectionStatus?: ConnectionStatus } = {},
): Promise<boolean> {
  const currentSessId = ctx.sessionIdRef.current;
  const currentRId = ctx.currentRunIdRef.current;
  if (!currentSessId || !currentRId) return false;
  const currentMsgId = resolveStreamingMessageId(ctx) ?? currentRId;

  let remoteTerminal = false;
  try {
    const statusData = await sessionApi.getStatus(currentSessId, currentRId);
    if (statusData.status === "completed" || statusData.status === "error") {
      remoteTerminal = true;
    }
  } catch (err) {
    console.error("[SSE Reconcile] Failed to check task status:", err);
    // 状态探测失败（网络刚恢复等）：交给原指数退避重连路径
    await reconnectSSE(ctx);
    return true;
  }

  if (remoteTerminal) {
    console.log("[SSE Reconcile] Run finished remotely, settling locally");
    settleRemotelyTerminatedRun(ctx, currentRId, currentMsgId);
    return false;
  }

  const status = opts.connectionStatus;
  const stale = isStreamActivityStale(ctx.lastStreamActivityAtRef.current, Date.now());
  // connecting 视为在建中（发送路径刚发起），不打断；静默阈值兜底
  const healthy =
    (status === "connected" && !stale) || (status === "connecting" && !stale);
  if (healthy) return true;

  console.log(
    `[SSE Reconcile] Live run but unhealthy transport (status=${status ?? "unknown"}, stale=${stale}); forcing reconnect`,
  );
  clearReconnectTimeout(ctx.reconnectTimeoutRef);
  if (ctx.abortControllerRef.current) {
    ctx.abortControllerRef.current.abort();
    ctx.abortControllerRef.current = null;
  }
  ctx.isConnectingRef.current = false;
  ctx.setConnectionStatus("reconnecting");
  ctx.isReconnectFromHistoryRef.current = true;
  if (currentMsgId) {
    await connectToSSE(currentSessId, currentRId, currentMsgId, ctx);
  }
  return true;
}

export interface ReconcileOpenSessionOptions {
  loadHistory: (targetSessionId: string) => Promise<unknown>;
  isSending: boolean;
  isLoadingHistory: boolean;
}

/**
 * 空闲会话对账：对话可能在其他端（网页/客户端）推进过——比对服务端
 * current_run_id，落后即重载历史（loadHistory 会顺带回放并接上活动流）。
 */
export async function reconcileOpenSession(
  ctx: StreamReconcileContext,
  opts: ReconcileOpenSessionOptions,
): Promise<void> {
  const currentSessId = ctx.sessionIdRef.current;
  if (!currentSessId) return;
  // 发送/加载在途时本地状态即将被新内容取代，跳过避免覆写
  if (opts.isSending || opts.isLoadingHistory) return;

  let sessionData: Awaited<ReturnType<typeof sessionApi.get>> | null = null;
  try {
    sessionData = await sessionApi.get(currentSessId);
  } catch (err) {
    console.warn("[SSE Reconcile] Failed to fetch session for staleness check:", err);
    return;
  }
  if (!sessionData) return;

  const serverRunId =
    (sessionData.metadata?.current_run_id as string | undefined) || null;
  if (
    shouldReloadOpenSession({
      serverRunId,
      localRunId: ctx.currentRunIdRef.current,
    })
  ) {
    console.log(
      `[SSE Reconcile] Server moved on (server run=${serverRunId}); reloading history`,
    );
    await opts.loadHistory(currentSessId);
  }
}

export interface StreamReconcileOptions {
  createSSEContext: () => SSEConnectionContext;
  sessionIdRef: React.MutableRefObject<string | null>;
  currentRunIdRef: React.MutableRefObject<string | null>;
  isReconnectFromHistoryRef: React.MutableRefObject<boolean>;
  streamingMessageIdRef: React.MutableRefObject<string | null>;
  connectionStatus: ConnectionStatus;
  setConnectionStatus: (status: ConnectionStatus) => void;
  isSendingRef: React.MutableRefObject<boolean>;
  isLoadingHistoryRef: React.MutableRefObject<boolean>;
  loadHistoryRef: React.MutableRefObject<
    ((targetSessionId: string) => Promise<unknown>) | null
  >;
}

/**
 * Hook：前台/网络恢复/静默看门狗的流对账入口。
 * 返回 reconcile 函数（带 runId 时退化为原 reconnectSSE 语义，
 * 供 HITL 续跑等显式恢复调用）。
 */
export function useStreamReconcile(
  opts: StreamReconcileOptions,
): (runId?: string | null) => Promise<void> {
  const {
    createSSEContext,
    sessionIdRef,
    currentRunIdRef,
    isReconnectFromHistoryRef,
    streamingMessageIdRef,
    setConnectionStatus,
    isSendingRef,
    isLoadingHistoryRef,
    loadHistoryRef,
  } = opts;

  const connectionStatusRef = useRef(opts.connectionStatus);
  connectionStatusRef.current = opts.connectionStatus;
  const lastReconcileAtRef = useRef(0);
  const isReconcilingRef = useRef(false);

  const reconcile = useCallback(
    async (runId?: string | null): Promise<void> => {
      const ctx: StreamReconcileContext = {
        ...createSSEContext(),
        sessionIdRef,
        currentRunIdRef,
        isReconnectFromHistoryRef,
      };
      if (runId) {
        await reconnectSSE(ctx, runId);
        return;
      }
      if (isReconcilingRef.current) return;
      const now = Date.now();
      if (now - lastReconcileAtRef.current < RECONCILE_MIN_INTERVAL_MS) return;
      lastReconcileAtRef.current = now;
      isReconcilingRef.current = true;
      try {
        const streaming =
          Boolean(sessionIdRef.current) &&
          Boolean(currentRunIdRef.current) &&
          Boolean(streamingMessageIdRef.current);
        let runStillActive = false;
        if (streaming) {
          runStillActive = await reconcileActiveStream(ctx, {
            connectionStatus: connectionStatusRef.current,
          });
        }
        if (!runStillActive) {
          await reconcileOpenSession(ctx, {
            loadHistory: (targetSessionId) =>
              loadHistoryRef.current?.(targetSessionId) ??
              Promise.resolve(null),
            isSending: isSendingRef.current,
            isLoadingHistory: isLoadingHistoryRef.current,
          });
        }
      } finally {
        isReconcilingRef.current = false;
      }
    },
    [
      createSSEContext,
      sessionIdRef,
      currentRunIdRef,
      isReconnectFromHistoryRef,
      streamingMessageIdRef,
      isSendingRef,
      isLoadingHistoryRef,
      loadHistoryRef,
    ],
  );

  const reconcileRef = useRef(reconcile);
  reconcileRef.current = reconcile;

  // visibilitychange/focus/online 触发对账；offline 只标记断开
  useEffect(() => {
    const maybeReconcile = () => {
      if (document.visibilityState === "visible") {
        void reconcileRef.current();
      }
    };
    const handleFocus = () => {
      void reconcileRef.current();
    };
    const handleOnline = () => {
      void reconcileRef.current();
    };
    const handleOffline = () => {
      setConnectionStatus("disconnected");
    };

    document.addEventListener("visibilitychange", maybeReconcile);
    window.addEventListener("focus", handleFocus);
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      document.removeEventListener("visibilitychange", maybeReconcile);
      window.removeEventListener("focus", handleFocus);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, [setConnectionStatus]);

  // 看门狗：页面可见、流声称在线但长时间无事件 → 对账（半开死连接自愈）
  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState !== "visible") return;
      if (connectionStatusRef.current !== "connected") return;
      if (!sessionIdRef.current || !currentRunIdRef.current) return;
      if (!streamingMessageIdRef.current) return;
      void reconcileRef.current();
    }, WATCHDOG_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [sessionIdRef, currentRunIdRef, streamingMessageIdRef]);

  return reconcile;
}
