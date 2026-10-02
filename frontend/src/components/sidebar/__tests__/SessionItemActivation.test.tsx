/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { SessionItem } from "../SessionItem";
import type { BackendSession } from "../../../services/api/session";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("../../../services/api", () => ({ sessionApi: { update: vi.fn() } }));
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
const session: BackendSession = {
  id: "session-1",
  name: "Research plan",
  agent_id: "agent",
  created_at: "2026-10-01",
  updated_at: "2026-10-01",
  is_active: true,
  metadata: {},
};
const defaults = {
  session,
  isActive: true,
  projects: [],
  onDelete: vi.fn(),
  onMoveToProject: vi.fn(),
  onSessionUpdate: vi.fn(),
};

test("session title supports keyboard activation once and keeps the More action separate", async () => {
  const select = vi.fn();
  const user = userEvent.setup();
  render(<SessionItem {...defaults} onSelect={select} />);
  const title = screen.getByRole("button", {
    name: "Research plan",
    exact: true,
  });
  expect(title).toHaveAttribute("aria-current", "page");
  await user.tab();
  expect(title).toHaveFocus();
  await user.keyboard("{Enter} ");
  expect(select).toHaveBeenCalledTimes(2);
  await user.click(screen.getByRole("button", { name: "sidebar.moreOptions" }));
  expect(select).toHaveBeenCalledTimes(2);
  expect(
    screen.getByRole("button", { name: "sidebar.rename" }),
  ).toBeInTheDocument();
  expect(document.querySelector("button button")).toBeNull();
});

test("selection mode uses the title toggle without navigating or duplicate controls", async () => {
  const select = vi.fn(),
    toggle = vi.fn();
  const user = userEvent.setup();
  const { rerender } = render(
    <SessionItem
      {...defaults}
      onSelect={select}
      selectionMode
      onToggleSelected={toggle}
    />,
  );
  const title = screen.getByRole("button", { name: "Research plan" });
  expect(title).toHaveAttribute("aria-pressed", "false");
  expect(screen.getAllByRole("button")).toHaveLength(1);
  await user.click(title);
  expect(toggle).toHaveBeenCalledOnce();
  expect(select).not.toHaveBeenCalled();
  rerender(
    <SessionItem
      {...defaults}
      onSelect={select}
      selectionMode
      isSelected
      onToggleSelected={toggle}
    />,
  );
  expect(title).toHaveAttribute("aria-pressed", "true");
});

test("renaming keeps the field named and Escape returns to the title without saving", async () => {
  const { sessionApi } = await import("../../../services/api");
  const select = vi.fn();
  const user = userEvent.setup();
  render(<SessionItem {...defaults} onSelect={select} />);
  await user.click(screen.getByRole("button", { name: "sidebar.moreOptions" }));
  await user.click(
    screen.getByRole("button", { name: "sidebar.rename", exact: true }),
  );
  const field = screen.getByRole("textbox", {
    name: "sidebar.rename Research plan",
  });
  expect(field).toHaveFocus();
  await user.clear(field);
  await user.type(field, "Draft name");
  await user.keyboard("{Escape}");
  expect(screen.getByRole("button", { name: "Research plan" })).toHaveFocus();
  expect(sessionApi.update).not.toHaveBeenCalled();
  expect(select).not.toHaveBeenCalled();
});

