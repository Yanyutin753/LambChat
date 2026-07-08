import type { Team, TeamListParams, TeamListResponse } from "../../types/team";

export const TEAM_EXPORT_PAGE_SIZE = 200;

type TeamListFetcher = (
  params: Pick<TeamListParams, "skip" | "limit">,
) => Promise<TeamListResponse>;

export async function fetchAllTeamsForExport(
  listTeams: TeamListFetcher,
  pageSize = TEAM_EXPORT_PAGE_SIZE,
): Promise<Team[]> {
  const allTeams: Team[] = [];
  let skip = 0;

  while (true) {
    const res = await listTeams({
      skip,
      limit: pageSize,
    });

    allTeams.push(...res.teams);
    skip += res.teams.length;

    if (skip >= res.total || res.teams.length < pageSize) break;
  }

  return allTeams;
}

export function toTeamExportData(teams: Team[]) {
  return teams.map((team) => ({
    name: team.name,
    description: team.description,
    avatar: team.avatar ?? null,
    tags: team.tags ?? [],
    members: team.members,
    default_member_id: team.default_member_id ?? null,
    team_instructions: team.team_instructions,
    run_in_sandbox: Boolean(team.run_in_sandbox),
    starter_prompts: team.starter_prompts ?? [],
  }));
}
