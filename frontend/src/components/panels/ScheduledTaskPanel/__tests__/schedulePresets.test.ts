import { expect, test } from "vitest";
import { getSchedulePreset } from "../utils";

test.each([
  [{ hour: "9", minute: "30" }, "daily"],
  [{ hour: "9", minute: "0", second: "0", day_of_week: "mon-fri" }, "weekdays"],
  [{ hour: "9", minute: "0", day_of_week: "wed" }, "weekly"],
  [{ hour: "*/3", minute: "0" }, "cron"],
  [{ hour: "9", minute: "0", second: "15" }, "cron"],
  [{ hour: "9", minute: "0", day: "1" }, "cron"],
  [{ hour: "9", minute: "0", year: "2027" }, "cron"],
  [{ minute: "0" }, "cron"],
])(
  "recognizes only schedules safely represented by a preset: %j",
  (config, expected) => {
    expect(
      getSchedulePreset({ trigger_type: "cron", trigger_config: config }),
    ).toBe(expected);
  },
);
