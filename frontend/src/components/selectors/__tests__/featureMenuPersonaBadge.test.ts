import { readFileSync } from "node:fs";
const featureMenuSource = readFileSync(
  new URL("../FeatureMenu.tsx", import.meta.url),
  "utf8",
);

const toolbarSource = readFileSync(
  new URL("../../chat/ChatInputToolbar.tsx", import.meta.url),
  "utf8",
);

const chatInputSource = readFileSync(
  new URL("../../chat/ChatInput.tsx", import.meta.url),
  "utf8",
);

test("feature menu persona item shows count fallback and prefers persona name", () => {
  expect(featureMenuSource).toMatch(/totalPersonaCount\?: number/);
  expect(featureMenuSource).toMatch(/badge=\{personaName \|\|/);
  expect(featureMenuSource).toMatch(
    /totalPersonaCount > 0 \? `\$\{totalPersonaCount\}` : undefined/,
  );
});

test("chat input toolbar forwards totalPersonaCount to feature menu", () => {
  expect(toolbarSource).toMatch(/totalPersonaCount\?: number/);
  expect(toolbarSource).toMatch(/totalPersonaCount=\{totalPersonaCount\}/);
});

test("chat input wires personaPresetsTotal into toolbar persona count", () => {
  expect(chatInputSource).toMatch(/totalPersonaCount=\{personaPresetsTotal\}/);
});
