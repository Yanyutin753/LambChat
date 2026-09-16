import { useCallback, useEffect, useRef } from "react";
import type { RefObject } from "react";

import { sessionApi } from "../../services/api";
import type { SteerItem } from "../../utils/mergeSteers";
import { uuid } from "../../utils/uuid";
import type { MessageAttachment } from "../../types";
import { useQueuedFollowUpState } from "./queuedFollowUpState";

interface SteerQueueOptions {
  sessionIdRef: RefObject<string | null>;
  deferSteer: (
    content: string,
    messageId: string,
    attachments?: MessageAttachment[],
  ) => void;
  removeDeferredSteer?: (content: string, messageId?: string) => void;
}

/**
 * 「追加提问」的本地排队项：不进后端插话队列（不会在 run 中途被注入
 * 打断当前任务），只作为排队气泡展示；run 结束后由
 * useSteerFollowUpPromotion 与未送达插话一起补发为普通消息。
 */
export function toFollowUpQueueItem(
  content: string,
  attachments: MessageAttachment[] = [],
): SteerItem | null {
  const text = content.trim();
  if (!text && attachments.length === 0) return null;
  return {
    id: uuid(),
    content: text,
    attachments,
    queued: true,
    status: "deferred",
    deferred: true,
    timestamp: new Date(),
  };
}

export function removeSteerItem(
  items: SteerItem[],
  content: string,
  messageId?: string,
): { remaining: SteerItem[]; removed?: SteerItem } {
  const index = messageId
    ? items.findIndex((item) => item.id === messageId)
    : items.findIndex((item) => item.content === content);
  if (index < 0) return { remaining: items };
  return {
    removed: items[index],
    remaining: [...items.slice(0, index), ...items.slice(index + 1)],
  };
}

/** Accepted-but-undelivered items become ordinary follow-up turns at run end. */
export function selectSteersForFollowUp(items: SteerItem[]): SteerItem[] {
  return items.filter((item) => item.queued && item.status !== "failed");
}

/**
 * effect cleanup 回滚：仍在队列（未被送达/清除）的排队项解除占用标记，
 * 让下一次 effect 重新接管——否则 cleanup 杀掉重试后这些项会永久滞留。
 */
export function releaseUnfinishedFollowUps(
  followUps: SteerItem[],
  isStillQueued: (id: string) => boolean,
  marked: Set<string>,
): void {
  for (const item of followUps) {
    if (isStillQueued(item.id)) marked.delete(item.id);
  }
}

export interface PromoteSteerFollowUpsDeps {
  sessionId: string | null;
  cancelSteer: (
    sessionId: string,
    content: string,
    messageId: string,
  ) => Promise<unknown>;
  sendMessage: (
    content: string,
    attachments?: MessageAttachment[],
  ) => Promise<unknown>;
  isCancelled?: (messageId: string) => boolean;
  clearSteer?: (content: string, messageId: string) => void;
  /** 会话仍有运行中的 run 时返回 true：插话留在队列等注入，不补发 */
  isSessionActive?: () => Promise<boolean>;
  /** 本地 sendMessage 在途时返回 true：补发会被在途守卫静默丢弃，须保留排队项稍后重试 */
  isSending?: () => boolean;
}

export interface PromoteSteerFollowUpsResult {
  promoted: number;
  /** 因会话仍在运行而暂缓补发的条数（调用方稍后重试） */
  skippedActive: number;
}

/**
 * 把未送达插话补发为普通消息。
 *
 * 必须先清本地状态、再取消后端队列中的同一条，最后作为普通消息发送：
 * 后端队列按会话共享，若只补发不取消，新 run 的首次模型调用会把同
 * 一条插话再次注入（同内容投递两次）。取消失败不阻塞补发——后端在
 * 新 run 提交时也会兜底清空残留队列。
 *
 * 补发前先探测会话是否仍在运行（重进/断连恢复场景）：运行中的 run
 * 仍可能在下一次模型调用注入这条插话，此时补发会造出同会话并发 run
 * （两路事件按时间交错落库，历史不可读）。探测失败按运行中处理——
 * 宁可让补发稍后再试，也不冒双发并发 run 的险。
 */
