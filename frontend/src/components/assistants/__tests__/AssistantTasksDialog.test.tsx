/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
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

test("completed work needs explicit review tied to the displayed run", async () => {
  api.reviewTask.mockResolvedValue({ ...task, state: "accepted" });
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
  expect(
    await screen.findByText("assistants.taskStates.awaiting_review"),
  ).toBeInTheDocument();
  fireEvent.click(
    screen.getByRole("button", { name: "assistants.acceptTask" }),
  );
  await waitFor(() =>
    expect(api.reviewTask).toHaveBeenCalledWith("helper", "task", {
      run_id: "run-2",
      revision: 3,
      accepted: true,
    }),
  );
});

test("network retry keeps the task admission key and draft", async () => {
  api.createTask
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ status: "queued" });
  render(
    <AssistantTasksDialog assistant={assistant} canWrite onClose={() => {}} />,
  );
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
  expect(navigate).toHaveBeenCalledWith("/chat/child");
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
  expect(await screen.findByText(description.trim())).toHaveClass(
    "line-clamp-3",
  );
  fireEvent.click(
    screen.getByRole("button", { name: "assistants.inspectTask" }),
  );
  expect(navigate).toHaveBeenCalledWith("/chat/child");
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
