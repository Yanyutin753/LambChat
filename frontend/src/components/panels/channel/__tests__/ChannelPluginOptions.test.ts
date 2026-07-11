import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../ChannelPluginOptions.tsx", import.meta.url),
  "utf8",
);

test("channel plugin options render Agent Team through plugin-owned option declaration", () => {
  expect(source).toMatch(/ChannelTeamSelect/);
  expect(source).toMatch(/CHANNEL_OPTION_RENDERERS/);
  expect(source).toMatch(/"agent_team\.TeamSelectOption"/);
  expect(source).toMatch(/option\.renderer/);
  expect(source).not.toMatch(/option\.plugin_id === AGENT_TEAM_PLUGIN_ID/);
  expect(source).not.toMatch(/option\.key === AGENT_TEAM_SELECTED_TEAM_OPTION/);
});

test("channel plugin options keep a generic renderer for future plugin fields", () => {
  expect(source).toMatch(/option\.type === "boolean"/);
  expect(source).toMatch(/option\.type === "select"/);
  expect(source).toMatch(/option\.type === "json"/);
  expect(source).toMatch(/optionInputType/);
  expect(source).toMatch(/onChange\(option\.plugin_id, option\.key/);
});

test("channel plugin options keep saved inactive values visible but read-only", () => {
  expect(source).toMatch(/option\.effective !== false/);
  expect(source).toMatch(/hasValue\(valueFor\(values, option\.plugin_id, option\.key\)\)/);
  expect(source).toMatch(/Plugin disabled; saved value is retained but will not apply\./);
  expect(source).toMatch(/const fieldDisabled = disabled \|\| inactive/);
  expect(source).toMatch(/loadTeams=\{!inactive\}/);
});
