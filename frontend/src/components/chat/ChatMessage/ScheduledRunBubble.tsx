import { useTranslation } from "react-i18next";
import { useScheduledTaskPrompt } from "../../../stores/scheduledTaskPromptStore";
import { buildScheduledRunBubbleContent } from "./scheduledRunBubbleContent";
import { UserMessageBubble } from "./UserMessageBubble";

/**
 * 定时 run 在目标对话里的合成用户气泡：本次 run 的提问是任务提示词，
 * 旧载荷缺 prompt 时按 taskId 从任务设置懒加载兜底。
 */
export function ScheduledRunBubble({
  taskId,
  taskName,
  prompt,
  timestamp,
}: {
  taskId?: string;
  taskName: string;
  prompt?: string;
  timestamp: string;
}) {
  const { t } = useTranslation();
  const fallbackPrompt = useScheduledTaskPrompt(prompt ? undefined : taskId);
  return (
    <UserMessageBubble
      content={buildScheduledRunBubbleContent({
        title: t("scheduledTask.title"),
        taskName,
        prompt: prompt || fallbackPrompt,
        timestamp,
      })}
    />
  );
}
