import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const settingsSource = readFileSync(
  resolve(__dirname, "../../../../contexts/SettingsContext.tsx"),
  "utf8",
);
const chatSource = readFileSync(
  resolve(__dirname, "../ChatAppContent.tsx"),
  "utf8",
);

test("settings context exposes the configured system default model ID", () => {
  expect(settingsSource).toMatch(/systemDefaultModelId:\s*string/);
  expect(settingsSource).toMatch(/systemDefaultModelId:\s*adminDefaultModelId/);
});

test("a successful empty model response remains distinct from unresolved loading", () => {
  expect(settingsSource).toMatch(/else\s*\{\s*setDbModels\(\[\]\)/);
});

test("an empty access-filtered model list does not clear persisted pins", () => {
  expect(settingsSource).toMatch(
    /if\s*\(\s*!dbModels\s*\|\|\s*dbModels\.length\s*===\s*0[\s\S]*return pinnedModelIds/,
  );
});

test("chat resolves explicit session, user, and system model sources", () => {
  expect(chatSource).toMatch(/systemDefaultModelId/);
  expect(chatSource).toMatch(
    /sessionModelSelection[\s\S]*setSessionModelSelection/,
  );
  expect(chatSource).toMatch(/resolveModelSelection\(\{/);
  expect(chatSource).toMatch(/availableModels:\s*filteredModels/);
  expect(chatSource).toMatch(
    /sessionModelId:\s*sessionModelSelection\?\.modelId/,
  );
  expect(chatSource).toMatch(
    /userDefaultId:\s*localStorage\.getItem\("defaultModelId"\)/,
  );
  expect(chatSource).toMatch(/systemDefaultId:\s*systemDefaultModelId/);
  expect(chatSource).not.toMatch(/reconcileCurrentModelSelection/);
  expect(chatSource).not.toMatch(/resolveDefaultModelSelection/);
  expect(chatSource).not.toMatch(/isSessionRestoredRef/);
});

test("chat rejects stale restores and protects model choices made during loading", () => {
  expect(chatSource).toMatch(/onSessionLoadStart:\s*handleSessionLoadStart/);
  expect(chatSource).toMatch(/isLatestSessionLoad\(\{/);
  expect(chatSource).toMatch(/shouldApplyRestoredModelSelection\(\{/);
  expect(chatSource).toMatch(/modelSelectionRevisionRef\.current\s*\+=\s*1/);
});

test("canonical model state is the only source of submitted agent model fields", () => {
  expect(chatSource).toMatch(/withoutModelSelection\(agentOptionValues\)/);
  expect(chatSource).toMatch(/restoreAgentOptions\(restoredAgentOptions\)/);
});

test("nested async session restoration rechecks the active load", () => {
  expect(chatSource).toMatch(/applyLatestSessionLoadResult\(\{/);
  expect(chatSource).toMatch(
    /getActiveLoadId:\s*\(\)\s*=>\s*activeSessionLoadRef\.current\?\.loadId/,
  );
});
