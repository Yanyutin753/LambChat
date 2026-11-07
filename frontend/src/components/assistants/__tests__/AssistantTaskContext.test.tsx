/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AssistantTaskContext } from "../AssistantTaskContext";
const { api, cancel, navigate, t } = vi.hoisted(() => ({
  api: { task: vi.fn(), reviewTask: vi.fn() },
  cancel: vi.fn(),
  navigate: vi.fn(),
  t: (key: string) => key,
}));
vi.mock("../../../services/api/assistant", () => ({ assistantApi: api }));
vi.mock("../../../services/api/session", () => ({ sessionApi: { cancel } }));
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t }) }));
const task = {
  id: "task",
  session_id: "child",
  description: "【Report】Check all sources",
  state: "awaiting_review",
  run_id: "run",
  review_revision: 4,
};
const props = {
  assistantId: "helper",
  taskId: "task",
  sessionId: "child",
  canWrite: true,
};
beforeEach(() => {
  api.task.mockResolvedValue(task);
});
afterEach(() => {
  cleanup();
  vi.resetAllMocks();
});
test("completed work offers its result without an acceptance ceremony", async () => {
  api.task.mockResolvedValue({ ...task, state: "completed" });
  render(<AssistantTaskContext {...props} />);
  expect(
    await screen.findByText("assistants.taskStates.completed"),
  ).not.toBeVisible();
  expect(
    screen.queryByRole("button", { name: "assistants.acceptTask" }),
  ).toBeNull();
  expect(
    screen.queryByRole("button", { name: "assistants.rejectTask" }),
  ).toBeNull();
});
test("readers see status without mutation controls", async () => {
  render(<AssistantTaskContext {...props} canWrite={false} />);
  expect(
    await screen.findByText("assistants.taskStates.awaiting_review"),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "assistants.acceptTask" }),
  ).toBeNull();
});
test("an unrelated conversation never exposes task actions or requirements", async () => {
  api.task.mockResolvedValue({ ...task, session_id: "foreign" });
  render(<AssistantTaskContext {...props} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "assistants.conversationMismatch",
  );
  expect(screen.queryByText(task.description)).toBeNull();
  expect(
    screen.queryByRole("button", { name: "assistants.acceptTask" }),
  ).toBeNull();
});
test("stopping work is fenced to its visible run", async () => {
  api.task.mockResolvedValue({ ...task, state: "running" });
  cancel.mockResolvedValue({});
  render(<AssistantTaskContext {...props} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.stopTask" }),
  );
  await waitFor(() => expect(cancel).toHaveBeenCalledWith("child", "run"));
});
test("focus refresh picks up completed work without a decision prompt", async () => {
  api.task.mockResolvedValueOnce({ ...task, state: "running" });
  render(<AssistantTaskContext {...props} />);
  await screen.findByText("assistants.taskStates.running");
  api.task.mockResolvedValue({ ...task, state: "completed" });
  fireEvent(window, new Event("focus"));
  expect(
    await screen.findByText("assistants.taskStates.completed"),
  ).not.toBeVisible();
  expect(
    screen.queryByRole("button", { name: "assistants.acceptTask" }),
  ).toBeNull();
});

test("a work result returns to its originating Chief conversation", async () => {
  api.task.mockResolvedValue({
    ...task,
    source_session_id: "chief-chat",
    source_assistant_id: "chief",
  });
  render(<AssistantTaskContext {...props} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.returnToSource" }),
  );
  expect(navigate).toHaveBeenCalledWith("/assistants/chief/chat/chief-chat");
});

test("completed task details stay collapsed until requested", async () => {
  api.task.mockResolvedValue({ ...task, state: "completed" });
  render(<AssistantTaskContext {...props} />);
  const status = await screen.findByText("assistants.taskStates.completed");
  expect(status.closest("details")).not.toHaveAttribute("open");
  expect(status).not.toBeVisible();
  const details = status.closest("details")!;
  details.open = true;
  fireEvent(details, new Event("toggle"));
  expect(status).toBeVisible();
  expect(screen.getByText(task.description)).toBeVisible();
});
