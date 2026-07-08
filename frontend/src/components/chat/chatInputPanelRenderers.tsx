import { type ReactElement } from "react";
import { TeamPickerModal } from "../team/TeamPickerModal";
import type { CoreChatInputPanelContribution } from "../../extensions/coreContributions";
import type { PluginOptionsMetadata } from "../../extensions/pluginOptions";
import { pluginOptionFromValues } from "../../extensions/pluginOptions";

export interface ChatInputPanelRendererProps {
  contribution: CoreChatInputPanelContribution;
  activePanel: string | null;
  onActivePanelChange: (panel: string | null) => void;
  pluginOptionValues?: PluginOptionsMetadata;
  onPluginOptionChange?: (
    pluginId: string,
    key: string,
    value: unknown,
  ) => void;
  onNavigate: (path: string) => void;
}

function AgentTeamPickerRenderer({
  contribution,
  activePanel,
  onActivePanelChange,
  pluginOptionValues,
  onPluginOptionChange,
  onNavigate,
}: ChatInputPanelRendererProps): ReactElement | null {
  const optionPath = contribution.optionBinding;
  if (!optionPath || !onPluginOptionChange) return null;
  const pluginSelectedTeamId =
    pluginOptionFromValues(pluginOptionValues, optionPath.pluginId, optionPath.key);
  const effectiveSelectedTeamId =
    typeof pluginSelectedTeamId === "string" ? pluginSelectedTeamId : null;
  const handleSelectTeam = (teamId: string | null) => {
    onPluginOptionChange?.(optionPath.pluginId, optionPath.key, teamId);
  };
  const navigateToCreate = contribution.createPath
    ? () => onNavigate(contribution.createPath as string)
    : undefined;
  const navigateToManage = contribution.managePath
    ? () => onNavigate(contribution.managePath as string)
    : navigateToCreate;
  return (
    <TeamPickerModal
      isOpen={activePanel === contribution.id}
      selectedTeamId={effectiveSelectedTeamId ?? null}
      onSelect={handleSelectTeam}
      onClose={() => onActivePanelChange(null)}
      onCreateNew={navigateToCreate}
      onManageTeams={navigateToManage}
    />
  );
}

export const CHAT_INPUT_PANEL_RENDERERS: Record<
  string,
  (props: ChatInputPanelRendererProps) => ReactElement | null
> = {
  "agent_team.TeamPickerModal": AgentTeamPickerRenderer,
};
