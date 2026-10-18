/** @vitest-environment jsdom */
import { act, cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import i18n from "../../../../i18n";
import { TaskSessionList } from "../TaskSessionList";
import type { TaskSession } from "../../../../types/scheduledTask";

const api = vi.hoisted(() => ({ getSessions: vi.fn() }));
vi.mock("../../../../services/api/scheduledTask", () => ({
  scheduledTaskApi: api,
}));
vi.mock("../../../../services/api/agent", () => ({
  agentApi: { list: vi.fn().mockResolvedValue({ agents: [] }) },
}));
vi.mock("../../../agent/AgentIcon", () => ({ AgentIcon: () => null }));
vi.mock("../../../common/InteractiveIcon", () => ({
  InteractiveIcon: ({ children }: { children: ReactNode }) => children,
}));

const session = (status: string): TaskSession => ({
  id: "child",
  name: "每分钟一个不重复数字",
  agent_id: "search",
  created_at: null,
  updated_at: null,
  is_active: status !== "success",
  metadata: { run_id: "run", run_status: status },
  unread_count: 0,
});
const response = (status: string) => ({ items: [session(status)], total: 1 });

beforeEach(async () => {
  vi.useFakeTimers();
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  api.getSessions.mockReset();
  await i18n.changeLanguage("zh");
});
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

async function show(taskId = "task") {
  await act(async () => {
    render(
      <MemoryRouter>
        <TaskSessionList taskId={taskId} taskName="任务" />
      </MemoryRouter>,
    );
  });
}

test("refreshes running executions into approval and completed states without reopening", async () => {
  api.getSessions
    .mockResolvedValueOnce(response("running"))
    .mockResolvedValueOnce(response("waiting_human"))
    .mockResolvedValue(response("success"));
  await show();
  expect(screen.getByText("运行中")).toBeVisible();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5_000);
  });
  expect(screen.getByText("等待确认")).toBeVisible();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5_000);
  });
  expect(screen.getByText("成功")).toBeVisible();
});

test("does not overlap requests and removes polling after leaving the list", async () => {
  let resolve!: (value: ReturnType<typeof response>) => void;
  api.getSessions.mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  await show();
  await act(async () => {
    await vi.advanceTimersByTimeAsync(15_000);
  });
  expect(api.getSessions).toHaveBeenCalledTimes(1);
  cleanup();
  await act(async () => {
    resolve(response("running"));
    await vi.advanceTimersByTimeAsync(5_000);
  });
  expect(api.getSessions).toHaveBeenCalledTimes(1);
});

test("pauses background polling and refreshes when the page becomes visible", async () => {
  api.getSessions.mockResolvedValue(response("running"));
  await show();
  const visibility = vi.spyOn(document, "visibilityState", "get");
  visibility.mockReturnValue("hidden");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10_000);
  });
  expect(api.getSessions).toHaveBeenCalledTimes(1);
  api.getSessions.mockResolvedValue(response("success"));
  visibility.mockReturnValue("visible");
  await act(async () => {
    document.dispatchEvent(new Event("visibilitychange"));
  });
  expect(screen.getByText("成功")).toBeVisible();
});

test("ignores a late response from the previous task", async () => {
  let resolve!: (value: ReturnType<typeof response>) => void;
  api.getSessions
    .mockReturnValueOnce(
      new Promise((done) => {
        resolve = done;
      }),
    )
    .mockResolvedValue(response("success"));
  const view = render(
    <MemoryRouter>
      <TaskSessionList taskId="old" taskName="旧任务" />
    </MemoryRouter>,
  );
  await act(async () => {
    view.rerender(
      <MemoryRouter>
        <TaskSessionList taskId="new" taskName="新任务" />
      </MemoryRouter>,
    );
  });
  await act(async () => {
    resolve(response("running"));
  });
  expect(screen.getByText("成功")).toBeVisible();
  expect(screen.queryByText("运行中")).toBeNull();
});
