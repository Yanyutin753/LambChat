import type { Message } from "../types/message";

/** 实时插话项：独立于 messages 的渲染数据源 */
export interface SteerItem {
  id: string;
  content: string;
  /** true = 已入队未送达（置灰 + 时钟角标） */
  queued: boolean;
  timestamp: Date;
}

/**
 * 把实时插话项按时间戳合并进消息流用于渲染。
 *
 * 插话是独立状态（不在 messages 数组里），渲染时与消息按时间顺序
 * 归并：排队中的插话落在当前流式回复之后，送达后（轮次分割产生的
 * 新助手轮次时间戳晚于插话）自然排在其之前。
 */
export function mergeMessagesWithSteers(
  messages: Message[],
  steers: SteerItem[],
): Message[] {
  if (steers.length === 0) return messages;

  const steerMessages: Message[] = steers.map((steer) => ({
    id: steer.id,
    role: "user",
    content: steer.content,
    timestamp: steer.timestamp,
    metadata: { steer: true, queued: steer.queued },
  }));

  return [...messages, ...steerMessages].sort(
    (a, b) => a.timestamp.getTime() - b.timestamp.getTime(),
  );
}
