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

test("delayed hover shows title, chat type, update time and an accessible unread count without marking read", () => {
  vi.useFakeTimers();
  render(<SessionItem {...props} />);
  fireEvent.mouseEnter(screen.getByRole("button", { name: session.name }));
  expect(screen.queryByRole("tooltip")).toBeNull();
  act(() => vi.advanceTimersByTime(500));
  const preview = screen.getByRole("tooltip");
  expect(within(preview).getByText(session.name)).toHaveClass(
    "line-clamp-3",
    "text-theme-text-secondary",
    "font-normal",
  );
  expect(within(preview).getByText("nav.chat")).toBeInTheDocument();
  expect(preview.querySelector("time")).toHaveAttribute(
    "dateTime",
    session.updated_at,
  );
  expect(preview.querySelector("time")?.parentElement).toHaveClass(
    "items-baseline",
  );
  expect(preview.querySelector("time")).toHaveClass("leading-5");
  expect(
    within(preview).getByLabelText("sidebar.unreadMessages"),
  ).toHaveTextContent("3");
  expect(props.onSelect).not.toHaveBeenCalled();
  expect(screen.getAllByText("3")).toHaveLength(2);
  fireEvent.keyDown(screen.getByRole("button", { name: session.name }), {
    key: "Escape",
  });
  expect(screen.queryByRole("tooltip")).toBeNull();
});

test("keyboard focus opens the preview and active sessions have no unread count", () => {
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

test.each([
  [1, "1"],
  [12, "12"],
  [9, "9"],
  [99, "99"],
  [100, "99"],
  [10000, "99"],
] as const)("sidebar shows unread count %s as %s", (count, label) => {
  render(
    <SessionItem {...props} session={{ ...session, unread_count: count }} />,
  );
  expect(screen.getByLabelText("sidebar.unreadMessages")).toHaveTextContent(
    new RegExp(`^${label}$`),
  );
});

test.each([
  "queued",
  "pending",
  "starting",
  "running",
  "recovering",
  "waiting_human",
])(
  "%s status takes priority over unread count in row and preview",
  (status) => {
    vi.useFakeTimers();
    const view = render(
      <SessionItem
        {...props}
        session={{ ...session, metadata: { task_status: status } }}
      />,
    );
    fireEvent.mouseEnter(screen.getByRole("button", { name: session.name }));
    act(() => vi.advanceTimersByTime(500));
    expect(screen.getByRole("tooltip")).toBeInTheDocument();
    expect(screen.queryByLabelText("sidebar.unreadMessages")).toBeNull();
    view.rerender(
      <SessionItem
        {...props}
        session={{ ...session, metadata: { task_status: "completed" } }}
      />,
    );
    expect(screen.getAllByLabelText("sidebar.unreadMessages")).toHaveLength(2);
  },
);

test.each([0, undefined])("sidebar hides empty unread count %s", (count) => {
  render(
    <SessionItem {...props} session={{ ...session, unread_count: count }} />,
  );
  expect(screen.queryByLabelText("sidebar.unreadMessages")).toBeNull();
});