export async function promoteSteerFollowUps(
  items: SteerItem[],
  deps: PromoteSteerFollowUpsDeps,
): Promise<PromoteSteerFollowUpsResult> {
  const { sessionId } = deps;
  if (!sessionId) return { promoted: 0, skippedActive: 0 };
  if (deps.isSessionActive) {
    let active = true;
    try {
      active = await deps.isSessionActive();
    } catch {
      active = true;
    }
    if (active) {
      const skippedActive = items.filter(
        (item) => !deps.isCancelled?.(item.id),
      ).length;
      return { promoted: 0, skippedActive };
    }
  }
  let promoted = 0;
  let deferredBySending = 0;
  for (const item of items) {
    if (deps.isCancelled?.(item.id)) continue;
    // 本地提交在途（用户恰好在 run 结束瞬间手动发送）：sendMessage 的
    // 在途守卫会静默丢弃补发调用，若先清本地项这条排队消息就丢了。
    // 原样留在队列，靠 skippedActive 的重试稍后再发。
    if (deps.isSending?.()) {
      deferredBySending += 1;
      continue;
    }
    deps.clearSteer?.(item.content, item.id);
    try {
      await deps.cancelSteer(sessionId, item.content, item.id);
    } catch {
      // 取消失败继续补发；新 run 提交时的后端兜底清理会移除残留项
    }
    await deps.sendMessage(item.content, item.attachments);
    promoted += 1;
  }
  return { promoted, skippedActive: deferredBySending };
}

/** 补发插话前视为「会话仍在运行」的任务状态（终态之外的都算） */
const ACTIVE_RUN_STATUSES = new Set([
  "pending",
  "queued",
  "starting",
  "running",
  "cancelling",
  "waiting_human",
  "recovering",
]);

const PROMOTE_RETRY_INTERVAL_MS = 5000;

export interface SteerFollowUpPromotionOptions {
  isLoading: boolean;
  isSendingRef: RefObject<boolean>;
  steerMessages: SteerItem[];
  clearSteer: (content: string, messageId?: string) => void;
  cancelledSteerIdsRef: RefObject<Set<string>>;
  followUpSteerIdsRef: RefObject<Set<string>>;
  sessionIdRef: RefObject<string | null>;
  sendMessageRef: RefObject<
    | ((content: string, attachments?: MessageAttachment[]) => Promise<void>)
    | null
  >;
}

/**
 * 未送达插话的自动补发（run 结束后转为普通消息）。
 *
 * 触发条件只看本地发送态——重进/断连恢复时它恒为 false，因此补发前
 * 必须探测会话实际状态：运行中则插话留在原 run 队列等注入，稍后重试
 * （避免补发造出同会话并发 run、两路事件按时间交错落库）。
 */
