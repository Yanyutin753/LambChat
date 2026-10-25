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
import { applyRecommendQuestionsToMessages } from "./recommendQuestionsUpdate";
import { sessionApi } from "../../services/api";
import type { ConnectionStatus, Message } from "../../types";
import {
  clearReconnectTimeout,
  connectToSSE,
  isTerminalRunStatus,
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
  if (ctx.streamingMessageIdRef.current)
    return ctx.streamingMessageIdRef.current;
  return (
    [...ctx.messagesRef.current]
      .reverse()
      .find(
        (message: Message) =>
          message.role === "assistant" && !message.metadata?.scheduledTaskId,
      )?.id ?? null
  );
}

/**
 * 流式中的 run 对账。返回 true 表示 run 仍在服务端执行。
 * 已终结时本地落定（缺内容经 onStaleRunStateDetected 重载历史）；
 * 仍在跑但传输层不健康（断开/重连中/静默）时立即强制重连。
 */
export async function reconcileActiveStream(
  ctx: StreamReconcileContext,
  opts: { connectionStatus?: ConnectionStatus; signal?: AbortSignal } = {},
): Promise<boolean> {
  const currentSessId = ctx.sessionIdRef.current;
  const currentRId = ctx.currentRunIdRef.current;
  if (!currentSessId || !currentRId) return false;
  const currentMsgId = resolveStreamingMessageId(ctx) ?? currentRId;

  const generation = ctx.sseGenerationRef.current;
  const isCurrentRun = () =>
    !opts.signal?.aborted &&
    ctx.sseGenerationRef.current === generation &&
    ctx.sessionIdRef.current === currentSessId &&
    ctx.currentRunIdRef.current === currentRId;
  let remoteTerminal = false;
  try {
    const statusData = await sessionApi.getStatus(currentSessId, currentRId, {
      signal: opts.signal,
    });
    if (isTerminalRunStatus(statusData.status)) {
      remoteTerminal = true;
    }
  } catch (err) {
    if (opts.signal?.aborted) return true;
    console.error("[SSE Reconcile] Failed to check task status:", err);
    // 状态探测失败（网络刚恢复等）：交给原指数退避重连路径
    if (!isCurrentRun()) return true;
    await reconnectSSE(ctx, undefined, opts.signal);
    return true;
  }

  if (!isCurrentRun()) return true;
  if (remoteTerminal) {
    console.log("[SSE Reconcile] Run finished remotely, settling locally");
    settleRemotelyTerminatedRun(ctx, currentRId, currentMsgId);
    return false;
  }

  const status = opts.connectionStatus;
  const stale = isStreamActivityStale(
    ctx.lastStreamActivityAtRef.current,
    Date.now(),
  );
  // connecting 视为在建中（发送路径刚发起），不打断；静默阈值兜底
  const healthy =
    (status === "connected" && !stale) || (status === "connecting" && !stale);
  if (healthy) return true;

  console.log(
    `[SSE Reconcile] Live run but unhealthy transport (status=${
      status ?? "unknown"
    }, stale=${stale}); forcing reconnect`,
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
    // SSE lives for the whole run; it must not hold the reconciliation lock.
    void connectToSSE(currentSessId, currentRId, currentMsgId, ctx).catch(
      (error) => {
        console.warn("[SSE Reconcile] Failed to reconnect stream:", error);
      },
    );
  }
  return true;
}

export interface ReconcileOpenSessionOptions {
  signal?: AbortSignal;
  loadHistory: (targetSessionId: string) => Promise<unknown>;
  targetRunId?: string | null;
  isSending: boolean;
  isLoadingHistory: boolean;
  isBusy?: () => boolean;
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
  const generation = ctx.sseGenerationRef.current;
  const localRunId = ctx.currentRunIdRef.current;

  let sessionData: Awaited<ReturnType<typeof sessionApi.get>> | null;
  try {
    sessionData = await sessionApi.get(currentSessId, { signal: opts.signal });
  } catch (err) {
    if (opts.signal?.aborted) return;
    console.warn(
      "[SSE Reconcile] Failed to fetch session for staleness check:",
      err,
    );
    return;
  }
  if (
    opts.signal?.aborted ||
    !sessionData ||
    ctx.sessionIdRef.current !== currentSessId ||
    ctx.currentRunIdRef.current !== localRunId ||
    ctx.sseGenerationRef.current !== generation ||
    opts.isBusy?.()
  )
    return;

