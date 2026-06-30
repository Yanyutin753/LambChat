import { existsSync, readFileSync } from "node:fs";
const teamAvatarUrl = new URL("../TeamAvatar.tsx", import.meta.url);
const teamAvatarSource = existsSync(teamAvatarUrl)
  ? readFileSync(teamAvatarUrl, "utf8")
  : "";
const teamAvatarUtilsUrl = new URL("../teamAvatarUtils.ts", import.meta.url);
const teamAvatarUtilsSource = existsSync(teamAvatarUtilsUrl)
  ? readFileSync(teamAvatarUtilsUrl, "utf8")
  : "";
const wrapperSource = readFileSync(
  new URL("../TeamBuilderWrapper.tsx", import.meta.url),
  "utf8",
);
const pickerSource = readFileSync(
  new URL("../TeamPickerModal.tsx", import.meta.url),
  "utf8",
);
const welcomePageSource = readFileSync(
  new URL("../../chat/WelcomePage.tsx", import.meta.url),
  "utf8",
);
const welcomeSurfaceRendererSource = readFileSync(
  new URL("../../chat/welcomeSurfaceRenderers.tsx", import.meta.url),
  "utf8",
);
const toolbarSource = readFileSync(
  new URL("../../chat/ChatInputToolbar.tsx", import.meta.url),
  "utf8",
);
const selectedRendererSource = readFileSync(
  new URL("../../chat/chatInputSelectedRenderers.tsx", import.meta.url),
  "utf8",
);

test("team avatar component supports team, default-role, and generic fallback icons", () => {
  expect(existsSync(teamAvatarUrl)).toBe(true);
  expect(teamAvatarSource).toMatch(/export function TeamAvatar/);
  expect(teamAvatarSource).toMatch(/team-avatar/);
  expect(teamAvatarUtilsSource).toMatch(/getTeamFallbackAvatar/);
  expect(teamAvatarSource).toMatch(/avatar \?\? fallbackAvatar/);
  expect(teamAvatarSource).toMatch(/PersonaAvatarImage/);
  expect(teamAvatarSource).toMatch(/PersonaAvatarIcon/);
  expect(teamAvatarSource).toMatch(/<Users/);
});

test("all team selection surfaces render team avatars consistently", () => {
  assert.match(wrapperSource, /<TeamAvatar[\s\S]*avatar=\{team\.avatar\}/);
  assert.match(pickerSource, /<TeamAvatar[\s\S]*avatar=\{team\.avatar\}/);
  assert.doesNotMatch(welcomePageSource, /<TeamAvatar/);
  assert.match(welcomeSurfaceRendererSource, /<TeamAvatar[\s\S]*avatar=\{team\.avatar\}/);
  assert.doesNotMatch(toolbarSource, /<TeamAvatar/);
  assert.match(
    selectedRendererSource,
    /<TeamAvatar[\s\S]*avatar=\{selectedTeam\?\.avatar\}/,
  );
});
