import { fetchAllTeamsForExport, toTeamExportData } from "../teamExport.ts";
import type {
  Team,
  TeamListParams,
  TeamListResponse,
} from "../../../types/team";

function team(id: string): Team {
  return {
    id,
    owner_user_id: "user-1",
    name: `Team ${id}`,
    description: "",
    avatar: null,
    tags: [],
    members: [],
    default_member_id: null,
    team_instructions: "",
    run_in_sandbox: false,
    starter_prompts: [],
    visibility: "private",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  };
}

test("fetchAllTeamsForExport keeps paging until every team is loaded", async () => {
  const pages = [[team("1"), team("2")], [team("3"), team("4")], [team("5")]];
  const calls: TeamListParams[] = [];

  const teams = await fetchAllTeamsForExport(async (params) => {
    calls.push(params);
    const pageIndex = (params.skip ?? 0) / 2;
    return {
      teams: pages[pageIndex] ?? [],
      total: 5,
      skip: params.skip ?? 0,
      limit: params.limit ?? 2,
    } satisfies TeamListResponse;
  }, 2);

  expect(calls.map((call) => ({ skip: call.skip, limit: call.limit }))).toEqual(
    [
      { skip: 0, limit: 2 },
      { skip: 2, limit: 2 },
      { skip: 4, limit: 2 },
    ],
  );
  expect(teams.map((item) => item.id)).toEqual(["1", "2", "3", "4", "5"]);
});

test("toTeamExportData keeps fields needed for importing teams later", () => {
  const exportData = toTeamExportData([
    {
      ...team("1"),
      tags: ["research"],
      members: [
        {
          member_id: "m-analyst",
          persona_preset_id: "preset-1",
          model_id: "model-member",
          role_name: "Analyst",
          role_avatar: null,
          role_tags: ["research"],
          role_instructions: "",
          position: 0,
          enabled: true,
        },
      ],
      team_instructions: "Coordinate analysis.",
    },
  ]);

  expect(exportData).toEqual([
    {
      name: "Team 1",
      description: "",
      avatar: null,
      tags: ["research"],
      members: [
        {
          member_id: "m-analyst",
          persona_preset_id: "preset-1",
          model_id: "model-member",
          role_name: "Analyst",
          role_avatar: null,
          role_tags: ["research"],
          role_instructions: "",
          position: 0,
          enabled: true,
        },
      ],
      default_member_id: null,
      team_instructions: "Coordinate analysis.",
      run_in_sandbox: false,
      starter_prompts: [],
    },
  ]);
});
