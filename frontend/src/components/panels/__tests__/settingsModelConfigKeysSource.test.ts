import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const constantsSource = readFileSync(
  join(import.meta.dirname, "../SettingsPanel.constants.ts"),
  "utf8",
);

test("image analysis model setting uses the model config selector", () => {
  assert.match(
    constantsSource,
    /MODEL_CONFIG_SETTING_KEYS[\s\S]*"IMAGE_ANALYSIS_MODEL_ID"/,
  );
});
