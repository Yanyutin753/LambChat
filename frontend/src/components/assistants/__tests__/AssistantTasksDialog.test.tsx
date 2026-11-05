/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AssistantTasksDialog } from "../AssistantTasksDialog";
import type { Assistant } from "../../../types/assistant";

const { api, sessionApi, navigate, t } = vi.hoisted(() => ({
  api: { tasks: vi.fn(), createTask: vi.fn(), reviewTask: vi.fn() },
  sessionApi: { cancel: vi.fn() },
  navigate: vi.fn(),
  t: (key: string) => key,
}));
vi.mock("../../../services/api/assistant", () => ({ assistantApi: api }));
vi.mock("../../../services/api/session", () => ({ sessionApi }));
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t }) }));
const assistant = {
  id: "helper",
  name: "Researcher",
  status: "active",
} as Assistant;
const task = {
  id: "task",
  description: "Find sources",
  session_id: "child",
  run_id: "run-2",
  state: "awaiting_review",
  review_revision: 3,
  timeout_seconds: 300,
  created_at: "2026-11-04T00:00:00Z",
};
beforeEach(() => {
  api.tasks.mockResolvedValue({ tasks: [task], total: 1 });
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});

test("completed work opens directly without manual acceptance", async () => {
  api.tasks.mockResolvedValue({
    tasks: [{ ...task, state: "completed" }],
    total: 1,
  });
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  expect(
    await screen.findByText("assistants.taskStates.completed"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "assistants.acceptTask" }),
  ).toBeNull();
  fireEvent.click(
    screen.getByRole("button", { name: "assistants.inspectTask" }),
  );
  expect(navigate).toHaveBeenCalledWith("/assistants/helper/chat/child");
});

test("network retry keeps the task admission key and draft", async () => {
  api.createTask
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ status: "queued" });
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "assistants.newTask" }));
  fireEvent.change(screen.getByLabelText("assistants.taskDescription"), {
    target: { value: "Create a verified report" },
  });
  fireEvent.click(screen.getByRole("button", { name: "assistants.startTask" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("offline");
  expect(screen.getByLabelText("assistants.taskDescription")).toHaveValue(
    "Create a verified report",
  );
  fireEvent.click(screen.getByRole("button", { name: "assistants.startTask" }));
  await waitFor(() => expect(api.createTask).toHaveBeenCalledTimes(2));
  expect(api.createTask.mock.calls[0][1]).toEqual(
    api.createTask.mock.calls[1][1],
  );
  expect(api.createTask.mock.calls[0][1].request_id).toBeTruthy();
});

test("activity comes first and the new task draft survives collapsing its form", async () => {
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  expect(
    await screen.findByRole("heading", { name: task.description }),
  ).toBeVisible();
  expect(screen.queryByLabelText("assistants.taskDescription")).toBeNull();
  const toggle = screen.getByRole("button", { name: "assistants.newTask" });
  fireEvent.click(toggle);
  fireEvent.change(screen.getByLabelText("assistants.taskDescription"), {
    target: { value: "Keep my draft" },
  });
  fireEvent.click(toggle);
  fireEvent.click(toggle);
  expect(screen.getByLabelText("assistants.taskDescription")).toHaveValue(
    "Keep my draft",
  );
});

test("groups the current page by attention, active work and history without dropping tasks", async () => {
  api.tasks.mockResolvedValue({
    total: 31,
    tasks: [
      { ...task, id: "done", description: "Finished work", state: "accepted" },
      { ...task, id: "working", description: "Working now", state: "running" },
      {
        ...task,
        id: "approval",
        description: "Approve this",
        state: "waiting_human",
      },
      {
        ...task,
        id: "unknown",
        description: "Unknown state",
        state: "future_state",
      },
    ],
  });
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  const attention = await screen.findByRole("region", {
    name: "assistants.taskGroups.attention",
  });
  expect(
    within(attention).getByRole("heading", { name: "Approve this" }),
  ).toBeVisible();
  expect(
    within(attention).getByRole("heading", { name: "Unknown state" }),
  ).toBeVisible();
  expect(
    screen
      .getAllByRole("region")
      .map((region) => region.getAttribute("aria-label")),
  ).toEqual([
    "assistants.taskGroups.attention",
    "assistants.taskGroups.active",
    "assistants.taskGroups.history",
  ]);
  expect(screen.getByText("assistants.pageGroupingHint")).toBeVisible();
  expect(screen.getAllByRole("listitem")).toHaveLength(4);
});

test("execution details and task IDs remain available without crowding the activity list", async () => {
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  const details = (await screen.findByText("assistants.taskDetails")).closest(
    "details",
  )!;
  expect(details).not.toHaveAttribute("open");
  expect(
    within(details).getByText("assistants.taskReference"),
  ).toBeInTheDocument();
});

test("a successful task admission clears and closes the form, while a new task gets a new key", async () => {
  api.createTask.mockResolvedValue({ status: "queued" });
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  for (const description of ["First task", "Second task"]) {
    fireEvent.click(screen.getByRole("button", { name: "assistants.newTask" }));
    const field = screen.getByLabelText("assistants.taskDescription");
    expect(field).toHaveFocus();
    expect(field).toHaveValue("");
    fireEvent.change(field, { target: { value: description } });
    fireEvent.click(
      screen.getByRole("button", { name: "assistants.startTask" }),
    );
    await waitFor(() =>
      expect(screen.queryByLabelText("assistants.taskDescription")).toBeNull(),
    );
  }
  expect(api.createTask.mock.calls[0][1].request_id).not.toBe(
    api.createTask.mock.calls[1][1].request_id,
  );
});

test("load failures do not show an empty inbox and can be retried", async () => {
  api.tasks
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValue({ tasks: [], total: 0 });
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("offline");
  expect(screen.queryByText("assistants.noTasks")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "common.refresh" }));
  expect(await screen.findByText("assistants.noTasks")).toBeVisible();
});

