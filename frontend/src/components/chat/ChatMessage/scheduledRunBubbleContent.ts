export interface ScheduledRunBubbleContentInput {
  title: string;
  taskName: string;
  prompt?: string;
  timestamp: string;
}

export function buildScheduledRunBubbleContent({
  title,
  taskName,
  prompt,
  timestamp,
}: ScheduledRunBubbleContentInput): string {
  const header = `${title} · ${taskName}`;
  const trimmedPrompt = prompt?.trim();
  // UserMessageBubble 走 Markdown 渲染，段落间用空行分隔
  return trimmedPrompt
    ? `${header}\n\n${trimmedPrompt}\n\n${timestamp}`
    : `${header}\n\n${timestamp}`;
}
