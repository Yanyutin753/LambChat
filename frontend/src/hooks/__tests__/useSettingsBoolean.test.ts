import { parseBooleanSettingValue } from "../../utils/booleanSettings.ts";

test("parses boolean settings from API values without treating non-empty false strings as enabled", () => {
  for (const value of [true, "true", "TRUE", "1", 1, "yes", "on", "enabled"]) {
    expect(parseBooleanSettingValue(value)).toBe(true);
  }

  for (const value of [false, "false", "False", "0", 0, "", "off", null, undefined]) {
    expect(parseBooleanSettingValue(value)).toBe(false);
  }
});
