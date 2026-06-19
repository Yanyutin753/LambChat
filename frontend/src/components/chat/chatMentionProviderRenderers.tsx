import { type ReactElement } from "react";
import { useTeamMentionSearch } from "../../hooks/useTeamMentionSearch";
import type { CoreMentionProviderContribution } from "../../extensions/coreContributions";
import type { Team } from "../../types/team";
import { TeamMentionPopup } from "./TeamMentionPopup";

export interface PluginMentionProviderSupportContext {
  onPluginOptionChange?: (pluginId: string, key: string, value: unknown) => void;
}

interface MentionPopupPlacement {
  left: number;
  width: number;
  bottom: number;
  maxHeight: number;
}

export interface PluginMentionProviderRuntimeOptions
  extends PluginMentionProviderSupportContext {
  provider: CoreMentionProviderContribution | null;
  query: string;
  isActive: boolean;
  highlightedIndex: number;
  selectedTeamId?: string | null;
  onBeforeSelect: () => void;
  onHover: (index: number) => void;
  onClose: () => void;
  placement?: MentionPopupPlacement | null;
}

export interface PluginMentionProviderRuntime {
  mode: string;
  resultCount: number;
  placeholderKey?: string;
  selectHighlighted: () => void;
  popup: ReactElement | null;
}

function isAgentTeamMentionProvider(
  provider: CoreMentionProviderContribution | null | undefined,
): boolean {
  return Boolean(
    provider &&
      provider.mode === "team" &&
      provider.provider === "agent_team.searchTeams",
  );
}

export function isPluginMentionProviderSupported(
  provider: CoreMentionProviderContribution | null | undefined,
  context: PluginMentionProviderSupportContext,
): boolean {
  if (isAgentTeamMentionProvider(provider)) {
    return Boolean(context.onPluginOptionChange && provider?.optionBinding);
  }
  return false;
}

export function usePluginMentionProviderRuntime({
  provider,
  query,
  isActive,
  highlightedIndex,
  selectedTeamId,
  onPluginOptionChange,
  onBeforeSelect,
  onHover,
  onClose,
  placement,
}: PluginMentionProviderRuntimeOptions): PluginMentionProviderRuntime | null {
  const isTeamProvider = isAgentTeamMentionProvider(provider);
  const teamMentionSearch = useTeamMentionSearch(query, isActive && isTeamProvider);

  if (!provider || !isTeamProvider || !onPluginOptionChange || !provider.optionBinding) {
    return null;
  }
  const optionBinding = provider.optionBinding;

  const selectTeam = (team: Team) => {
    onBeforeSelect();
    onPluginOptionChange(optionBinding.pluginId, optionBinding.key, team.id);
  };

  return {
    mode: provider.mode,
    resultCount: teamMentionSearch.teams.length,
    placeholderKey: "chat.teamPlaceholder",
    selectHighlighted: () => {
      const highlighted = teamMentionSearch.teams[highlightedIndex];
      if (highlighted) selectTeam(highlighted);
    },
    popup:
      isActive && provider.mode === "team" ? (
        <TeamMentionPopup
          teams={teamMentionSearch.teams}
          highlightedIndex={highlightedIndex}
          selectedTeamId={selectedTeamId}
          isLoading={teamMentionSearch.isLoading}
          onSelect={selectTeam}
          onHover={onHover}
          onClose={onClose}
          placement={placement}
        />
      ) : null,
  };
}
