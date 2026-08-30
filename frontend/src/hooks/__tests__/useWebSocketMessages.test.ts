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
