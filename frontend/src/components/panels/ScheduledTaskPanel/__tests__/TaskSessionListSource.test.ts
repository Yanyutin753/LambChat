import { readFileSync } from "node:fs";
import { join } from "node:path";

const source = readFileSync(join(__dirname, "../TaskSessionList.tsx"), "utf-8");

test("session card indicator renders the agent's real icon via AgentIcon", () => {
  expect(source).toContain("import { AgentIcon }");
  expect(source).toMatch(/<AgentIcon\s+icon=\{agent\?\.icon\}/);
});

test("session card meta no longer uses the generic Bot placeholder icon", () => {
  expect(source).not.toMatch(/\bBot\b/);
});
