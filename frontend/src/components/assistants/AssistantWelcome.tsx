import { useTranslation } from "react-i18next";
import { useState } from "react";
import type { Assistant } from "../../types/assistant";
import { AgentAvatar } from "../common/AgentAvatar";
import { WelcomeSuggestions } from "../chat/WelcomeSuggestions";
import { ChatInput, type ChatInputProps } from "../chat/ChatInput";

export function AssistantWelcome({
  assistant,
  chatInputProps,
}: {
  assistant: Assistant;
  chatInputProps: ChatInputProps;
}) {
  const { t } = useTranslation();
  const [pendingInput, setPendingInput] = useState<string | null>(null);
  const unavailable =
    chatInputProps.disabled ||
    chatInputProps.isLoading ||
    chatInputProps.sendBlocked ||
    chatInputProps.canSend === false;
  return (
    <div className="flex h-full min-h-0 flex-1 flex-col overflow-y-auto py-6">
      <div className="my-auto w-full py-2">
        <div className="mx-auto mb-8 flex w-full max-w-2xl flex-col items-center gap-3 px-3 text-center sm:px-6">
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
        <div className="w-full">
          <div className="welcome-suggestions chat-content-column mb-4">
            <WelcomeSuggestions
              suggestions={["first", "second", "third"].map((key) => ({
                text: t(`assistants.starters.${assistant.kind}.${key}`),
              }))}
              disabled={unavailable}
              onSelect={setPendingInput}
            />
          </div>
          <ChatInput
            {...chatInputProps}
            className="chat-content-column"
            pendingInput={pendingInput ?? chatInputProps.pendingInput}
            onPendingInputConsumed={() => {
              if (pendingInput !== null) setPendingInput(null);
              else chatInputProps.onPendingInputConsumed?.();
            }}
          />
        </div>
      </div>
    </div>
  );
}
