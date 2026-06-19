import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

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
  assert.equal(existsSync(teamAvatarUrl), true);
  assert.match(teamAvatarSource, /export function TeamAvatar/);
  assert.match(teamAvatarSource, /team-avatar/);
  assert.match(teamAvatarUtilsSource, /getTeamFallbackAvatar/);
  assert.match(teamAvatarSource, /avatar \?\? fallbackAvatar/);
  assert.match(teamAvatarSource, /PersonaAvatarImage/);
  assert.match(teamAvatarSource, /PersonaAvatarIcon/);
  assert.match(teamAvatarSource, /<Users/);
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
