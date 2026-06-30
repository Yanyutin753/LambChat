import { useMemo, useEffect, useState } from "react";
import { teamApi } from "../services/api/team";
import { subscribeTeamsChanged } from "./teamEvents";
import type { Team } from "../types/team";

export function useTeamMentionSearch(query: string, isActive: boolean) {
  const [teams, setTeams] = useState<Team[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (!isActive) {
      setTeams([]);
      setIsLoading(false);
      return;
    }

    let cancelled = false;
    setIsLoading(true);
    const loadTeams = () => {
      teamApi
        .list(0, 50)
        .then((response) => {
          if (!cancelled) setTeams(response.teams);
        })
        .catch(() => {
          if (!cancelled) setTeams([]);
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false);
        });
    };
    loadTeams();
    const unsubscribe = subscribeTeamsChanged(() => {
      loadTeams();
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, [isActive]);

  const filteredTeams = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return teams;
    return teams.filter(
      (team) =>
        team.name.toLowerCase().includes(q) ||
        team.description?.toLowerCase().includes(q) ||
        team.members.some(
          (member) =>
            member.role_name.toLowerCase().includes(q) ||
            member.role_tags.some((tag) => tag.toLowerCase().includes(q)),
        ),
    );
  }, [query, teams]);

  return {
    teams: filteredTeams,
    total: filteredTeams.length,
    isLoading,
    isLoadingMore: false,
    hasMore: false,
  };
}
