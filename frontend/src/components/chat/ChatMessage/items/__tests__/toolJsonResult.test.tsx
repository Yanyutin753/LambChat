// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { ToolResultContent } from "../McpBlockPreview";

afterEach(cleanup);

test.each([
  { success: false, error: "web_search_no_provider_configured" },
  JSON.stringify({ success: false, error: "web_fetch_ssrf_blocked" }),
])("raw JSON tool output has a labeled result frame: %j", (result) => {
  const view = render(<ToolResultContent result={result} hideCopyButton />);
  const frame = view.getByRole("region");
  expect(frame.getAttribute("aria-label")).toBeTruthy();
  expect(frame.className).toContain("border-theme-border");
  expect(frame.querySelector("pre")?.textContent).toContain('"success": false');
  expect(frame.querySelector("pre")?.textContent).toContain("error");
});

test("JSON output places one copy action in its header", () => {
  const view = render(
    <ToolResultContent result={{ success: false, error: "unavailable" }} />,
  );
  const frame = view.getByRole("region");
  const buttons = frame.querySelectorAll("button");
  expect(buttons).toHaveLength(1);
  expect(buttons[0].parentElement).toBe(frame.firstElementChild);
  expect(buttons[0].className).toContain("tool-result-copy");
  expect(buttons[0].getAttribute("aria-label")).toBeTruthy();
});
