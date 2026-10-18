import {
  dispatchWebSocketMessage,
  type RecommendQuestionsNotification,
  type TaskCompleteNotification,
  type UsageUpdatedNotification,
} from "../useWebSocket";

test("dispatches usage update notifications to their dedicated callback", () => {
  const updates: UsageUpdatedNotification[] = [];
  const message: UsageUpdatedNotification = {
    type: "usage:updated",
    data: { trace_id: "trace-1" },
  };

  dispatchWebSocketMessage(message, {
    onUsageUpdated: (notification) => updates.push(notification),
  });

  expect(updates).toEqual([message]);
});

test("ignores malformed usage update payloads", () => {
  const updates: UsageUpdatedNotification[] = [];

  dispatchWebSocketMessage(
    { type: "usage:updated", data: { trace_id: 123 } },
    { onUsageUpdated: (notification) => updates.push(notification) },
  );
  dispatchWebSocketMessage(
    { type: "usage:updated" },
    { onUsageUpdated: (notification) => updates.push(notification) },
  );

  expect(updates).toEqual([]);
});

test("dispatches recommendation notifications to their dedicated callback", () => {
  const recommendations: RecommendQuestionsNotification[] = [];
  const tasks: TaskCompleteNotification[] = [];
  const message: RecommendQuestionsNotification = {
    type: "recommend:questions",
    data: {
      session_id: "session-1",
      run_id: "run-1",
      questions: ["问题一？", "问题二？"],
    },
  };

  dispatchWebSocketMessage(message, {
    onRecommendQuestions: (notification) => recommendations.push(notification),
    onTaskComplete: (notification) => tasks.push(notification),
  });

  expect(recommendations).toEqual([message]);
  expect(tasks).toEqual([]);
});

test("keeps existing task completion dispatch compatible", () => {
  const tasks: TaskCompleteNotification[] = [];
  const message: TaskCompleteNotification = {
    type: "task:complete",
    data: {
      session_id: "session-1",
      run_id: "run-1",
      status: "completed",
    },
  };

  dispatchWebSocketMessage(message, {
    onTaskComplete: (notification) => tasks.push(notification),
  });

  expect(tasks).toEqual([message]);
});

test("ignores malformed recommendation payloads", () => {
  const recommendations: RecommendQuestionsNotification[] = [];

  dispatchWebSocketMessage(
    {
      type: "recommend:questions",
      data: {
        session_id: "session-1",
        run_id: "run-1",
        questions: "not-an-array",
      },
    },
    {
      onRecommendQuestions: (notification) =>
        recommendations.push(notification),
    },
  );

  expect(recommendations).toEqual([]);
});

// ---------------------------------------------------------------------------
// sandbox:presence 消息分发（presence 推送直达 store）
// ---------------------------------------------------------------------------

test("dispatches valid sandbox:presence messages", () => {
  const onSandboxPresence = vi.fn();
  dispatchWebSocketMessage(
    {
      type: "sandbox:presence",
      data: {
        machines: [
          {
            machine_id: "m1",
            name: "MacBook",
            platform: "darwin",
            version: "0.4.0",
            confirm_policy: "all",
            online: true,
            last_seen: 1700_000_000,
          },
        ],
        default_machine_id: "m1",
        legacy_online: false,
        revision: 100.5,
      },
    },
    { onSandboxPresence },
  );
  expect(onSandboxPresence).toHaveBeenCalledTimes(1);
  const notification = onSandboxPresence.mock.calls[0][0];
  expect(notification.data.machines[0].machine_id).toBe("m1");
  expect(notification.data.revision).toBe(100.5);
});

test("drops sandbox:presence with invalid payloads", () => {
  const onSandboxPresence = vi.fn();
  dispatchWebSocketMessage(
    { type: "sandbox:presence", data: { machines: "nope", revision: 1 } },
    { onSandboxPresence },
  );
  dispatchWebSocketMessage(
    { type: "sandbox:presence", data: { machines: [], revision: "bad" } },
    { onSandboxPresence },
  );
  dispatchWebSocketMessage(
    {
      type: "sandbox:presence",
      data: {
        machines: [{ name: "no-machine-id" }],
        revision: 2,
      },
    },
    { onSandboxPresence },
  );
  expect(onSandboxPresence).not.toHaveBeenCalled();
});

test("dispatches account read scopes and rejects malformed scopes", () => {
  const onSessionsRead = vi.fn();
  for (const data of [
    { session_id: "s1" },
    { project_id: "p1" },
    { scheduled_task_id: "t1" },
    {},
  ]) {
    dispatchWebSocketMessage(
      { type: "sessions:read", data },
      { onSessionsRead },
    );
  }
  expect(onSessionsRead.mock.calls.map(([scope]) => scope)).toEqual([
    { sessionId: "s1" },
    { projectId: "p1" },
    { scheduledTaskId: "t1" },
    {},
  ]);
  for (const data of [
    null,
    [],
    { session_id: 42 },
    { project_id: "" },
    { unknown: "field" },
  ]) {
    dispatchWebSocketMessage(
      { type: "sessions:read", data },
      { onSessionsRead },
    );
  }
  expect(onSessionsRead).toHaveBeenCalledTimes(4);
});

test("scheduled results bypass task completion and active-run reconciliation", () => {
  const onTaskComplete = vi.fn();
  const onScheduledResult = vi.fn();
  const data = {
    session_id: "parent",
    run_id: "scheduled-1",
    message_id: "scheduled-result:1",
    task_id: "t",
    task_name: "Numbers",
    content: "748196",
    timestamp: "2026-10-16T17:46:50Z",
  };
  dispatchWebSocketMessage(
    { type: "scheduled:result", data },
    { onTaskComplete, onScheduledResult },
  );
  expect(onScheduledResult).toHaveBeenCalledWith(data);
  expect(onTaskComplete).not.toHaveBeenCalled();
  dispatchWebSocketMessage(
    { type: "scheduled:result", data: { session_id: "parent" } },
    { onScheduledResult },
  );
  expect(onScheduledResult).toHaveBeenCalledTimes(1);
});

test("scheduled startup progress accepts empty content and bypasses human task completion", () => {
  const onTaskComplete = vi.fn();
  const onScheduledProgress = vi.fn();
  const data = {
    session_id: "parent",
    run_id: "scheduled-1",
    message_id: "scheduled-result:scheduled-1",
    task_id: "task",
    task_name: "Numbers",
    content: "",
    timestamp: "2026-10-16T17:46:50Z",
    updated_at: "2026-10-16T17:46:50Z",
    status: "running",
  };
  dispatchWebSocketMessage(
    { type: "scheduled:progress", data },
    { onScheduledProgress, onTaskComplete },
  );
  expect(onScheduledProgress).toHaveBeenCalledWith(data);
  expect(onTaskComplete).not.toHaveBeenCalled();
  dispatchWebSocketMessage(
    { type: "scheduled:progress", data: { ...data, status: "invalid" } },
    { onScheduledProgress },
  );
  expect(onScheduledProgress).toHaveBeenCalledTimes(1);
});

test("quota invalidation reuses the usage callback without requiring a trace", () => {
  const updates: unknown[] = [];
  dispatchWebSocketMessage(
    { type: "usage_quota_updated" },
    { onUsageUpdated: (message) => updates.push(message) },
  );
  expect(updates).toEqual([{ type: "usage_quota_updated" }]);
});
