import { useCallback, useMemo, useState } from "react";
import type { RefObject } from "react";

import type { PendingSteer } from "../../components/chat/SteerQueueChips";
import { sessionApi } from "../../services/api";

import { createSteerMessage } from "./steerMessage";

interface SteerQueueOptions {
  sessionIdRef: RefObject<string | null>;
  setError: (error: string | null) => void;
}

/**
 * 运行中插话（steer）的前端排队状态：
 * - 发送：POST 后端队列 + 显示"排队 chip"（不直接插入对话流）
 * - 送达：后端注入模型调用时发 user:message 事件，事件回调移除 chip，
 *   正式气泡由标准 user:message 渲染路径上屏
 * - 取消：DELETE 后端队列中未送达的消息
 */
export function useSteerQueue({ sessionIdRef, setError }: SteerQueueOptions) {
  const [pendingSteers, setPendingSteers] = useState<PendingSteer[]>([]);

  const removePendingSteer = useCallback((steerId: string) => {
    setPendingSteers((prev) => prev.filter((item) => item.id !== steerId));
  }, []);

  const removePendingSteerByContent = useCallback((content: string) => {
    setPendingSteers((prev) => prev.filter((item) => item.content !== content));
  }, []);

  const cancelPendingSteer = useCallback((content: string) => {
    setPendingSteers((prev) => prev.filter((item) => item.content !== content));
    const currentSessionId = sessionIdRef.current;
    if (currentSessionId) {
      sessionApi.cancelSteer(currentSessionId, content).catch(() => {});
    }
  }, [sessionIdRef]);

  const clearPendingSteers = useCallback(() => setPendingSteers([]), []);

  const steerMessage = useMemo(
    () =>
      createSteerMessage({
        sessionIdRef,
        onQueued: (steer) => setPendingSteers((prev) => [...prev, steer]),
        onFailed: removePendingSteer,
        setError,
      }),
    [removePendingSteer, sessionIdRef, setError],
  );

  return {
    pendingSteers,
    steerMessage,
    cancelPendingSteer,
    removePendingSteerByContent,
    clearPendingSteers,
  };
}
