import { useEffect, useState } from "react";
import { teamApi } from "../../services/api/team";
import type { Team } from "../../types/team";
import type {
  CoreAssistantIdentityResolverContribution,
  PluginRuntimeContributionStates,
} from "../../extensions/coreContributions";
import { buildAssistantIdentityResolverContributions } from "../../extensions/coreContributions";
import { pluginOptionFromValues, type PluginOptionsMetadata } from "../../extensions/pluginOptions";
import { getTeamFallbackAvatar } from "../team/teamAvatarUtils";

export interface ChatAssistantIdentity {
  avatar: string | null;
  name: string | null;
}

export interface ChatAssistantIdentityResolverContext {
  currentAgent: string;
  pluginOptionValues?: PluginOptionsMetadata;
  runtimePlugins?: PluginRuntimeContributionStates;
}

export interface ChatAssistantIdentitySnapshotContext {
  currentAgent?: string | null;
  runtimePlugins?: PluginRuntimeContributionStates;
  teamName?: string | null;
  teamAvatar?: string | null;
}

interface ChatAssistantIdentityResolverEntry {
  resolver: string;
  canResolve: (context: ChatAssistantIdentityResolverContext) => boolean;
  useIdentity: (context: ChatAssistantIdentityResolverContext) => ChatAssistantIdentity | null;
}

function useAgentTeamIdentity({
  currentAgent,
  pluginOptionValues,
  runtimePlugins,
}: ChatAssistantIdentityResolverContext): ChatAssistantIdentity | null {
  const [currentTeam, setCurrentTeam] = useState<Team | null>(null);
  const contribution = findRuntimeAssistantIdentityResolver(
    { currentAgent, runtimePlugins },
    "agent_team.TeamAssistantIdentity",
  );
  const contributionId = contribution?.id ?? null;
  const contributionAgentId = contribution?.agentId ?? null;
  const optionBinding = contribution?.optionBinding;
  const selectedTeamValue = optionBinding
    ? pluginOptionFromValues(
        pluginOptionValues,
        optionBinding.pluginId,
        optionBinding.key,
      )
    : null;
  const selectedTeamId =
    typeof selectedTeamValue === "string" && selectedTeamValue.trim()
      ? selectedTeamValue
      : null;

  useEffect(() => {
    if (
      !contributionAgentId ||
      currentAgent !== contributionAgentId ||
      !selectedTeamId ||
      !contributionId
    ) {
      setCurrentTeam(null);
      return;
    }

    let cancelled = false;
    teamApi
      .get(selectedTeamId)
      .then((team) => {
        if (!cancelled) setCurrentTeam(team);
      })
      .catch(() => {
        if (!cancelled) setCurrentTeam(null);
      });

    return () => {
      cancelled = true;
    };
  }, [contributionAgentId, contributionId, currentAgent, selectedTeamId]);

  if (!contributionAgentId || currentAgent !== contributionAgentId || !currentTeam) return null;
  const fallbackAvatar = getTeamFallbackAvatar(currentTeam);
  return {
    avatar: currentTeam.avatar ?? fallbackAvatar,
    name: currentTeam.name ?? null,
  };
}

export const CHAT_ASSISTANT_IDENTITY_RESOLVERS: readonly ChatAssistantIdentityResolverEntry[] = [
  {
    resolver: "agent_team.TeamAssistantIdentity",
    canResolve: ({ currentAgent, pluginOptionValues, runtimePlugins }) => {
      const contribution = findRuntimeAssistantIdentityResolver(
        { currentAgent, runtimePlugins },
        "agent_team.TeamAssistantIdentity",
      );
      if (!contribution || contribution.agentId !== currentAgent) return false;
      const optionBinding = contribution?.optionBinding;
      if (!optionBinding) return false;
      return Boolean(
        pluginOptionFromValues(
          pluginOptionValues,
          optionBinding.pluginId,
          optionBinding.key,
        ),
      );
    },
    useIdentity: useAgentTeamIdentity,
  },
];

export function usePluginChatAssistantIdentity(
  context: ChatAssistantIdentityResolverContext,
): ChatAssistantIdentity | null {
  const runtimeResolvers = buildAssistantIdentityResolverContributions(
    context.runtimePlugins,
    { agentId: context.currentAgent },
  );
  const allowedResolvers = new Set(runtimeResolvers.map((item) => item.resolver));
  const resolver = CHAT_ASSISTANT_IDENTITY_RESOLVERS.find(
    (entry) => allowedResolvers.has(entry.resolver) && entry.canResolve(context),
  );
  return resolver?.useIdentity(context) ?? null;
}

export function resolvePluginAssistantIdentitySnapshot({
  currentAgent,
  runtimePlugins,
  teamName,
  teamAvatar,
}: ChatAssistantIdentitySnapshotContext): ChatAssistantIdentity | null {
  if (!currentAgent) return null;
  const runtimeResolvers = buildAssistantIdentityResolverContributions(
    runtimePlugins,
    { agentId: currentAgent },
  );
  const hasAgentTeamResolver = runtimeResolvers.some(
    (entry) => entry.resolver === "agent_team.TeamAssistantIdentity",
  );
  if (!hasAgentTeamResolver || (!teamName && !teamAvatar)) return null;
  return {
    name: teamName ?? null,
    avatar: teamAvatar ?? null,
  };
}

function findRuntimeAssistantIdentityResolver(
  context: ChatAssistantIdentityResolverContext,
  resolver: string,
): CoreAssistantIdentityResolverContribution | undefined {
  return buildAssistantIdentityResolverContributions(context.runtimePlugins, {
    agentId: context.currentAgent,
  }).find((entry) => entry.resolver === resolver);
}
