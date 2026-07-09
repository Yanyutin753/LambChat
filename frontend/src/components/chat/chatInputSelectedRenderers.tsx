import { type ComponentType } from "react";
import { pluginOptionFromValues } from "../../extensions/pluginOptions";
import {
  AgentTeamSelectedChip,
  type ChatInputSelectedRendererProps,
} from "./chatInputSelectedRendererComponents";

export interface ChatInputSelectedRendererEntry {
  hasSelection: (props: ChatInputSelectedRendererProps) => boolean;
  Component: ComponentType<ChatInputSelectedRendererProps>;
}

export const CHAT_INPUT_SELECTED_RENDERERS: Record<
  string,
  ChatInputSelectedRendererEntry
> = {
  "agent_team.SelectedTeamChip": {
    hasSelection: ({ option, pluginOptionValues, onPluginOptionChange }) => {
      const optionPath = option.optionBinding;
      const pluginSelectedTeamId = optionPath
        ? pluginOptionFromValues(pluginOptionValues, optionPath.pluginId, optionPath.key)
        : null;
      return Boolean(
        onPluginOptionChange &&
          typeof pluginSelectedTeamId === "string" &&
          pluginSelectedTeamId,
      );
    },
    Component: AgentTeamSelectedChip,
  },
};

export type { ChatInputSelectedRendererProps };
