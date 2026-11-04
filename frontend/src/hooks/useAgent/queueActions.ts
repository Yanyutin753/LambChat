import {
  useCallback,
  type Dispatch,
  type RefObject,
  type SetStateAction,
} from "react";
import i18n from "../../i18n";
import { sessionApi } from "../../services/api";
import type { Message, MessageAttachment } from "../../types";
import type { UseAgentOptions, UseAgentReturn } from "./types";
import type { useQueuePause } from "./queuePause";
import type { SteerFollowUpPromotionOptions } from "./steerQueue";
import { settleRunMessages } from "./settleStream";

interface QueueActionsOptions {
  sessionIdRef: RefObject<string | null>;
  currentRunIdRef: RefObject<string | null>;
  submitInFlightRef: RefObject<boolean>;
  isSendingRef: RefObject<boolean>;
  sendSeqRef: RefObject<number>;
  stoppedSubmitSeqRef: RefObject<number | null>;
  streamVersionRef: RefObject<number>;
  sendMessageRef: SteerFollowUpPromotionOptions["sendMessageRef"];
  setQueuePaused: ReturnType<typeof useQueuePause>["setQueuePaused"];
  queuePaused: boolean;
  queueFollowUp: UseAgentReturn["queueFollowUp"];
  steerMessage: (
    content: string,
    attachments?: MessageAttachment[],
    queuedMessageId?: string,
  ) => Promise<void>;
  clearSteer: (content: string, messageId?: string, sessionId?: string) => void;
  setIsLoading: (loading: boolean) => void;
  setIsInitializingSandbox: (loading: boolean) => void;
  setSandboxError: (error: string | null) => void;
  setError: (error: string | null) => void;
  setMessages: Dispatch<SetStateAction<Message[]>>;
  persistentGoalStatus?: string;
  onClearApprovals?: UseAgentOptions["onClearApprovals"];
}

export function useQueueActions({
  sessionIdRef,
  currentRunIdRef,
  submitInFlightRef,
  isSendingRef,
  sendSeqRef,
  stoppedSubmitSeqRef,
  streamVersionRef,
  sendMessageRef,
  setQueuePaused,
  queuePaused,
  queueFollowUp,
  steerMessage,
  clearSteer,
  setIsLoading,
  setIsInitializingSandbox,
  setSandboxError,
  setError,
  setMessages,
  persistentGoalStatus,
  onClearApprovals,
}: QueueActionsOptions) {
  const stopGeneration = useCallback(
    async (requireCancellation = false) => {
      const stoppedRunId = currentRunIdRef.current;
      setQueuePaused(sessionIdRef.current, true, stoppedRunId ?? undefined);
      if (submitInFlightRef.current)
        stoppedSubmitSeqRef.current = sendSeqRef.current;
      // 用户停止即夺取发送所有权：在途 sendMessage 的 finally 不得再重置
      // 共享标志（否则会把停止后新发送刚置好的状态抹掉）
      sendSeqRef.current += 1;
      submitInFlightRef.current = false;
      isSendingRef.current = false;
      setIsLoading(false);
      setIsInitializingSandbox(false);
      setSandboxError(null);

      // Clear approvals immediately (don't wait for SSE cancel event which may never arrive)
      onClearApprovals?.(sessionIdRef.current ?? undefined);

      setMessages((previous) =>
        settleRunMessages(previous, currentRunIdRef.current),
      );

      const currentSessionId = sessionIdRef.current;
      if (currentSessionId) {
        try {
          await sessionApi.cancel(currentSessionId, stoppedRunId ?? undefined);
        } catch (error) {
          console.error(
            "[stopGeneration] Failed to call backend cancel API:",
            error,
          );
          if (sessionIdRef.current === currentSessionId)
            setError(i18n.t("chat.requestFailed"));
          if (requireCancellation) throw error;
        }
      }
    },
    [
      onClearApprovals,
      setIsInitializingSandbox,
      setIsLoading,
      setSandboxError,
      setQueuePaused,
      sessionIdRef,
      currentRunIdRef,
      submitInFlightRef,
      isSendingRef,
      sendSeqRef,
      stoppedSubmitSeqRef,
      setMessages,
      setError,
    ],
  );

  // 补充当前问题：打断进行中的 run，把补充内容并入这轮思考重新生成
  // （原问题与已生成部分保留在历史，新一轮自动携带完整上下文）
  const supplementFollowUp = useCallback(
    async (
      content: string,
      attachments?: MessageAttachment[],
      queuedMessageId?: string,
    ) => {
      const text = content.trim();
      if (!text && !attachments?.length) return;
      if (queuedMessageId) {
        if (queuePaused) {
          const targetSession = sessionIdRef.current;
          await sendMessageRef.current?.(text, attachments, {
            onAccepted: () =>
              clearSteer(text, queuedMessageId, targetSession ?? undefined),
          });
          return;
        }
        if (!submitInFlightRef.current)
          await steerMessage(text, attachments, queuedMessageId);
        return;
      }
      // isSendingRef 在整个流式期间恒为 true，不能用它在途判定；只有
      // POST 尚未被服务端受理时打断才会造成同会话双提交——仅该窗口转排队
      if (submitInFlightRef.current) {
        queueFollowUp(text, attachments);
        return;
      }
      if (persistentGoalStatus === "active") {
        await steerMessage(text, attachments);
        return;
      }
      const targetSession = sessionIdRef.current;
      const targetVersion = streamVersionRef.current;
      const stopSequence = sendSeqRef.current + 1;
      const isCurrentSupplement = () =>
        sessionIdRef.current === targetSession &&
        streamVersionRef.current === targetVersion &&
        sendSeqRef.current === stopSequence;
      try {
        await stopGeneration(true);
      } catch {
        if (isCurrentSupplement()) queueFollowUp(text, attachments);
        return;
      }
      if (!isCurrentSupplement()) return;
      await sendMessageRef.current?.(text, attachments);
    },
    [
      queueFollowUp,
      stopGeneration,
      persistentGoalStatus,
      steerMessage,
      queuePaused,
      clearSteer,
      sessionIdRef,
      submitInFlightRef,
      sendMessageRef,
      streamVersionRef,
      sendSeqRef,
    ],
  );

  return { stopGeneration, supplementFollowUp };
}
