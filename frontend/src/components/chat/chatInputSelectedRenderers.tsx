import { useEffect, useState, type ReactElement } from "react";
import type { CoreChatInputOptionContribution } from "../../extensions/coreContributions";
import type { PluginOptionsMetadata } from "../../extensions/pluginOptions";
import { pluginOptionFromValues } from "../../extensions/pluginOptions";
import { teamApi } from "../../services/api/team";
import type { Team } from "../../types/team";
import { TeamAvatar } from "../team/TeamAvatar";
import {
  getTeamFallbackAvatar,
  getTeamFallbackTag,
} from "../team/teamAvatarUtils";
import { ToolbarChip } from "./ToolbarChip";

export interface ChatInputSelectedRendererProps {
  option: CoreChatInputOptionContribution;
  activePanel: string | null;
  onActivePanelChange: (panel: string | null) => void;
  pluginOptionValues?: PluginOptionsMetadata;
  onPluginOptionChange?: (
    pluginId: string,
    key: string,
    value: unknown,
  ) => void;
  fallbackLabel: string;
}

export interface ChatInputSelectedRendererEntry {
  hasSelection: (props: ChatInputSelectedRendererProps) => boolean;
  render: (props: ChatInputSelectedRendererProps) => ReactElement | null;
}

function AgentTeamSelectedChip({
  option,
  onActivePanelChange,
  pluginOptionValues,
  onPluginOptionChange,
  fallbackLabel,
}: ChatInputSelectedRendererProps): ReactElement | null {
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null);
  const optionPath = option.optionBinding;
  const pluginSelectedTeamId =
    optionPath
      ? pluginOptionFromValues(pluginOptionValues, optionPath.pluginId, optionPath.key)
      : null;
  const effectiveSelectedTeamId =
    typeof pluginSelectedTeamId === "string" && pluginSelectedTeamId
      ? pluginSelectedTeamId
      : null;
  const clearSelection = () => {
    if (!optionPath) return;
    onPluginOptionChange?.(optionPath.pluginId, optionPath.key, null);
  };

  useEffect(() => {
    if (!effectiveSelectedTeamId) {
      setSelectedTeam(null);
      return;
    }
    let cancelled = false;
    teamApi
      .get(effectiveSelectedTeamId)
      .then((team) => {
        if (!cancelled) setSelectedTeam(team);
      })
      .catch(() => {
        if (!cancelled) setSelectedTeam(null);
      });
    return () => {
      cancelled = true;
    };
  }, [effectiveSelectedTeamId]);

  if (!optionPath || !effectiveSelectedTeamId || !onPluginOptionChange) return null;
  const label = selectedTeam?.name ?? fallbackLabel;
  return (
    <ToolbarChip
      icon={
        <TeamAvatar
          avatar={selectedTeam?.avatar}
          fallbackAvatar={selectedTeam ? getTeamFallbackAvatar(selectedTeam) : null}
          fallbackTag={selectedTeam ? getTeamFallbackTag(selectedTeam) : ""}
          label={label}
          className="team-toolbar-avatar transition-opacity group-hover:opacity-0"
          iconSize={18}
        />
      }
      label={label}
      onClick={() => option.panel && onActivePanelChange(option.panel)}
      onClear={clearSelection}
    />
  );
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
    render: AgentTeamSelectedChip,
  },
};
