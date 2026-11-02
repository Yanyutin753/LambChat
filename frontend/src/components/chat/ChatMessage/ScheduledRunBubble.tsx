import { useTranslation } from "react-i18next";
import { buildScheduledRunBubbleContent } from "./scheduledRunBubbleContent";
import { UserMessageBubble } from "./UserMessageBubble";

/**
 * 定时 run 在目标对话里的合成用户气泡：本次 run 的提问是任务提示词，
 * 旧载荷缺少提示词时保持未知，不能用修改后的任务配置冒充历史。
 */
export function ScheduledRunBubble({
  taskName,
  prompt,
  timestamp,
}: {
  taskName: string;
  prompt?: string;
  timestamp: string;
}) {
  const { t } = useTranslation();
  return (
    <UserMessageBubble
      content={buildScheduledRunBubbleContent({
        title: t("scheduledTask.title"),
        taskName,
        prompt,
        timestamp,
      })}
    />
  );
}
