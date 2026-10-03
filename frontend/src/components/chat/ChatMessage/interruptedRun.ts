import type { Message } from "../../../types";
import { hasPendingAskHuman } from "../../../hooks/useAgent/messageParts";

/**
 * 判断一条已落定的助手消息是否属于「远端中断且零产出」的 run：
 * 断联窗口内 run 已在服务端终结（completed/error），但正文从未送达
 * 本地——只留下过程 part（子代理/工具/思考等）。这种轮次不能在 UI
 * 上伪装成正常完成，需要渲染「回答已中断」状态与重试入口。
 *
 * 渲染时推导而非落库：历史重载带回服务端真相（有正文或错误文案）
 * 后判定自然消失，无需与重载结果做合并。
 */
export function isInterruptedRunMessage(
  message: Pick<Message, "isStreaming" | "cancelled" | "content" | "parts">,
): boolean {
  if (message.isStreaming) return false;
  if (message.cancelled) return false;
  const parts = message.parts ?? [];
  // 等待人工输入的 HITL 轮次不是中断
  if (hasPendingAskHuman(parts)) return false;
  // 用户主动停止走既有的 cancelled part UI
  if (parts.some((part) => part.type === "cancelled")) return false;
  // 没有任何过程痕迹（纯推荐问题轮/空壳）不显示横幅
  const hasTrace = parts.some((part) => part.type !== "recommend_questions");
  if (!hasTrace) return false;
  const hasOutput =
    Boolean(message.content?.trim()) ||
    parts.some((part) => part.type === "text" && part.content.trim());
  return !hasOutput;
}