  const serverRunId =
    (sessionData.metadata?.current_run_id as string | undefined) || null;
  const taskStatus = sessionData.metadata?.task_status;
  const missingReply =
    taskStatus === "completed" &&
    !ctx.messagesRef.current.some(
      (message) =>
        message.role === "assistant" && message.runId === serverRunId,
    );
  if (
    opts.targetRunId &&
    opts.targetRunId !== serverRunId &&
    taskStatus === "completed" &&
    !missingReply
  )
    return;
  if (
    shouldReloadOpenSession({
      serverRunId,
      localRunId: ctx.currentRunIdRef.current,
    }) ||
    (serverRunId &&
      !ctx.streamingMessageIdRef.current &&
      (taskStatus === "running" || missingReply))
  ) {
    console.log(
      `[SSE Reconcile] Server moved on (server run=${serverRunId}); reloading history`,
    );
    await opts.loadHistory(currentSessId);
    return;
  }

  // Recommendations finish independently; a missed WebSocket notification is not replayed.
  const reply = [...ctx.messagesRef.current]
    .reverse()
    .find(
      (message) =>
        message.role === "assistant" && message.runId === serverRunId,
    );
  if (
    taskStatus !== "completed" ||
    !serverRunId ||
    !reply ||
    reply.isStreaming ||
    reply.parts?.some(
      (part) =>
        part.type === "recommend_questions" && part.questions.length > 0,
    )
  )
    return;
  try {
    const { runs } = await sessionApi.getRuns(currentSessId, {
      limit: 1,
      signal: opts.signal,
    });
    const questions = runs.find((run) => run.run_id === serverRunId)
      ?.recommend_questions;
    if (
      !questions?.length ||
      opts.signal?.aborted ||
      opts.isBusy?.() ||
      ctx.sessionIdRef.current !== currentSessId ||
      ctx.currentRunIdRef.current !== localRunId ||
      ctx.sseGenerationRef.current !== generation
    )
      return;
    ctx.setMessages((previous) =>
      applyRecommendQuestionsToMessages(previous, serverRunId, questions),
    );
  } catch (error) {
    if (opts.signal?.aborted) return;
    console.warn("[SSE Reconcile] Failed to catch up recommendations:", error);
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
  submitInFlightRef?: React.MutableRefObject<boolean>;
  isLoadingHistoryRef: React.MutableRefObject<boolean>;
  loadHistoryRef: React.MutableRefObject<
    ((targetSessionId: string, targetRunId?: string) => Promise<unknown>) | null
  >;
  historyTargetRunIdRef?: React.MutableRefObject<string | null>;
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
    submitInFlightRef,
    isLoadingHistoryRef,
    loadHistoryRef,
    historyTargetRunIdRef,
  } = opts;

