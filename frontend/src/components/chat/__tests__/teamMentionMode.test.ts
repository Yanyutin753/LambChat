import { readFileSync } from "node:fs";
const chatInputSource = readFileSync(
  new URL("../ChatInput.tsx", import.meta.url),
  "utf8",
);

test("team agent mention switches teams instead of persona presets", () => {
  expect(chatInputSource).toMatch(/useTeamMentionSearch/);
  expect(chatInputSource).toMatch(
    /const mentionMode =[\s\S]*currentAgent === "team"[\s\S]*\? "team"[\s\S]*: "persona"/,
  );
  expect(chatInputSource).toMatch(
    /function applyTeamMentionSelection|const applyTeamMentionSelection/,
  );
  expect(chatInputSource).toMatch(/onSelectTeam\?\.\(team\.id\)/);
  expect(chatInputSource).toMatch(/<TeamMentionPopup/);
  expect(chatInputSource).toMatch(/mentionMode === "team"/);
  expect(chatInputSource).toMatch(/mentionMode === "persona"/);
});

test("team agent can submit without selecting an existing team", () => {
  expect(chatInputSource).not.toMatch(/requiresTeamSelection/);
  expect(chatInputSource).not.toMatch(/!\s*requiresTeamSelection/);
});
