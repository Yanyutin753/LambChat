import type { Message } from "../types/message";
import { uuid } from "./uuid";

interface BuildSteerUserMessageOptions {
  previousCount: number;
  content: string;
  now?: Date;
  createId?: () => string;
}

/**
 * 构造运行中插话（steer）的乐观用户消息。
 *
 * 消息先本地展示（steered 标记），由后端 SteerMiddleware 在下一次
 * 模型调用注入并持久化到图状态；运行结束后历史刷新会以持久化
 * 版本为准。
 */
export function buildSteerUserMessage({
  content,
  now = new Date(),
  createId = () => uuid(),
}: BuildSteerUserMessageOptions): Message {
  return {
    id: createId(),
    role: "user",
    content: content.trim(),
    timestamp: now,
    metadata: { steered: true },
  };
}
