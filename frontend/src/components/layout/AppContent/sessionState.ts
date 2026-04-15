import type { Message } from "../../../types";
import type { SessionConfig } from "../../../hooks/useAgent/types";

export function isSessionRunning(
  messages: Pick<Message, "isStreaming">[],
  isLoading: boolean,
): boolean {
  return isLoading || messages.some((message) => message.isStreaming);
}

export function getRestoredModelSelection(
  config: Pick<SessionConfig, "agent_options">,
): {
  modelId: string;
  modelValue: string;
} {
  const modelId =
    typeof config.agent_options?.model_id === "string"
      ? config.agent_options.model_id
      : "";
  const modelValue =
    typeof config.agent_options?.model === "string"
      ? config.agent_options.model
      : "";

  return {
    modelId,
    modelValue,
  };
}
