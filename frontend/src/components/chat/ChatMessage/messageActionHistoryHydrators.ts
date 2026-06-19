import { feedbackApi } from "../../../plugins/feedback/api";
import type { Message } from "../../../types";
import type { CoreMessageActionContribution } from "../../../extensions/coreContributions";

export interface MessageActionHistoryHydratorContext {
  sessionId: string;
  messages: Message[];
}

type MessageActionHistoryHydrator = (
  context: MessageActionHistoryHydratorContext,
) => Promise<Message[]>;

const MESSAGE_ACTION_HISTORY_HYDRATORS: Record<string, MessageActionHistoryHydrator> = {
  "feedback.FeedbackButtons": hydrateFeedbackHistory,
};

async function hydrateFeedbackHistory({
  sessionId,
  messages,
}: MessageActionHistoryHydratorContext): Promise<Message[]> {
  const feedbackList = await feedbackApi.list(0, 100, undefined, undefined, sessionId);
  if (!feedbackList.items.length) return messages;

  const feedbackMap = new Map(
    feedbackList.items.map((feedback) => [
      feedback.run_id,
      { feedback: feedback.rating, feedbackId: feedback.id },
    ]),
  );

  return messages.map((message) => {
    if (!message.runId) return message;
    const feedbackInfo = feedbackMap.get(message.runId);
    return feedbackInfo
      ? {
          ...message,
          feedback: feedbackInfo.feedback,
          feedbackId: feedbackInfo.feedbackId,
        }
      : message;
  });
}

export async function hydrateMessageActionHistory(
  contributions: readonly CoreMessageActionContribution[],
  context: MessageActionHistoryHydratorContext,
): Promise<Message[]> {
  let nextMessages = context.messages;
  for (const contribution of contributions) {
    const hydrator = MESSAGE_ACTION_HISTORY_HYDRATORS[contribution.renderer];
    if (!hydrator) continue;
    nextMessages = await hydrator({ ...context, messages: nextMessages });
  }
  return nextMessages;
}
