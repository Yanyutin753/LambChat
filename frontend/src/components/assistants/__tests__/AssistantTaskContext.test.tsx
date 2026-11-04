/** @vitest-environment jsdom */
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  act,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { AssistantTaskContext } from "../AssistantTaskContext";
const { api, cancel, t } = vi.hoisted(() => ({
  api: { task: vi.fn(), reviewTask: vi.fn() },
  cancel: vi.fn(),
  t: (key: string) => key,
}));
vi.mock("../../../services/api/assistant", () => ({ assistantApi: api }));
vi.mock("../../../services/api/session", () => ({ sessionApi: { cancel } }));
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
test("review submits the displayed run and revision and refreshes the receipt", async () => {
  api.reviewTask.mockImplementation(async () => {
    api.task.mockResolvedValue({
      ...task,
      state: "accepted",
      review_revision: 5,
    });
  });
  render(<AssistantTaskContext {...props} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.acceptTask" }),
  );
  expect(
    await screen.findByText("assistants.taskStates.accepted"),
  ).toBeVisible();
  expect(api.reviewTask).toHaveBeenCalledWith("helper", "task", {
    run_id: "run",
    revision: 4,
    accepted: true,
  });
  expect(
    screen.queryByRole("button", { name: "assistants.acceptTask" }),
  ).toBeNull();
});
test("a stale review is disabled until current work is reloaded", async () => {
  api.reviewTask.mockRejectedValue(new Error("Review changed"));
  render(<AssistantTaskContext {...props} />);
  fireEvent.click(
    await screen.findByRole("button", { name: "assistants.acceptTask" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent("Review changed");
  expect(
    screen.getByRole("button", { name: "assistants.acceptTask" }),
  ).toBeDisabled();
  api.task.mockResolvedValue({
    ...task,
    run_id: "new-run",
    review_revision: 5,
  });
  fireEvent.click(screen.getByRole("button", { name: "common.refresh" }));
  await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
  api.reviewTask.mockResolvedValue({});
  fireEvent.click(
    screen.getByRole("button", { name: "assistants.rejectTask" }),
  );
  await waitFor(() =>
    expect(api.reviewTask).toHaveBeenLastCalledWith("helper", "task", {
      run_id: "new-run",
      revision: 5,
      accepted: false,
    }),
  );
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
test("focus refresh picks up work completed in the background", async () => {
  api.task.mockResolvedValueOnce({ ...task, state: "running" });
  render(<AssistantTaskContext {...props} />);
  await screen.findByText("assistants.taskStates.running");
  fireEvent(window, new Event("focus"));
  expect(
    await screen.findByRole("button", { name: "assistants.acceptTask" }),
  ).toBeVisible();
});
test("an older read cannot overwrite a completed review", async () => {
  let resolve!: (value: unknown) => void;
  render(<AssistantTaskContext {...props} />);
  await screen.findByRole("button", { name: "assistants.acceptTask" });
  api.task.mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done;
      }),
  );
  fireEvent(window, new Event("focus"));
  api.reviewTask.mockImplementation(async () => {
    api.task.mockResolvedValue({ ...task, state: "accepted" });
  });
  fireEvent.click(
    screen.getByRole("button", { name: "assistants.acceptTask" }),
  );
  await screen.findByText("assistants.taskStates.accepted");
  await act(async () => resolve(task));
  expect(
    screen.queryByRole("button", { name: "assistants.acceptTask" }),
  ).toBeNull();
});