test("legacy acceptance is retained without obsolete review controls", async () => {
  api.tasks.mockResolvedValue({
    tasks: [{ ...task, state: "accepted" }],
    total: 1,
  });
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  await screen.findByText("assistants.taskStates.accepted");
  expect(
    screen.queryByRole("button", {
      name: "assistants.rejectTask",
      hidden: true,
    }),
  ).toBeNull();
});

test("changing pages keeps the known total while the next page loads", async () => {
  api.tasks.mockImplementation((_id, skip) =>
    Promise.resolve({
      total: 11,
      tasks: [{ ...task, description: skip ? "Second page" : "First page" }],
    }),
  );
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  await screen.findByRole("heading", { name: "First page" });
  fireEvent.click(screen.getByRole("button", { name: "common.next" }));
  expect(
    await screen.findByRole("heading", { name: "Second page" }),
  ).toBeVisible();
  expect(api.tasks).toHaveBeenLastCalledWith("helper", 10, 10);
});

test("readers can inspect the real child conversation without write controls", async () => {
  render(
    <AssistantTasksDialog
      assistant={assistant}
      canWrite={false}
      onClose={() => {}}
    />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.inspectTask" }),
  );
  expect(navigate).toHaveBeenCalledWith("/assistants/helper/chat/child");
  expect(
    screen.queryByRole("button", { name: "assistants.startTask" }),
  ).toBeNull();
  expect(
    screen.queryByRole("button", { name: "assistants.acceptTask" }),
  ).toBeNull();
});

test("long task requirements leave room for controls and open the full conversation", async () => {
  const description = "Review the source and preserve all evidence. ".repeat(
    100,
  );
  api.tasks.mockResolvedValue({ tasks: [{ ...task, description }], total: 1 });
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  expect(
    await screen.findByRole("heading", { name: description.trim() }),
  ).toHaveClass("line-clamp-3");
  fireEvent.click(
    screen.getByRole("button", { name: "assistants.inspectTask" }),
  );
  expect(navigate).toHaveBeenCalledWith("/assistants/helper/chat/child");
});

