import test from "node:test";
import assert from "node:assert/strict";
import { parseBooleanSettingValue } from "../../utils/booleanSettings.ts";

test("parses boolean settings from API values without treating non-empty false strings as enabled", () => {
  for (const value of [true, "true", "TRUE", "1", 1, "yes", "on", "enabled"]) {
    assert.equal(parseBooleanSettingValue(value), true);
  }

  for (const value of [false, "false", "False", "0", 0, "", "off", null, undefined]) {
    assert.equal(parseBooleanSettingValue(value), false);
  }
});
