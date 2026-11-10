import { useTranslation } from "react-i18next";
import { useState } from "react";
import type { Assistant } from "../../types/assistant";
import { AgentAvatar } from "../common/AgentAvatar";
import {
  WELCOME_INPUT_CONTAINER_CLASS_NAME,
  getWelcomeSuggestionsContainerClass,
  getSelectedPersonaStarterPrompts,
} from "../chat/welcomeLayout";
import { WelcomeSuggestions } from "../chat/WelcomeSuggestions";
import { ChatInput, type ChatInputProps } from "../chat/ChatInput";

export function AssistantWelcome({
  assistant,
  chatInputProps,
}: {
  assistant: Assistant;
  chatInputProps: ChatInputProps;
}) {
  const { t, i18n } = useTranslation();
  const [pendingInput, setPendingInput] = useState<string | null>(null);
  const unavailable =
    chatInputProps.disabled ||
    chatInputProps.isLoading ||
    chatInputProps.sendBlocked ||
    chatInputProps.canSend === false;
  return (
    <div className="welcome-root relative flex h-full min-h-0 flex-1 flex-col items-center justify-start !overflow-y-auto px-4">
      <div className="my-auto w-full py-2">
        <div className="mx-auto mb-1 sm:mb-2 md:mb-2.5 xl:mb-3 2xl:mb-3 flex w-full max-w-2xl flex-col items-center gap-3 px-3 text-center sm:px-6">
          <AgentAvatar
            avatar={assistant.avatar}
            seed={assistant.name}
            size={64}
          />
          <h1 className="text-24 font-medium text-theme-text">
            {assistant.name}
          </h1>
          <p className="max-w-lg text-14 leading-relaxed text-theme-text-secondary">
            {assistant.description ||
              t(
                assistant.kind === "chief"
                  ? "assistants.chiefWelcome"
                  : assistant.kind === "group"
                    ? "assistants.groupWelcome"
                    : "assistants.assistantWelcome",
              )}
          </p>
        </div>
        <div className={WELCOME_INPUT_CONTAINER_CLASS_NAME}>
          <ChatInput
            {...chatInputProps}
            className="mx-auto w-full px-2"
            pendingInput={pendingInput ?? chatInputProps.pendingInput}
            onPendingInputConsumed={() => {
              if (pendingInput !== null) setPendingInput(null);
              else chatInputProps.onPendingInputConsumed?.();
            }}
          />
        </div>
        <div className={getWelcomeSuggestionsContainerClass("prompts")}>
          <WelcomeSuggestions
            suggestions={getSelectedPersonaStarterPrompts(
              [assistant],
              assistant.id,
              i18n.language,
              ["first", "second", "third"].map((key) => ({
                icon: null,
                text: t(`assistants.starters.${assistant.kind}.${key}`),
              })),
            )}
            disabled={unavailable}
            onSelect={setPendingInput}
          />
        </div>
      </div>
    </div>
  );
}
