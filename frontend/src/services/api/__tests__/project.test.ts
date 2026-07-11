import {
  buildProjectPluginOptionUrl,
  buildProjectPluginOptionsUrl,
} from "../project.ts";

test("builds project plugin options urls", () => {
  expect(buildProjectPluginOptionsUrl("project 1")).toBe("/api/projects/project%201/plugin-options");
  expect(buildProjectPluginOptionUrl("project 1", "agent_team", "DEFAULT_TEAM_ID")).toBe("/api/projects/project%201/plugin-options/agent_team/DEFAULT_TEAM_ID");
});
