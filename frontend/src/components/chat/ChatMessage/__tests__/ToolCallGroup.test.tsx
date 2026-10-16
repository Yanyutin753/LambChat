/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import userEvent from "@testing-library/user-event";
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
  expect(
    view.container.querySelector(".chat-tool-call-group__status"),
  ).toBeNull();
  expect(screen.getByRole("button")).toHaveTextContent("2");
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

test("tool groups support keyboard expansion and only render contents when opened", async () => {
  const user = userEvent.setup();
  const content = vi.fn(() => <div>Expanded tools</div>);
  const view = render(
    <ToolCallGroup
      category="execute"
      count={2}
      stateKey="keyboard:tools"
      renderExpanded={content}
    />,
  );
  expect(content).not.toHaveBeenCalled();
  const trigger = screen.getByRole("button", { expanded: false });
  await user.tab();
  expect(trigger).toHaveFocus();
  await user.keyboard("{Enter}");
  const panelId = trigger.getAttribute("aria-controls");
  expect(panelId).toBeTruthy();
  expect(view.container.querySelector(`[id="${panelId}"]`)).toHaveTextContent(
    "Expanded tools",
  );
  await user.keyboard(" ");
  expect(trigger).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByText("Expanded tools")).toBeNull();
});
