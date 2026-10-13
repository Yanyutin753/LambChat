import { expect, test } from "vitest";
import { parseResult } from "../scheduledTaskResult";

test("recognizes array task lists including the empty list", () => {
  expect(parseResult('[{"name":"Weekly review"}]')).toMatchObject({
    isList: true, tasks: [{ name: "Weekly review" }],
  });
  expect(parseResult('[]')).toMatchObject({ isList: true, tasks: [] });
});
