import type { HistoryEvent, HistoryEventData } from "./types";

const STEER_REPLY_TEXT_EVENTS = new Set(["thinking", "message:chunk"]);

/**
 * 旧版后端把 steer:message 事件写在模型调用成功之后，事件落在 run 尾部
 * 且不带 created_at，直接按序重建会把插话渲染在它自己的回答之后。
 * 重建前把这类事件（组）移回其回答文本轮次之前：向前跳过同 run 的连续
 * 文本事件（thinking / message:chunk），插到该文本块开始处。带
 * created_at 的新版事件按注入时刻写入，位置天然正确，直接跳过。
 */
export function anchorLegacySteerMessageEvents(
  events: HistoryEvent[],
): HistoryEvent[] {
  const anchored: HistoryEvent[] = [];
  let replyText: HistoryEvent[] = [];
  const flushReplyText = () => {
    for (const event of replyText) anchored.push(event);
    replyText = [];
  };
  for (let index = 0; index < events.length; index++) {
    const event = events[index];
    if (STEER_REPLY_TEXT_EVENTS.has(event.event_type)) {
      if (event.event_type === "thinking" || replyText[0]?.run_id !== event.run_id) {
        flushReplyText();
      }
      replyText.push(event);
      continue;
    }
    const data = event.data as HistoryEventData | null | undefined;
    if (
      event.event_type === "steer:message" &&
      typeof data?.created_at !== "string" &&
      replyText.length > 0 &&
      replyText[0].run_id === event.run_id
    ) {
      // Keep the answer buffered while adjacent legacy steer events move before it.
      anchored.push(event);
      while (
        index + 1 < events.length &&
        events[index + 1].event_type === "steer:message" &&
        events[index + 1].run_id === event.run_id
      ) {
        anchored.push(events[++index]);
      }
      continue;
    }
    flushReplyText();
    anchored.push(event);
  }
  flushReplyText();
  return anchored;
}

/**
 * 为缺失 run_id 的历史事件回填就近 run_id。
 * 旧记录（如推荐问题）可能缺少 run_id 信封；按时间序取前向最近的
 * run_id，无前向时回退到后向第一个 run_id，保持与逐事件反向查找一致的语义。
 */
export function normalizeEventRunIds(events: HistoryEvent[]): HistoryEvent[] {
  const prevRunIdByIndex: Array<string | undefined> = new Array(events.length);
  let lastSeenRunId: string | undefined;
  for (let index = 0; index < events.length; index++) {
    prevRunIdByIndex[index] = lastSeenRunId;
    const runId = events[index].run_id;
    if (runId) lastSeenRunId = runId;
  }

  const nextRunIdByIndex: Array<string | undefined> = new Array(events.length);
  let nextSeenRunId: string | undefined;
  for (let index = events.length - 1; index >= 0; index--) {
    nextRunIdByIndex[index] = nextSeenRunId;
    const runId = events[index].run_id;
    if (runId) nextSeenRunId = runId;
  }

  return events.map((event, index) => {
    if (event.run_id) return event;
    const runId = prevRunIdByIndex[index] || nextRunIdByIndex[index];
    return runId ? { ...event, run_id: runId } : event;
  });
}
