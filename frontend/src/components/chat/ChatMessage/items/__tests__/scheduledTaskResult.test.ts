import { expect, test } from "vitest";
import { parseResult } from "../scheduledTaskResult";

test("recognizes array task lists including the empty list", () => {
  expect(parseResult('[{"name":"Weekly review"}]')).toMatchObject({
    isList: true,
    tasks: [{ name: "Weekly review" }],
  });
  expect(parseResult("[]")).toMatchObject({ isList: true, tasks: [] });
});

test.each(["deleted", "paused", "resumed", "triggered"])(
  "recognizes a %s confirmation without a task object",
  (action) => {
    expect(
      parseResult(
        JSON.stringify({
          success: true,
          action,
          task_id: "task-1",
          message: "Operation complete.",
        }),
      ),
    ).toMatchObject({
      message: "Operation complete.",
      task: null,
      isList: false,
    });
  },
);
