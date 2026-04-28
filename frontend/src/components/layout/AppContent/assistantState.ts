import {
  EMPTY_ASSISTANT_SELECTION,
  type AssistantSelection,
} from "../../../types";
import type { SessionConfig } from "../../../hooks/useAgent/types";

export function getRestoredAssistantSelection(
  config: Pick<
    SessionConfig,
    "assistant_id" | "assistant_name" | "assistant_prompt_snapshot"
  >,
): AssistantSelection {
  return {
    assistantId:
      typeof config.assistant_id === "string" ? config.assistant_id : "",
    assistantName:
      typeof config.assistant_name === "string" ? config.assistant_name : "",
    assistantPromptSnapshot:
      typeof config.assistant_prompt_snapshot === "string"
        ? config.assistant_prompt_snapshot
        : "",
  };
}

export function hasActiveAssistantSelection(
  selection: Pick<
    AssistantSelection,
    "assistantId" | "assistantPromptSnapshot"
  >,
): boolean {
  return Boolean(selection.assistantId || selection.assistantPromptSnapshot);
}

export function getAssistantIndicatorName(
  selection: Pick<AssistantSelection, "assistantId" | "assistantName">,
): string {
  return selection.assistantName || selection.assistantId || "Assistant";
}

export { EMPTY_ASSISTANT_SELECTION };
