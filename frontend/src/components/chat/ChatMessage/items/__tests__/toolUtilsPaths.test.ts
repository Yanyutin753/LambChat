import { expect, test } from "vitest";
import { extractPaths } from "../toolUtils";

test("empty glob responses are not counted as file paths", () => {
  expect(extractPaths("No files found")).toEqual([]);
  expect(
    extractPaths({ content: [{ type: "text", text: "No files found" }] }),
  ).toEqual([]);
  expect(extractPaths('["/workspace/No files found.txt"]')).toEqual([
    "/workspace/No files found.txt",
  ]);
});
