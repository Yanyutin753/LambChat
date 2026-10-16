/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { SessionItem } from "../SessionItem";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../services/api", () => ({ sessionApi: { update: vi.fn() } }));
afterEach(() => {
  cleanup();
  vi.useRealTimers();
});
const session = {
  id: "preview",
  name: "A complete conversation title",
  agent_id: "fast",
  created_at: "2026-10-16T00:00:00Z",
  updated_at: "2026-10-16T01:00:00Z",
  is_active: true,
  metadata: {},
  unread_count: 3,
};
const props = {
  session,
  isActive: false,
  projects: [],
  onSelect: vi.fn(),
  onDelete: vi.fn(),
  onMoveToProject: vi.fn(),
  onSessionUpdate: vi.fn(),
};

test("delayed hover shows title, chat type, update time and an accessible unread dot without marking read", () => {
  vi.useFakeTimers();
  render(<SessionItem {...props} />);
  fireEvent.mouseEnter(screen.getByRole("button", { name: session.name }));
  expect(screen.queryByRole("tooltip")).toBeNull();
  act(() => vi.advanceTimersByTime(500));
  const preview = screen.getByRole("tooltip");
  expect(within(preview).getByText(session.name)).toBeInTheDocument();
  expect(within(preview).getByText("nav.chat")).toBeInTheDocument();
  expect(preview.querySelector("time")).toHaveAttribute(
    "dateTime",
    session.updated_at,
  );
  expect(
    within(preview).getByLabelText("sidebar.unreadMessages"),
  ).toBeInTheDocument();
  expect(props.onSelect).not.toHaveBeenCalled();
  expect(screen.queryByText("3")).toBeNull();
  fireEvent.keyDown(screen.getByRole("button", { name: session.name }), {
    key: "Escape",
  });
  expect(screen.queryByRole("tooltip")).toBeNull();
});

test("keyboard focus opens the preview and active sessions have no unread dot", () => {
  render(<SessionItem {...props} isActive />);
  fireEvent.keyDown(document, { key: "Tab" });
  fireEvent.focus(screen.getByRole("button", { name: session.name }));
  expect(screen.getByRole("tooltip")).toBeInTheDocument();
  expect(screen.queryByLabelText("sidebar.unreadMessages")).toBeNull();
});

test("touch drag and selection mode suppress the preview", () => {
  vi.useFakeTimers();
  const view = render(<SessionItem {...props} />);
  const button = screen.getByRole("button", { name: session.name });
  fireEvent.touchStart(button, { touches: [{ clientX: 10, clientY: 10 }] });
  act(() => vi.advanceTimersByTime(600));
  expect(screen.queryByRole("tooltip")).toBeNull();
  view.rerender(<SessionItem {...props} selectionMode />);
  fireEvent.mouseEnter(screen.getByRole("checkbox", { name: session.name }));
  act(() => vi.advanceTimersByTime(600));
  expect(screen.queryByRole("tooltip")).toBeNull();
});

test("preview anchors to the full row and aligns its top edge", () => {
  vi.useFakeTimers();
  render(<SessionItem {...props} />);
  const row = screen.getByRole("group", { name: session.name });
  vi.spyOn(row, "getBoundingClientRect").mockReturnValue({
    x: 20,
    y: 100,
    left: 20,
    top: 100,
    right: 280,
    bottom: 132,
    width: 260,
    height: 32,
    toJSON: () => ({}),
  });
  fireEvent.mouseEnter(screen.getByRole("button", { name: session.name }));
  act(() => vi.advanceTimersByTime(500));
  expect(screen.getByRole("tooltip")).toHaveStyle({
    top: "100px",
    left: "290px",
  });
});
