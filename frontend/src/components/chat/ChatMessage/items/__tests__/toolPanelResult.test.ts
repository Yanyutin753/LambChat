import { expect, test } from "vitest";
import { parseToolPanelResult } from "../toolUtils";

test("unwraps serialized MCP content for readable sidebar rendering", () => {
  const result = { content: [{ type: "text", text: "## Report\n\nCompleted." }] };
  expect(parseToolPanelResult(JSON.stringify(result))).toBe("## Report\n\nCompleted.");
  expect(parseToolPanelResult(result)).toBe("## Report\n\nCompleted.");
  const mixed = { content: [{ type: "image", url: "image.png" }] };
  expect(parseToolPanelResult(mixed)).toEqual(mixed);
  expect(parseToolPanelResult("raw output")).toBe("raw output");
  expect(parseToolPanelResult('{"count":2}')).toBe('{"count":2}');
  expect(parseToolPanelResult(undefined)).toBeUndefined();
});
