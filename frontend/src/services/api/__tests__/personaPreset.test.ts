import test from "node:test";
import assert from "node:assert/strict";

import { buildPersonaPresetListUrl } from "../personaPreset.ts";

test("builds the default persona preset list url", () => {
  assert.equal(buildPersonaPresetListUrl(), "/api/persona-presets/");
});

test("builds persona preset list url with filters", () => {
  assert.equal(
    buildPersonaPresetListUrl({
      scope: "global",
      q: "coder",
      tag: "coding",
      skip: 20,
      limit: 10,
    }),
    "/api/persona-presets/?scope=global&q=coder&tag=coding&skip=20&limit=10",
  );
});
