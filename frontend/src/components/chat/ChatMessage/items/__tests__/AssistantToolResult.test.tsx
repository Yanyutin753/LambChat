// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test } from "vitest";
import { AssistantToolResult } from "../AssistantToolResult";

afterEach(cleanup);

test("assistant results use search-style cards and resolve member names", () => {
  const result = {
    assistants: [
      {
        id: "group/id",
        name: "Delivery",
        kind: "group",
        member_ids: ["reviewer"],
        status: "active",
        instructions: "Review schedule",
      },
      { id: "reviewer", name: "Reviewer", kind: "assistant" },
    ],
  };
  const view = render(<AssistantToolResult result={JSON.stringify(result)} />);
  expect(view.getAllByRole("article")).toHaveLength(2);
  expect(
    view.container.querySelectorAll('[data-avatar-style="boring"]'),
  ).toHaveLength(2);
  expect(view.getByRole("heading", { name: "Delivery" })).toBeTruthy();
  expect(
    view.container.querySelector(".assistant-tool-card__members")?.textContent,
  ).toContain("Reviewer");
  expect(view.container.querySelector("a")?.getAttribute("href")).toBe(
    "/assistants/group%2Fid",
  );
  expect(
    view.container.querySelector(".tool-result-raw")?.hasAttribute("open"),
  ).toBe(false);
  expect(view.container.querySelector("pre")?.textContent).toContain(
    "group/id",
  );
});

test("long instructions can be expanded without losing content", () => {
  const instructions = "Detailed instructions. ".repeat(30);
  const view = render(
    <AssistantToolResult
      result={{ id: "a", name: "Assistant", instructions }}
    />,
  );
  const details = view.container.querySelector(".assistant-tool-instructions")!;
  fireEvent.click(details.querySelector("summary")!);
  expect(details.hasAttribute("open")).toBe(true);
  expect(details.querySelector("p")?.textContent).toBe(instructions);
});

test.each([
  { assistants: [] },
  { assistants: [null] },
  { error: "unavailable" },
  undefined,
])("handles empty, malformed and pending results: %j", (result) => {
  const view = render(<AssistantToolResult result={result} />);
  expect(view.container.textContent).toBeTruthy();
  expect(view.queryAllByRole("article")).toHaveLength(0);
});