export function useSteerFollowUpPromotion(
  options: SteerFollowUpPromotionOptions,
): void {
  const {
    isLoading,
    isSendingRef,
    steerMessages,
    clearSteer,
    cancelledSteerIdsRef,
    followUpSteerIdsRef,
    sessionIdRef,
    sendMessageRef,
  } = options;
  // 重试时校验插话是否仍在队列（已被注入/送达的不重发，防同内容双投）
  const steerMessagesRef = useRef(steerMessages);
  useEffect(() => {
    steerMessagesRef.current = steerMessages;
  }, [steerMessages]);

  useEffect(() => {
    if (isLoading || isSendingRef.current) return;
    const followUps = selectSteersForFollowUp(steerMessages).filter(
      (item) => !followUpSteerIdsRef.current.has(item.id),
    );
    if (followUps.length === 0) return;
    for (const item of followUps) {
      followUpSteerIdsRef.current.add(item.id);
    }
    let cancelled = false;
    let retryTimer: number | undefined;
    // cleanup 读 ref.current 会触发 exhaustive-deps 且有滞后风险：进入时
    // 拷贝（Set 本身从不被整体重赋值，语义等价）
    const markedFollowUpIds = followUpSteerIdsRef.current;
    const queuedSnapshot = steerMessagesRef;
    const promote = async () => {
      // 先取消后端队列中的残留项再补发，否则新 run 的首次模型调用会把
      // 同一条插话再次注入（同内容投递两次）。FIFO 逐条等待补发，避免
      // 单 run 守卫丢弃后续条目。
      const result = await promoteSteerFollowUps(followUps, {
        sessionId: sessionIdRef.current,
        cancelSteer: (sessionId, content, messageId) =>
          sessionApi.cancelSteer(sessionId, content, messageId),
        sendMessage: async (content, attachments) => {
          await sendMessageRef.current?.(content, attachments);
        },
        // cancelled：effect 卸载或用户撤销；不在队列：已被注入/送达
        isCancelled: (id) =>
          cancelled ||
          cancelledSteerIdsRef.current.has(id) ||
          !steerMessagesRef.current.some((item) => item.id === id),
        clearSteer,
        isSessionActive: async () => {
          const sessionId = sessionIdRef.current;
          if (!sessionId) return false;
          const { status } = await sessionApi.getStatus(sessionId);
          return ACTIVE_RUN_STATUSES.has(status);
        },
        isSending: () => isSendingRef.current,
      });
      // 会话仍在运行：插话留在原 run 队列等注入，稍后再探测
      if (result.skippedActive > 0 && !cancelled) {
        retryTimer = window.setTimeout(() => {
          void promote();
        }, PROMOTE_RETRY_INTERVAL_MS);
      }
    };
    const timer = window.setTimeout(() => {
      void promote();
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      if (retryTimer !== undefined) window.clearTimeout(retryTimer);
      // cleanup 会杀掉在途补发/5s 重试：未完成的排队项回滚占用标记，
      // 交给下一次 effect 接管，避免「追问排队后永远没发出去」
      releaseUnfinishedFollowUps(
        followUps,
        (id) => queuedSnapshot.current.some((item) => item.id === id),
        markedFollowUpIds,
      );
    };
  }, [
    clearSteer,
    isLoading,
    isSendingRef,
    steerMessages,
    cancelledSteerIdsRef,
    followUpSteerIdsRef,
    sessionIdRef,
    sendMessageRef,
  ]);
}

export interface PendingSteerSnapshot {
  message_id: string;
  content: string;
  created_at: string;
  attachments?: Array<
    Omit<MessageAttachment, "mimeType"> & {
      mimeType?: string;
      mime_type?: string;
    }
  >;
}

/**
 * 运行中插话（steer）的独立前端状态——与用户消息管线完全解耦：
 * - 发送：POST 后端队列 + 本地插话项（排队态），不触碰 messages
 * - 送达：后端注入模型调用时发 steer:message 事件 → 轮次分割 +
 *   本地 optimistic 项移除，正式消息由事件处理器写入 messages
 * - 取消：删除本地项 + DELETE 后端队列中未送达的消息
 */
export function useSteerQueue({
  sessionIdRef,
  deferSteer,
  removeDeferredSteer,
}: SteerQueueOptions) {
  const {
    steerMessages,
    setSteerMessages,
    clearSteerMessages,
    restoreSteerMessages,
    bindSteerSession,
  } = useQueuedFollowUpState(sessionIdRef.current);

  // 引用必须稳定：作为 props 传给 memo(ChatInput)，流式期间父级高频
  // 重渲染时不能破坏记忆化（否则编辑器每个 token 重渲染一次）
  const steerMessage = useCallback(
    async (content: string, attachments: MessageAttachment[] = []) => {
      const text = content.trim();
      const currentSessionId = sessionIdRef.current;
      if (!text || !currentSessionId) return;

      const item: SteerItem = {
        id: uuid(),
        content: text,
        attachments,
        queued: true,
        status: "pending",
        timestamp: new Date(),
      };
      setSteerMessages((prev) => [...prev, item]);
      try {
        await sessionApi.steer(currentSessionId, text, item.id, attachments);
      } catch (error) {
        console.error("[steerMessage] Failed to steer session:", error);
        const status =
          typeof error === "object" && error !== null && "status" in error
            ? (error as { status?: number }).status
            : undefined;
        // A 409 means the run ended between the status check and enqueue. It
        // is safe to preserve the user's intent as a normal next turn;
        // transport/auth/server failures must remain retryable instead.
        if (status === 409) {
          setSteerMessages((prev) =>
            prev.map((s) =>
              s.id === item.id
                ? { ...s, queued: false, status: "deferred", deferred: true }
                : s,
            ),
          );
          deferSteer(text, item.id, attachments);
          return;
        }
        setSteerMessages((prev) =>
          prev.map((s) =>
            s.id === item.id ? { ...s, queued: false, status: "failed" } : s,
          ),
        );
      }
    },
    [sessionIdRef, deferSteer, setSteerMessages],
  );

  // 追加提问：只入本地排队（不 POST /steer），run 结束后自动转普通消息
  const queueFollowUp = useCallback(
    (content: string, attachments: MessageAttachment[] = []) => {
      const item = toFollowUpQueueItem(content, attachments);
      if (!item) return;
      const currentSessionId = sessionIdRef.current;
      if (!currentSessionId) {
        // 首条消息 POST 在途（会话尚未建立）：挂到 deferred 队列，由该次
        // 发送的 finally 在 run 结束后补发——静默丢弃会弄丢用户输入
        deferSteer(item.content, item.id, attachments);
      }
      setSteerMessages((prev) => [...prev, item]);
    },
    [sessionIdRef, deferSteer, setSteerMessages],
  );

  const cancelSteer = useCallback(
    (content: string, messageId?: string) => {
      let removed: SteerItem | undefined;
      setSteerMessages((prev) => {
        const result = removeSteerItem(prev, content, messageId);
        removed = result.removed;
        return result.remaining;
      });
      removeDeferredSteer?.(content, messageId ?? removed?.id);
      const currentSessionId = sessionIdRef.current;
      if (currentSessionId) {
        sessionApi
          .cancelSteer(currentSessionId, content, messageId)
          .catch(() => {});
      }
    },
    [removeDeferredSteer, sessionIdRef, setSteerMessages],
  );

  const markSteerDelivered = useCallback(
    (content: string, messageId?: string) => {
      setSteerMessages((prev) => {
        const indexById = messageId
          ? prev.findIndex((s) => s.id === messageId)
          : -1;
        const index =
          indexById >= 0
            ? indexById
            : prev.findIndex((s) => s.content === content && s.queued);
        if (index === -1) return prev;
        return [...prev.slice(0, index), ...prev.slice(index + 1)];
      });
    },
    [setSteerMessages],
  );

  const hydrateSteers = useCallback(
    (items: PendingSteerSnapshot[]) => {
      setSteerMessages((prev) => {
        const existing = new Map(prev.map((item) => [item.id, item]));
        for (const item of items) {
          if (!existing.has(item.message_id)) {
            existing.set(item.message_id, {
              id: item.message_id,
              content: item.content,
              attachments: item.attachments?.map((attachment) => ({
                ...attachment,
                mimeType: attachment.mimeType ?? attachment.mime_type ?? "",
              })),
              queued: true,
              status: "pending",
              timestamp: new Date(item.created_at),
            });
          }
        }
        return [...existing.values()].sort(
          (a, b) => a.timestamp.getTime() - b.timestamp.getTime(),
        );
      });
    },
    [setSteerMessages],
  );
  const clearSteer = useCallback(
    (content: string, messageId?: string) =>
      setSteerMessages((prev) =>
        prev.filter((item) =>
          messageId ? item.id !== messageId : item.content !== content,
        ),
      ),
    [setSteerMessages],
  );

  return {
    steerMessages,
    steerMessage,
    queueFollowUp,
    cancelSteer,
    markSteerDelivered,
    clearSteerMessages,
    clearSteer,
    hydrateSteers,
    restoreSteerMessages,
    bindSteerSession,
  };
}
