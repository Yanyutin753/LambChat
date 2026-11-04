import { useTranslation } from "react-i18next";
import type { Assistant } from "../../types/assistant";
import { AgentAvatar } from "../common/AgentAvatar";
import { ChatInput, type ChatInputProps } from "../chat/ChatInput";

export function AssistantWelcome({
  assistant,
  chatInputProps,
}: {
  assistant: Assistant;
  chatInputProps: ChatInputProps;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex min-h-0 flex-1 flex-col justify-center px-3 py-8 sm:px-6">
      <div className="mx-auto mb-8 flex w-full max-w-2xl flex-col items-center gap-3 text-center">
        <AgentAvatar seed={assistant.name} size={64} />
        <h1 className="text-24 font-medium text-theme-text">
          {assistant.name}
        </h1>
        <p className="max-w-lg text-14 leading-relaxed text-theme-text-secondary">
          {t(
            assistant.kind === "chief"
              ? "assistants.chiefWelcome"
              : assistant.kind === "group"
                ? "assistants.groupWelcome"
                : "assistants.assistantWelcome",
          )}
        </p>
      </div>
      <div className="mx-auto w-full max-w-3xl">
        <ChatInput {...chatInputProps} />
      </div>
    </div>
  );
}
