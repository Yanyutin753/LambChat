/**
 * Streaming-target settlement helpers.
 *
 * A streaming assistant bubble can end its run without ever receiving
 * content: the client reloaded mid-run and the SSE replay never attached,
 * the run finished while disconnected, or only a recommend-questions push
 * landed on the placeholder. Such a bubble must not survive as an empty
 * orphan in the transcript — settle it, and drop it when nothing
 * renderable remains.
 */
import type { Message } from "../../types";
import { clearAllLoadingStates } from "./messageParts";

/** Whether an assistant message carries anything renderable besides
 *  recommend-questions suggestions (those render under the last message,
 *  never as a standalone turn). */
export function assistantMessageHasContent(message: Message): boolean {
  return Boolean(
    message.content?.trim() ||
      message.toolCalls?.length ||
      message.toolResults?.length ||
      message.cancelled ||
      message.parts?.some((part) => part.type !== "recommend_questions"),
  );
}

export function settleAssistantMessage(
  previous: Message[],
  messageId: string,
  options: { preserveAskHuman?: boolean } = {},
): Message[] {
  const target = previous.find((message) => message.id === messageId);
  if (!target) return previous;

  const settled: Message = {
    ...target,
    isStreaming: false,
    parts: clearAllLoadingStates(target.parts || [], {
      preserveAskHuman: options.preserveAskHuman ?? true,
    }),
  };
  if (target.role === "assistant" && !assistantMessageHasContent(settled)) {
    return previous.filter((message) => message.id !== messageId);
  }
  return previous.map((message) =>
    message.id === messageId ? settled : message,
  );
}
