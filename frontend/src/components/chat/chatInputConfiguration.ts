import { useEffect, type Dispatch, type SetStateAction } from "react";
import type { FeaturePanel } from "../selectors/FeatureMenu";
import type { ChatInputProps } from "./chatInputTypes";

function lockChatInputConfiguration(props: ChatInputProps): ChatInputProps {
  return {
    ...props,
    onToggleAgentOption: undefined,
    onSelectAgent: undefined,
    onSelectTeam: undefined,
    onUsePersonaPreset: undefined,
    onClearPersonaPreset: undefined,
    onOpenTeamBuilder: undefined,
    selectedPersonaName: undefined,
  };
}

export function useChatInputConfiguration(
  rawProps: ChatInputProps,
  onPanelChange: Dispatch<SetStateAction<FeaturePanel>>,
): ChatInputProps {
  const props = rawProps.configurationLocked
    ? lockChatInputConfiguration(rawProps)
    : rawProps;
  const { currentAgent, onSelectTeam } = props;
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isMac =
        typeof navigator !== "undefined" &&
        navigator.platform.toUpperCase().indexOf("MAC") >= 0;
      const modifier = isMac ? e.metaKey : e.ctrlKey;
      if (modifier && e.key === "t") {
        e.preventDefault();
        if (currentAgent === "team" && onSelectTeam) {
          onPanelChange((prev) => (prev === "team" ? null : "team"));
        }
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [currentAgent, onSelectTeam, onPanelChange]);
  return props;
}
