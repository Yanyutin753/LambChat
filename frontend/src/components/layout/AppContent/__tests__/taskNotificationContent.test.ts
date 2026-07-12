import { buildTaskNotificationCopy } from "../taskNotificationContent.ts";

test("uses the latest assistant reply as the completed notification summary", () => {
  const notification = buildTaskNotificationCopy({
    sessionName: "Design Review",
    status: "completed",
    successLabel: "Task completed",
    failureLabel: "Task failed",
    fallbackMessage: "Generic completion message",
    events: [
      {
        id: "1",
        event_type: "user:message",
        data: { content: "Can you review this?" },
        timestamp: "2026-04-25T10:00:00.000Z",
        run_id: "run-1",
      },
      {
        id: "2",
        event_type: "message:chunk",
        data: { content: "Sure, here are the three biggest risks." },
        timestamp: "2026-04-25T10:00:01.000Z",
        run_id: "run-1",
      },
      {
        id: "3",
        event_type: "message:chunk",
        data: { content: "\nFirst, the retry path can duplicate writes." },
        timestamp: "2026-04-25T10:00:02.000Z",
        run_id: "run-1",
      },
    ],
  });

  expect(notification).toEqual({
    title: "Design Review",
    body: "Sure, here are the three biggest risks. First, the retry path can duplicate writes.",
    statusLabel: "Task completed",
    isSuccess: true,
  });
});

test("falls back to the websocket message when no assistant summary is available", () => {
  const notification = buildTaskNotificationCopy({
    sessionName: "Bug Bash",
    status: "completed",
    successLabel: "Task completed",
    failureLabel: "Task failed",
    fallbackMessage: "The background task has finished.",
    events: [],
  });

  expect(notification.body).toBe("The background task has finished.");
});

test("uses the failure message for failed notifications", () => {
  const notification = buildTaskNotificationCopy({
    sessionName: "Deploy Check",
    status: "failed",
    successLabel: "Task completed",
    failureLabel: "Task failed",
    fallbackMessage: "Rate limit exceeded",
    events: [
      {
        id: "2",
        event_type: "message:chunk",
        data: { content: "This text should not be used for failures." },
        timestamp: "2026-04-25T10:00:01.000Z",
        run_id: "run-1",
      },
    ],
  });

  expect(notification).toEqual({
    title: "Deploy Check",
    body: "Rate limit exceeded",
    statusLabel: "Task failed",
    isSuccess: false,
  });
});

test("truncates very long notification summaries to a readable short preview", () => {
  const notification = buildTaskNotificationCopy({
    sessionName: "Long Research",
    status: "completed",
    successLabel: "Task completed",
    failureLabel: "Task failed",
    fallbackMessage:
      "This is a very long completion summary that should still be concise enough for a system notification instead of taking over the screen.",
    events: [],
  });

  expect(notification.body.endsWith("…")).toBe(true);
  expect(notification.body.length <= 96).toBe(true);
});
