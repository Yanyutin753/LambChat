/**
 * 插话取消回调注册表。
 *
 * 排队的插话气泡（queued 用户消息）渲染在消息列表深处，取消回调由
 * ChatView 注册、UserMessageBubble 直接触发，避免层层透传 props。
 */
type SteerCancelHandler = (content: string, messageId?: string) => void;

let handler: SteerCancelHandler | null = null;

export function setSteerCancelHandler(next: SteerCancelHandler | null): void {
  handler = next;
}

export function cancelSteeredMessage(
  content: string,
  messageId?: string,
): void {
  handler?.(content, messageId);
}
