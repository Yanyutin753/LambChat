/** @vitest-environment jsdom */
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import i18n from "../../../../i18n";
import type { ScheduledTaskCreate } from "../../../../types/scheduledTask";

const api = vi.hoisted(() => ({
  listBySession: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
  pause: vi.fn(),
  resume: vi.fn(),
  runNow: vi.fn(),
}));
const auth = vi.hoisted(() => ({ write: true }));
vi.mock("../../../../services/api/scheduledTask", () => ({
  scheduledTaskApi: api,
}));
vi.mock("../../../../hooks/useAuth", () => ({
  useAuth: () => ({
    hasPermission: (permission: string) =>
      !permission.includes("write") || auth.write,
  }),
}));
vi.mock("../../../agent/useAgentCatalog", () => ({
  useAgentCatalog: () => [],
}));
vi.mock("../../../../contexts/SettingsContext", () => ({
  useSettingsContext: () => ({ availableModels: null }),
}));
vi.mock("../../../common/EditorSidebar", () => ({
  EditorSidebar: ({
    children,
    footer,
  }: {
    children: React.ReactNode;
    footer: React.ReactNode;
  }) => (
    <div>
      {children}
      {footer}
    </div>
  ),
}));
vi.mock("../TaskFormModal", () => ({
  TaskFormModal: ({
    defaultSessionId,
    task,
    onSave,
  }: {
    defaultSessionId: string;
    task: { id: string } | null;
    onSave: (data: ScheduledTaskCreate) => Promise<void>;
  }) => (
    <button
      onClick={() =>
        void onSave({
          name: "Watch release",
          agent_id: "search",
          trigger_type: "interval",
          trigger_config: { seconds: 300 },
          input_payload: { message: "Report changes" },
          execution_mode: "conversation",
          target_session_id: defaultSessionId,
        }).catch(() => undefined)
      }
    >
      Save {task?.id || defaultSessionId}
    </button>
  ),
}));
import { SessionScheduledTasksPanel } from "../SessionScheduledTasksPanel";

const task = {
  id: "task-1",
  name: "Release watch",
  agent_id: "search",
  status: "active",
  enabled: true,
  trigger_type: "interval",
  trigger_config: { seconds: 300 },
  input_payload: {},
  timezone: "Asia/Shanghai",
};
function Location() {
  return <p>{useLocation().pathname}</p>;
}
function mount() {
  return render(
    <MemoryRouter initialEntries={["/chat/chat-1"]}>
      <Location />
      <SessionScheduledTasksPanel sessionId="chat-1" onClose={vi.fn()} />
    </MemoryRouter>,
  );
}
beforeEach(() => {
  vi.clearAllMocks();
  auth.write = true;
  api.listBySession.mockResolvedValue({ items: [task], total: 1 });
  api.create.mockResolvedValue(task);
  api.update.mockResolvedValue(task);
});
afterEach(cleanup);

test("creates and edits schedules without navigating away from the chat", async () => {
  mount();
  await screen.findByText(task.name);
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("scheduledTask.create") }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Save chat-1" }));
  await waitFor(() => expect(api.create).toHaveBeenCalledOnce());
  await screen.findByText(task.name);
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("scheduledTask.edit") }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Save task-1" }));
  await waitFor(() =>
    expect(api.update).toHaveBeenCalledWith(
      "task-1",
      expect.objectContaining({ target_session_id: "chat-1" }),
    ),
  );
  expect(screen.getByText("/chat/chat-1")).toBeVisible();
});

test("failed saves keep the editor open for retry", async () => {
  api.create.mockRejectedValueOnce(new Error("offline"));
  mount();
  await screen.findByText(task.name);
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("scheduledTask.create") }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Save chat-1" }));
  await waitFor(() => expect(api.create).toHaveBeenCalledOnce());
  expect(screen.getByRole("button", { name: "Save chat-1" })).toBeVisible();
});

test("read-only users cannot create, edit, or run tasks", async () => {
  auth.write = false;
  mount();
  await screen.findByText(task.name);
  for (const key of ["create", "edit", "runNow", "pause"])
    expect(
      screen.queryByRole("button", { name: i18n.t(`scheduledTask.${key}`) }),
    ).toBeNull();
});

test("pending actions prevent duplicate manual executions", async () => {
  let finish!: () => void;
  api.runNow.mockReturnValueOnce(
    new Promise<void>((resolve) => {
      finish = resolve;
    }),
  );
  mount();
  await screen.findByText(task.name);
  const run = screen.getByRole("button", {
    name: i18n.t("scheduledTask.runNow"),
  });
  fireEvent.click(run);
  fireEvent.click(run);
  expect(api.runNow).toHaveBeenCalledOnce();
  expect(run).toBeDisabled();
  await act(async () => finish());
});

test("failed loading exposes retry rather than a false empty state", async () => {
  api.listBySession.mockRejectedValueOnce(new Error("offline"));
  mount();
  fireEvent.click(
    await screen.findByRole("button", { name: i18n.t("common.retry") }),
  );
  expect(await screen.findByText(task.name)).toBeVisible();
});

test("session schedules paginate instead of silently truncating the list", async () => {
  api.listBySession.mockResolvedValue({ items: [task], total: 25 });
  mount();
  await screen.findByText(task.name);
  fireEvent.click(screen.getByRole("button", { name: i18n.t("common.next") }));
  await waitFor(() =>
    expect(api.listBySession).toHaveBeenLastCalledWith("chat-1", 20, 20),
  );
});

test("refresh keeps the existing tasks visible while loading and after a refresh failure", async () => {
  mount();
  await screen.findByText(task.name);
  let fail!: (error: Error) => void;
  api.listBySession.mockReturnValueOnce(
    new Promise((_, reject) => {
      fail = reject;
    }),
  );
  fireEvent.click(
    screen.getByRole("button", { name: i18n.t("common.refresh") }),
  );
  expect(screen.getByText(task.name)).toBeVisible();
  await act(async () => fail(new Error("offline")));
  expect(screen.getByText(task.name)).toBeVisible();
  expect(screen.getByRole("alert")).toHaveTextContent(
    i18n.t("common.loadFailed"),
  );
});
