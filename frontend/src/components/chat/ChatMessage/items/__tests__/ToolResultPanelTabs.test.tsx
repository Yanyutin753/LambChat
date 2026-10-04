/** @vitest-environment jsdom */

import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { resetRightPanelCoordinator } from "../../../../common/rightPanelCoordinator";
import { ToolResultPanel } from "../ToolResultPanel";

afterEach(() => {
  cleanup();
  resetRightPanelCoordinator();
});

test("execution tabs identify their commands and switch to the matching panel", () => {
  const view = render(
    <>
      <ToolResultPanel
        open
        onClose={vi.fn()}
        title="执行"
        subtitle="lscpu | head -20"
      >
        CPU output
      </ToolResultPanel>
      <ToolResultPanel open onClose={vi.fn()} title="执行" subtitle="free -h">
        Memory output
      </ToolResultPanel>
    </>,
  );

  const cpuTab = view.getByRole("tab", { name: "执行 · lscpu | head -20" });
  expect(cpuTab).toHaveAttribute("title", "执行 · lscpu | head -20");
  expect(view.getByRole("tab", { name: "执行 · free -h" })).toHaveAttribute(
    "aria-selected",
    "true",
  );

  fireEvent.click(cpuTab);
  expect(view.getByRole("tab", { selected: true })).toHaveTextContent(
    "执行 · lscpu | head -20",
  );
  expect(view.getByRole("tabpanel")).toHaveTextContent("CPU output");
});

test.each([undefined, "", " \n\t "])(
  "tool tabs retain the title when their summary is %j",
  (subtitle) => {
    const view = render(
      <ToolResultPanel open onClose={vi.fn()} title="执行" subtitle={subtitle}>
        Output
      </ToolResultPanel>,
    );

    expect(view.getByRole("tab", { name: "执行" })).toHaveAttribute(
      "title",
      "执行",
    );
  },
);

test("tool tabs update their summaries without replacing the active tab", () => {
  const onClose = vi.fn();
  const view = render(
    <ToolResultPanel open onClose={onClose} title="搜索">
      Results
    </ToolResultPanel>,
  );
  const panelId = view.getByRole("tab").getAttribute("aria-controls");

  view.rerender(
    <ToolResultPanel
      open
      onClose={onClose}
      title="搜索"
      subtitle={"  React\n  hooks  "}
    >
      Results
    </ToolResultPanel>,
  );

  const tab = view.getByRole("tab", { name: "搜索 · React hooks" });
  expect(tab).toHaveAttribute("aria-controls", panelId);
  expect(tab).toHaveAttribute("aria-selected", "true");
  expect(tab).toHaveAttribute("title", "搜索 · React hooks");
});
