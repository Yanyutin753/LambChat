/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ToolResultPanel } from "../../chat/ChatMessage/items/ToolResultPanel";
import { RightPanelTabs } from "../RightPanelTabs";
import {
  registerRightPanel,
  resetRightPanelCoordinator,
} from "../rightPanelCoordinator";

beforeEach(() => {
  vi.useFakeTimers();
  resetRightPanelCoordinator();
});
afterEach(() => {
  cleanup();
  resetRightPanelCoordinator();
  vi.useRealTimers();
});
function setup() {
  registerRightPanel({
    id: Symbol(),
    kind: "content",
    automatic: false,
    close: () => {},
    opener: null,
    title: "__init__.py",
    path: "/workspace/src/__init__.py",
    fileType: "python",
  });
  render(<RightPanelTabs />);
  return screen.getByRole("tab", { name: "__init__.py" });
}
test("hover reveals the file name, full path and type without a native tooltip", () => {
  const tab = setup();
  expect(tab).not.toHaveAttribute("title");
  fireEvent.mouseEnter(tab);
  expect(screen.queryByRole("tooltip")).toBeNull();
  act(() => vi.advanceTimersByTime(499));
  expect(screen.queryByRole("tooltip")).toBeNull();
  act(() => vi.advanceTimersByTime(1));
  const tip = screen.getByRole("tooltip");
  expect(tip).toHaveStyle({ zIndex: 300 });
  expect(within(tip).getByText("__init__.py")).toBeVisible();
  expect(tip).toHaveTextContent("/workspace/src/__init__.py");
  expect(tip).toHaveTextContent("python");
  fireEvent.click(tab);
  expect(screen.queryByRole("tooltip")).toBeNull();
});
test("keyboard focus reveals details and Escape dismisses them", () => {
  const tab = setup();
  fireEvent.keyDown(document, { key: "Tab" });
  fireEvent.focusIn(tab);
  const tip = screen.getByRole("tooltip");
  expect(tab).toHaveAttribute("aria-describedby", tip.id);
  fireEvent.keyDown(tab, { key: "Escape" });
  expect(screen.queryByRole("tooltip")).toBeNull();
});
test("a tap stays quiet, long press reveals details, and scrolling cancels it", () => {
  const tab = setup();
  fireEvent.touchStart(tab, { touches: [{ clientX: 20, clientY: 20 }] });
  fireEvent.touchEnd(tab);
  fireEvent.click(tab);
  expect(screen.queryByRole("tooltip")).toBeNull();
  fireEvent.touchStart(tab, { touches: [{ clientX: 20, clientY: 20 }] });
  fireEvent.touchMove(tab, { touches: [{ clientX: 50, clientY: 20 }] });
  act(() => vi.advanceTimersByTime(500));
  expect(screen.queryByRole("tooltip")).toBeNull();
  fireEvent.touchEnd(tab);
  fireEvent.touchStart(tab, { touches: [{ clientX: 20, clientY: 20 }] });
  act(() => vi.advanceTimersByTime(500));
  expect(screen.getByRole("tooltip")).toHaveTextContent(
    "/workspace/src/__init__.py",
  );
  act(() => vi.advanceTimersByTime(2000));
  expect(screen.queryByRole("tooltip")).toBeNull();
});

test("panel metadata reaches the tooltip and Escape keeps the panel open", () => {
  const onClose = vi.fn();
  render(
    <ToolResultPanel
      open
      onClose={onClose}
      title="report.pdf"
      path="/workspace/report.pdf"
      fileType="PDF"
    >
      Report
    </ToolResultPanel>,
  );
  const tab = screen.getByRole("tab", { name: "report.pdf" });
  fireEvent.keyDown(document, { key: "Tab" });
  fireEvent.focusIn(tab);
  expect(screen.getByRole("tooltip")).toHaveTextContent(
    "/workspace/report.pdf",
  );
  expect(screen.getByRole("tooltip")).toHaveTextContent("PDF");
  fireEvent.keyDown(tab, { key: "Escape" });
  expect(screen.queryByRole("tooltip")).toBeNull();
  expect(onClose).not.toHaveBeenCalled();
});

test("opening a panel does not reveal details from its automatic focus", () => {
  render(
    <ToolResultPanel open onClose={() => {}} title="report.pdf">
      Report
    </ToolResultPanel>,
  );
  const tab = screen.getByRole("tab", { name: "report.pdf" });
  act(() => tab.focus());
  expect(tab).toHaveFocus();
  expect(screen.queryByRole("tooltip")).toBeNull();
});
test("leaving or clicking before the hover delay cancels the tooltip", () => {
  const tab = setup();
  fireEvent.mouseEnter(tab);
  act(() => vi.advanceTimersByTime(250));
  fireEvent.mouseLeave(tab);
  act(() => vi.advanceTimersByTime(500));
  expect(screen.queryByRole("tooltip")).toBeNull();
  fireEvent.mouseEnter(tab);
  fireEvent.click(tab);
  act(() => vi.advanceTimersByTime(500));
  expect(screen.queryByRole("tooltip")).toBeNull();
});
