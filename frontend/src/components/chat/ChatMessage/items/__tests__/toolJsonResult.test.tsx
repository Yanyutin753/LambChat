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

test("assistant results show named cards with metadata and raw data collapsed", () => {
  const view = render(
    <ToolResultContent
      result={{
        assistants: [
          {
            name: "Delivery team",
            kind: "group",
            instructions: "Review the schedule",
            id: "long-id",
            member_ids: ["member-1"],
          },
          { name: "Reviewer", kind: "assistant", status: "active" },
        ],
      }}
    />,
  );
  expect(view.getByRole("heading", { name: "Delivery team" })).toBeTruthy();
  expect(view.getByRole("heading", { name: "Reviewer" })).toBeTruthy();
  expect(view.getByText("Review the schedule")).toBeTruthy();
  expect(
    view.container.querySelector(".tool-result-metadata")?.hasAttribute("open"),
  ).toBe(false);
  expect(
    view.container.querySelector(".tool-result-raw")?.hasAttribute("open"),
  ).toBe(false);
  expect(view.container.querySelector("pre")?.textContent).toContain("long-id");
});

test("large lists have bounded cards while retaining complete raw output", () => {
  const result = {
    items: Array.from({ length: 30 }, (_, i) => ({ name: `Item ${i}` })),
  };
  const view = render(<ToolResultContent result={JSON.stringify(result)} />);
  expect(view.getAllByRole("heading")).toHaveLength(20);
  expect(view.container.querySelector(".tool-result-raw")).toBeTruthy();
});

test.each([undefined, null, {}, { items: [], enabled: false, count: 0 }])(
  "empty and falsy output stays readable: %j",
  (result) => {
    const view = render(
      <ToolResultContent
        result={result as Record<string, unknown> | undefined}
      />,
    );
    expect(view.getByRole("region")).toBeTruthy();
    if (result && "enabled" in result) {
      expect(view.getByText("false")).toBeTruthy();
      expect(view.getByText("0")).toBeTruthy();
    }
  },
);