test("stopping a task submits the displayed run identity", async () => {
  api.tasks.mockResolvedValue({
    tasks: [{ ...task, state: "running" }],
    total: 1,
  });
  sessionApi.cancel.mockResolvedValue({ success: true });
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.stopTask" }),
  );
  await waitFor(() =>
    expect(sessionApi.cancel).toHaveBeenCalledWith("child", "run-2"),
  );
});

test("task activity displays a deadline and separates authorized turns from recovery", async () => {
  api.tasks.mockResolvedValue({
    tasks: [
      {
        ...task,
        deadline_at: "2026-11-04T00:05:00Z",
        authorized_turns: 2,
        recovery_attempts: 3,
      },
    ],
    total: 1,
  });
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  expect(await screen.findByText("assistants.taskBudget")).toBeInTheDocument();
  expect(screen.getByText("assistants.taskAttempts")).toBeInTheDocument();
  expect(screen.getByText("assistants.taskDeadline")).toBeInTheDocument();
});

test("notification journal entries are distinguished from transport acceptance", async () => {
  api.tasks.mockResolvedValue({
    total: 1,
    tasks: [
      {
        ...task,
        authorization: { kind: "rule" },
        notification: {
          recorded_at: "2026-11-04T00:05:00Z",
          status: "completed",
          accepted_transports: [],
        },
      },
    ],
  });
  render(
    <AssistantTasksDialog
      assistant={assistant}
      canWrite={false}
      onClose={() => {}}
    />,
  );
  expect(
    await screen.findByText("assistants.receiptRecorded"),
  ).toBeInTheDocument();
  expect(screen.queryByText("assistants.receiptAccepted")).toBeNull();
  expect(screen.getByText("assistants.authorization.rule")).toBeInTheDocument();
});

test("workspace task titles open the result in place and preserve full requirements in details", async () => {
  const description = "【金额汇总】仅在 task-b 目录创建文件，并运行完整测试。";
  api.tasks.mockResolvedValue({
    tasks: [{ ...task, description, state: "accepted" }],
    total: 1,
  });
  render(
    <AssistantTasksDialog
      assistant={assistant}
      canWrite
      embedded
      onClose={() => {}}
    />,
  );
  fireEvent.click(await screen.findByRole("button", { name: "金额汇总" }));
  expect(navigate).toHaveBeenCalledWith("/assistants/helper/chat/child");
  expect(screen.getByText(description).closest("details")).not.toBeNull();
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("new workspace tasks immediately open their admitted conversation", async () => {
  api.createTask.mockResolvedValue({
    status: "queued",
    task_id: "new",
    session_id: "new-child",
  });
  const close = vi.fn();
  render(
    <AssistantTasksDialog
      assistant={assistant}
      canWrite
      embedded
      onClose={close}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "assistants.newTask" }));
  fireEvent.change(screen.getByLabelText("assistants.taskDescription"), {
    target: { value: "Verify sources" },
  });
  fireEvent.click(screen.getByRole("button", { name: "assistants.startTask" }));
  await waitFor(() =>
    expect(navigate).toHaveBeenCalledWith("/assistants/helper/chat/new-child"),
  );
  expect(close).toHaveBeenCalledOnce();
});

test("failed admission retains the draft and does not navigate", async () => {
  api.createTask.mockResolvedValue({
    status: "error",
    session_id: "failed-child",
  });
  render(
    <AssistantTasksDialog
      assistant={assistant}
      canWrite
      embedded
      onClose={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "assistants.newTask" }));
  fireEvent.change(screen.getByLabelText("assistants.taskDescription"), {
    target: { value: "Keep this" },
  });
  fireEvent.click(screen.getByRole("button", { name: "assistants.startTask" }));
  await screen.findByRole("alert");
  expect(navigate).not.toHaveBeenCalled();
  expect(screen.getByLabelText("assistants.taskDescription")).toHaveValue(
    "Keep this",
  );
});

test("Chief's delegated work opens in the receiving assistant workspace", async () => {
  api.tasks.mockResolvedValue({
    tasks: [{ ...task, assistant_id: "writer", state: "completed" }],
    total: 1,
  });
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.inspectTask" }),
  );
  expect(navigate).toHaveBeenCalledWith("/assistants/writer/chat/child");
});
