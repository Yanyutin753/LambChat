import test from "node:test";
import assert from "node:assert/strict";
import {
  buildProjectPluginOptionUrl,
  buildProjectPluginOptionsUrl,
} from "../project.ts";

test("builds project plugin options urls", () => {
  assert.equal(
    buildProjectPluginOptionsUrl("project 1"),
    "/api/projects/project%201/plugin-options",
  );
  assert.equal(
    buildProjectPluginOptionUrl("project 1", "agent_team", "DEFAULT_TEAM_ID"),
    "/api/projects/project%201/plugin-options/agent_team/DEFAULT_TEAM_ID",
  );
});
