import { type ReactElement } from "react";
import {
  AgentTeamPickerRenderer,
  type ChatInputPanelRendererProps,
} from "./chatInputPanelRendererComponents";

export const CHAT_INPUT_PANEL_RENDERERS: Record<
  string,
  (props: ChatInputPanelRendererProps) => ReactElement | null
> = {
  "agent_team.TeamPickerModal": AgentTeamPickerRenderer,
};

export type { ChatInputPanelRendererProps };
