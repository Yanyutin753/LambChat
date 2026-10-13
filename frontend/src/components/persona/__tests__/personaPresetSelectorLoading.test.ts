import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const currentDir = dirname(fileURLToPath(import.meta.url));
const selectorSource = readFileSync(
  resolve(currentDir, "../PersonaPresetSelector.tsx"),
  "utf8",
);
const previewSource = readFileSync(
  resolve(currentDir, "../PersonaPreviewSidebar.tsx"),
  "utf8",
);
const personaCss = readFileSync(
  resolve(currentDir, "../../../styles/persona.css"),
  "utf8",
);

test("persona preset use buttons expose per-preset loading feedback", () => {
  expect(selectorSource).toMatch(/pendingUsePresetId/);
  expect(selectorSource).toMatch(/setPendingUsePresetId\(preset\.id\)/);
  expect(selectorSource).toMatch(
    /finally\s*\{\s*setPendingUsePresetId\(null\);/,
  );
  expect(selectorSource).toMatch(/aria-busy=\{isUsingPreset\}/);
  expect(selectorSource).toMatch(
    /<LoadingSpinner color="text-current" size=\{13\}/,
  );
  expect(selectorSource).toMatch(/personaPresets\.applying/);
});

test("persona preview use button can mirror selector loading state", () => {
  expect(previewSource).toMatch(/isUsingPreset/);
  expect(previewSource).toMatch(/aria-busy=\{isUsingPreset\}/);
  expect(previewSource).toMatch(
    /<LoadingSpinner color="text-current" size=\{14\}/,
  );
  expect(previewSource).toMatch(/personaPresets\.applying/);
});

test("persona preset loading buttons keep disabled cursor distinct", () => {
  expect(personaCss).toMatch(/\.pps-card__action--loading/);
  expect(personaCss).toMatch(/cursor: wait;/);
});
