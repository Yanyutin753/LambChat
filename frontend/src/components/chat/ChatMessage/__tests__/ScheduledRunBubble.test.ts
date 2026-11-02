import { describe, expect, test } from "vitest";
import { buildScheduledRunBubbleContent } from "../scheduledRunBubbleContent";

describe("buildScheduledRunBubbleContent", () => {
  test("shows the task prompt between the header and the timestamp", () => {
    expect(
      buildScheduledRunBubbleContent({
        title: "定时任务",
        taskName: "Numbers",
        prompt: "Check whether AO3 is back",
        timestamp: "2026/10/16 17:46",
      }),
    ).toBe(
      "定时任务 · Numbers\n\nCheck whether AO3 is back\n\n2026/10/16 17:46",
    );
  });

  test("omits the prompt section when the run carried no prompt", () => {
    expect(
      buildScheduledRunBubbleContent({
        title: "定时任务",
        taskName: "Numbers",
        prompt: undefined,
        timestamp: "2026/10/16 17:46",
      }),
    ).toBe("定时任务 · Numbers\n\n2026/10/16 17:46");
  });

  test("trims a whitespace-only prompt away", () => {
    expect(
      buildScheduledRunBubbleContent({
        title: "定时任务",
        taskName: "Numbers",
        prompt: "   ",
        timestamp: "2026/10/16 17:46",
      }),
    ).toBe("定时任务 · Numbers\n\n2026/10/16 17:46");
  });
});
