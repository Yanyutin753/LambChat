/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ToolCallGroup } from "../ToolCallGroup";
import { clearUiExpansions } from "../uiExpansionStore";
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { count?: number }) =>
      `${key} ${options?.count ?? ""}`,
  }),
}));
afterEach(() => {
  cleanup();
  clearUiExpansions();
});
test("several tools start collapsed and preserve a deliberate expansion when appended or remounted", () => {
  const content = () => <div>Read files and run checks</div>;
  const view = render(
    <ToolCallGroup
      category="read"
      count={2}
      stateKey="message:tools:first"
      renderExpanded={content}
    />,
  );
  expect(screen.queryByText("Read files and run checks")).toBeNull();
  fireEvent.click(screen.getByRole("button", { expanded: false }));
  expect(screen.getByText("Read files and run checks")).toBeVisible();
  view.rerender(
    <ToolCallGroup
      category="read"
      count={3}
      stateKey="message:tools:first"
      renderExpanded={content}
    />,
  );
  expect(screen.getByRole("button", { expanded: true })).toHaveTextContent("3");
  view.unmount();
  render(
    <ToolCallGroup
      category="read"
      count={3}
      stateKey="message:tools:first"
      renderExpanded={content}
    />,
  );
  expect(screen.getByText("Read files and run checks")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { expanded: true }));
  expect(screen.queryByText("Read files and run checks")).toBeNull();
});
