/**
 * Queue position polling — keeps the "排队中 (第 N 位)" toast in sync with the
 * live queue position instead of freezing it at submission time.
 */

import i18n from "../../i18n";
import { sessionApi } from "../../services/api/session";

export interface QueuePositionSnapshot {
  run_id: string | null;
  task_status: string;
  position: number;
}

/**
 * Decide whether polling should continue after one snapshot.
 * Returns the position to display, or null when polling should stop
 * (run changed, task left the queue, or processing already started).
 */
export function resolveQueuePollAction(
  snapshot: QueuePositionSnapshot,
  expectedRunId: string,
): number | null {
  if (snapshot.run_id !== expectedRunId) return null;
  // 仍在排队侧状态：刷新位置（position 可能为 0，表示即将出队，继续轮询确认）
  if (snapshot.task_status === "queued" || snapshot.task_status === "pending") {
    return snapshot.position;
  }
  // 已开始处理 / 终态：queue_update 事件会接管 toast，停止轮询
  return null;
}

const QUEUE_POLL_INTERVAL_MS = 5000;
const QUEUE_POLL_MAX_TICKS = 360; // 最多轮询 30 分钟，超时自然停止

/**
 * Poll the queue position endpoint and update the chat-queue toast in place.
 * Self-terminating: stops when the run leaves the queue, the run id changes,
 * a request fails, or the max duration elapses. Fire-and-forget.
 */
export function startQueuePositionPolling(
  sessionId: string,
  runId: string,
  fetchSnapshot: (sessionId: string) => Promise<QueuePositionSnapshot> = (id) =>
    sessionApi.getQueuePosition(id),
  onUpdate: (position: number) => void = (position) => {
    import("react-hot-toast").then(({ default: toast }) => {
      toast.loading(i18n.t("chat.queued", { position }), {
        id: "chat-queue",
        duration: Infinity,
      });
    });
  },
  intervalMs: number = QUEUE_POLL_INTERVAL_MS,
): void {
  const poll = async () => {
    for (let tick = 0; tick < QUEUE_POLL_MAX_TICKS; tick += 1) {
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
      let snapshot: QueuePositionSnapshot;
      try {
        snapshot = await fetchSnapshot(sessionId);
      } catch {
        return; // 网络错误/会话删除等：直接停，避免死循环报错
      }
      const position = resolveQueuePollAction(snapshot, runId);
      if (position === null) return;
      onUpdate(position);
    }
  };
  void poll();
}
