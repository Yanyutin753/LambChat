// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, waitFor } from "@testing-library/react";
import { SessionItem } from "../SessionItem";
import { RecentChatsDialog } from "../RecentChatsDialog";
import { sessionApi } from "../../../services/api/session";
import type { BackendSession } from "../../../services/api/session";

vi.mock("react-i18next", async (importOriginal) => ({
  ...(await importOriginal<typeof import("react-i18next")>()),
  useTranslation: () => ({
    t: (key: string) =>
      (
        ({
          "sidebar.runningStatus": "Running",
          "sidebar.pendingStatus": "Waiting",
          "sidebar.waitingHuman": "Needs your reply",
        }) as Record<string, string>
      )[key] ?? key,
    i18n: { language: "en" },
  }),
}));
vi.mock("react-intersection-observer", () => ({
  useInView: () => ({ ref: vi.fn(), inView: false }),
}));
vi.mock("../../../hooks/useStickyDropdownPosition", () => ({
  useStickyDropdownPosition: () => ({ top: 0, left: 0 }),
}));
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const session: BackendSession = {
  id: "background",
  name: "Background work",
  agent_id: "fast",
  created_at: "2026-10-13T00:00:00Z",
  updated_at: "2026-10-13T00:00:00Z",
  is_active: true,
  metadata: {},
};

it.each(["queued", "starting", "recovering"])(
  "sidebar exposes %s background work",
  (status) => {
    const view = render(
      <SessionItem
        session={{ ...session, metadata: { task_status: status } }}
        isActive={false}
        projects={[]}
        onSelect={vi.fn()}
        onDelete={vi.fn()}
        onMoveToProject={vi.fn()}
        onSessionUpdate={vi.fn()}
      />,
    );
    expect(
      view.container.querySelector(".spinner-rotate")?.parentElement,
    ).toHaveAttribute(
      "aria-label",
      status === "recovering" ? "Running" : "Waiting",
    );
  },
);

it.each(["queued", "starting", "recovering", "waiting_human"])(
  "recent chats exposes translated %s background state",
  async (status) => {
    vi.spyOn(sessionApi, "list").mockResolvedValue([
      { ...session, metadata: { task_status: status } },
    ]);
    render(
      <RecentChatsDialog
        isOpen
        onClose={vi.fn()}
        onSelectSession={vi.fn()}
        anchorEl={document.createElement("button")}
      />,
    );
    await waitFor(() => {
      const indicator =
        status === "waiting_human"
          ? document.querySelector("[data-session-status=ask-human]")
          : document.querySelector(".spinner-rotate")?.parentElement;
      expect(indicator).toHaveAttribute(
        "aria-label",
        status === "waiting_human"
          ? "Needs your reply"
          : status === "recovering"
            ? "Running"
            : "Waiting",
      );
    });
  },
);

it("sidebar attention label follows the selected language", () => {
  const view = render(
    <SessionItem
      session={{ ...session, metadata: { task_status: "waiting_human" } }}
      isActive={false}
      projects={[]}
      onSelect={vi.fn()}
      onDelete={vi.fn()}
      onMoveToProject={vi.fn()}
      onSessionUpdate={vi.fn()}
    />,
  );
  expect(
    view.container.querySelector("[data-session-status=ask-human]"),
  ).toHaveAttribute("aria-label", "Needs your reply");
});

it.each([
  "queued",
  "pending",
  "starting",
  "running",
  "recovering",
  "waiting_human",
  "completed",
])(
  "recent chats gives %s status priority over unread count",
  async (status) => {
    vi.spyOn(sessionApi, "list").mockResolvedValue([
      { ...session, unread_count: 100, metadata: { task_status: status } },
    ]);
    const view = render(
      <RecentChatsDialog
        isOpen
        onClose={vi.fn()}
        onSelectSession={vi.fn()}
        anchorEl={document.createElement("button")}
      />,
    );
    await waitFor(() =>
      expect(view.getByText(session.name)).toBeInTheDocument(),
    );
    const unread = view.queryByLabelText("sidebar.unreadMessages");
    if (status === "completed") expect(unread).toHaveTextContent(/^99$/);
    else expect(unread).toBeNull();
  },
);
