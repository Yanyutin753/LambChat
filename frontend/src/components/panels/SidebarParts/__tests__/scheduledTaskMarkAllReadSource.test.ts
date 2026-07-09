import { readFileSync } from "node:fs";
const source = readFileSync(
  new URL("../SessionListContent.tsx", import.meta.url),
  "utf8",
);

test("scheduled task mark-all-read clears the task summary unread count after success", () => {
  expect(source).toMatch(/handleScheduledTaskMarkAllRead/);
  expect(source).toMatch(/await onMarkAllRead\(\{ scheduledTaskId \}\)/);
  expect(source).toMatch(/setScheduledTasks\(\(prev\) =>/);
  expect(source).toMatch(/task\.id === scheduledTaskId/);
  expect(source).toMatch(/unread_count: 0/);
  expect(source).toMatch(
    /onMarkAllRead=\{\(\) =>\s+handleScheduledTaskMarkAllRead\(task\.id\)\s+\}/,
  );
});
