import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../AgentIcon.tsx", import.meta.url),
  "utf8",
);

test("renders the default bot icon as the fluent 3d robot image", () => {
  expect(source).toMatch(/const DEFAULT_AGENT_ICON_EMOJI = "🤖"/);
  expect(source).toMatch(
    /name=\{isDefaultBotIcon\(icon\) \? DEFAULT_AGENT_ICON_EMOJI : icon\}/,
  );
});