test.each(["blur", "Enter"])(
  "a delayed rename saved by %s keeps focus on the next action",
  async (finish) => {
    const { sessionApi } = await import("../../../services/api");
    let finishSave!: () => void;
    const save = new Promise<Awaited<ReturnType<typeof sessionApi.update>>>(
      (resolve) => {
        finishSave = () =>
          resolve({
            status: "ok",
            session: { ...session, name: "Draft name" },
          });
      },
    );
    vi.mocked(sessionApi.update).mockReturnValue(save);
    const user = userEvent.setup();
    render(
      <>
        <SessionItem {...defaults} onSelect={vi.fn()} />
        <button>Search sessions</button>
      </>,
    );
    await user.click(
      screen.getByRole("button", { name: "sidebar.moreOptions" }),
    );
    await user.click(
      screen.getByRole("button", { name: "sidebar.rename", exact: true }),
    );
    const field = screen.getByRole("textbox", {
      name: "sidebar.rename Research plan",
    });
    await user.clear(field);
    await user.type(field, "Draft name");
    if (finish === "Enter") await user.keyboard("{Enter}");
    const next = screen.getByRole("button", { name: "Search sessions" });
    await user.click(next);
    expect(next).toHaveFocus();
    await act(async () => finishSave());
    expect(next).toHaveFocus();
  },
);

test("desktop session options focus each panel and Escape returns to the opener", async () => {
  const user = userEvent.setup();
  render(<SessionItem {...defaults} onSelect={vi.fn()} />);
  const opener = screen.getByRole("button", { name: "sidebar.moreOptions" });
  await user.click(opener);
  expect(
    screen.getByRole("group", { name: "sidebar.sessionOptions" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "sidebar.rename" })).toHaveFocus();
  await user.tab();
  await user.keyboard("{Enter}");
  expect(
    screen.getByRole("button", { name: "sidebar.moveToProject" }),
  ).toHaveFocus();
  expect(
    screen.getByRole("button", { name: "sidebar.uncategorized" }),
  ).toBeInTheDocument();
  await user.keyboard("{Escape}");
  expect(
    screen.queryByRole("button", { name: "sidebar.uncategorized" }),
  ).toBeNull();
  expect(screen.getByRole("button", { name: "sidebar.rename" })).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(opener).toHaveFocus();
  expect(
    screen.queryByRole("group", { name: "sidebar.sessionOptions" }),
  ).toBeNull();
});

test("opening session options hides the trigger tooltip without hiding the button", async () => {
  const user = userEvent.setup();
  render(<SessionItem {...defaults} onSelect={vi.fn()} />);
  const opener = screen.getByRole("button", { name: "sidebar.moreOptions" });
  await user.hover(opener);
  expect(screen.getByText("sidebar.moreOptions")).toBeVisible();
  await user.click(opener);
  expect(screen.queryByText("sidebar.moreOptions")).toBeNull();
  expect(opener).toBeVisible();
});

test.each(["forward", "backward"])(
  "%s Tab exits the desktop session options into the sidebar",
  async (direction) => {
    const user = userEvent.setup();
    render(
      <>
        <SessionItem {...defaults} onSelect={vi.fn()} />
        <button>Next sidebar action</button>
      </>,
    );
    await user.click(
      screen.getByRole("button", { name: "sidebar.moreOptions" }),
    );
    expect(
      screen.getByRole("button", { name: "sidebar.rename" }),
    ).toHaveFocus();
    if (direction === "forward") {
      await user.tab();
      await user.tab();
      expect(
        screen.getByRole("button", { name: "common.delete" }),
      ).toHaveFocus();
    }
    await user.tab({ shift: direction === "backward" });
    expect(screen.queryByRole("button", { name: "sidebar.rename" })).toBeNull();
    expect(
      screen.getByRole("button", {
        name: direction === "forward" ? "Next sidebar action" : "Research plan",
      }),
    ).toHaveFocus();
  },
);

test("a touch drag suppresses the next title activation", () => {
  vi.useFakeTimers();
  try {
    const select = vi.fn(),
      drag = vi.fn();
    render(
      <SessionItem {...defaults} onSelect={select} onDragStartTouch={drag} />,
    );
    const title = screen.getByRole("button", { name: "Research plan" });
    fireEvent.touchStart(title, { touches: [{ clientX: 12, clientY: 30 }] });
    vi.advanceTimersByTime(400);
    expect(drag).toHaveBeenCalledWith("session-1", 12, 30);
    fireEvent.click(title);
    expect(select).not.toHaveBeenCalled();
  } finally {
    vi.useRealTimers();
  }
});