  const connectionStatusRef = useRef(opts.connectionStatus);
  connectionStatusRef.current = opts.connectionStatus;
  const lastReconcileAtRef = useRef(0);
  const reconcileControllerRef = useRef<AbortController | null>(null);
  const resumedRef = useRef<boolean | null>(null);
  const foregroundRefreshRef = useRef<{
    sessionId: string;
    runId: string | null;
  } | null>(null);

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
      const now = Date.now();
      if (reconcileControllerRef.current) {
        if (now - lastReconcileAtRef.current < STREAM_STALE_THRESHOLD_MS)
          return;
        reconcileControllerRef.current.abort();
      }
      if (now - lastReconcileAtRef.current < RECONCILE_MIN_INTERVAL_MS) return;
      lastReconcileAtRef.current = now;
      const controller = new AbortController();
      reconcileControllerRef.current = controller;
      try {
        const refresh = foregroundRefreshRef.current;
        if (refresh) {
          if (
            sessionIdRef.current !== refresh.sessionId ||
            (currentRunIdRef.current !== refresh.runId &&
              !isLoadingHistoryRef.current)
          ) {
            foregroundRefreshRef.current = null;
          } else if (!submitInFlightRef?.current) {
            const targetRunId = historyTargetRunIdRef?.current;
            const loaded = await loadHistoryRef.current?.(refresh.sessionId);
            if (controller.signal.aborted) return;
            if (loaded && foregroundRefreshRef.current === refresh) {
              foregroundRefreshRef.current = null;
              if (
                targetRunId &&
                sessionIdRef.current === refresh.sessionId &&
                historyTargetRunIdRef?.current === targetRunId &&
                !submitInFlightRef?.current
              ) {
                await loadHistoryRef.current?.(refresh.sessionId, targetRunId);
              }
            }
            return;
          } else {
            return;
          }
        }
        const streaming =
          Boolean(sessionIdRef.current) &&
          Boolean(currentRunIdRef.current) &&
          Boolean(streamingMessageIdRef.current);
        let runStillActive = false;
        if (streaming) {
          runStillActive = await reconcileActiveStream(ctx, {
            connectionStatus: connectionStatusRef.current,
            signal: controller.signal,
          });
        }
        if (!runStillActive && !controller.signal.aborted) {
          await reconcileOpenSession(ctx, {
            signal: controller.signal,
            loadHistory: async (targetSessionId) => {
              const targetRunId = historyTargetRunIdRef?.current;
              await loadHistoryRef.current?.(targetSessionId);
              if (
                targetRunId &&
                sessionIdRef.current === targetSessionId &&
                historyTargetRunIdRef?.current === targetRunId &&
                !isSendingRef.current
              ) {
                await loadHistoryRef.current?.(targetSessionId, targetRunId);
              }
            },
            targetRunId: historyTargetRunIdRef?.current,
            isSending: isSendingRef.current,
            isLoadingHistory: isLoadingHistoryRef.current,
            isBusy: () => isSendingRef.current || isLoadingHistoryRef.current,
          });
        }
      } finally {
        if (reconcileControllerRef.current === controller)
          reconcileControllerRef.current = null;
      }
    },
    [
      createSSEContext,
      sessionIdRef,
      currentRunIdRef,
      isReconnectFromHistoryRef,
      streamingMessageIdRef,
      isSendingRef,
      submitInFlightRef,
      isLoadingHistoryRef,
      loadHistoryRef,
      historyTargetRunIdRef,
    ],
  );

  const reconcileRef = useRef(reconcile);
  reconcileRef.current = reconcile;

  // visibilitychange/focus/online 触发对账；offline 只标记断开
  useEffect(() => {
    let wasHidden = document.visibilityState === "hidden";
    let lastResumeAt = -Infinity;
    const handlePause = () => {
      resumedRef.current = false;
      wasHidden = true;
      lastResumeAt = -Infinity;
    };
    const maybeReconcile = () => {
      if (document.visibilityState === "hidden") handlePause();
      else if (wasHidden) handleNativeResume();
      else void reconcileRef.current();
    };
    const handleFocus = () => {
      if (wasHidden) handleNativeResume();
      else void reconcileRef.current();
    };
    const handleOnline = () => {
      void reconcileRef.current();
    };
    const handleOffline = () => {
      setConnectionStatus("disconnected");
    };
    const handleNativeResume = () => {
      resumedRef.current = true;
      wasHidden = false;
      if (Date.now() - lastResumeAt < RECONCILE_MIN_INTERVAL_MS) return;
      lastResumeAt = Date.now();
      // Both transports may have missed updates, even for the same completed run.
      const sessionId = sessionIdRef.current;
      foregroundRefreshRef.current = sessionId
        ? { sessionId, runId: currentRunIdRef.current }
        : null;
      reconcileControllerRef.current?.abort();
      reconcileControllerRef.current = null;
      connectionStatusRef.current = "disconnected";
      setConnectionStatus("disconnected");
      lastReconcileAtRef.current = 0;
      void reconcileRef.current();
    };

    document.addEventListener("resume", handleNativeResume);
    document.addEventListener("pause", handlePause);
    document.addEventListener("visibilitychange", maybeReconcile);
    window.addEventListener("focus", handleFocus);
    window.addEventListener("online", handleOnline);
    window.addEventListener("pageshow", maybeReconcile);
    window.addEventListener("offline", handleOffline);
    return () => {
      reconcileControllerRef.current?.abort();
      reconcileControllerRef.current = null;
      document.removeEventListener("resume", handleNativeResume);
      document.removeEventListener("pause", handlePause);
      document.removeEventListener("visibilitychange", maybeReconcile);
      window.removeEventListener("focus", handleFocus);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("pageshow", maybeReconcile);
      window.removeEventListener("offline", handleOffline);
    };
  }, [setConnectionStatus, sessionIdRef, currentRunIdRef]);

  // 空闲的可见会话也要对账，发现定时任务或其他端新启动的 run 后接上流。
  useEffect(() => {
    const timer = setInterval(() => {
      if (
        resumedRef.current === false ||
        (document.visibilityState !== "visible" && resumedRef.current !== true)
      )
        return;
      if (!sessionIdRef.current) return;
      void reconcileRef.current();
    }, WATCHDOG_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [sessionIdRef, currentRunIdRef, streamingMessageIdRef]);

  return reconcile;
}
