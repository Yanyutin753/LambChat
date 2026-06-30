import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../ChannelPluginOptions.tsx", import.meta.url),
  "utf8",
);

test("channel plugin options render Agent Team through plugin-owned option declaration", () => {
  assert.match(source, /ChannelTeamSelect/);
  assert.match(source, /CHANNEL_OPTION_RENDERERS/);
  assert.match(source, /"agent_team\.TeamSelectOption"/);
  assert.match(source, /option\.renderer/);
  assert.doesNotMatch(source, /option\.plugin_id === AGENT_TEAM_PLUGIN_ID/);
  assert.doesNotMatch(source, /option\.key === AGENT_TEAM_SELECTED_TEAM_OPTION/);
});

test("channel plugin options keep a generic renderer for future plugin fields", () => {
  assert.match(source, /option\.type === "boolean"/);
  assert.match(source, /option\.type === "select"/);
  assert.match(source, /option\.type === "json"/);
  assert.match(source, /optionInputType/);
  assert.match(source, /onChange\(option\.plugin_id, option\.key/);
});

test("channel plugin options keep saved inactive values visible but read-only", () => {
  assert.match(source, /option\.effective !== false/);
  assert.match(source, /hasValue\(valueFor\(values, option\.plugin_id, option\.key\)\)/);
  assert.match(source, /Plugin disabled; saved value is retained but will not apply\./);
  assert.match(source, /const fieldDisabled = disabled \|\| inactive/);
  assert.match(source, /loadTeams=\{!inactive\}/);
});
