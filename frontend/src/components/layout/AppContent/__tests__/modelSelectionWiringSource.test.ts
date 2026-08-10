import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

const settingsSource = readFileSync(
  resolve(__dirname, "../../../../contexts/SettingsContext.tsx"),
  "utf8",
);

test("settings context exposes the configured system default model ID", () => {
  expect(settingsSource).toMatch(/systemDefaultModelId:\s*string/);
  expect(settingsSource).toMatch(/systemDefaultModelId:\s*adminDefaultModelId/);
});

test("a successful empty model response remains distinct from unresolved loading", () => {
  expect(settingsSource).toMatch(/else\s*\{\s*setDbModels\(\[\]\)/);
});
