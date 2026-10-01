import { readFileSync } from "node:fs";

const source = readFileSync(
  new URL("../SessionListContent.tsx", import.meta.url),
  "utf8",
);
const taskPanel = readFileSync(
  new URL("../../ScheduledTaskPanel/index.tsx", import.meta.url),
  "utf8",
);

test("scheduled tasks and execution sessions belong to the task page instead of the chat list", () => {
  expect(source).not.toMatch(
    /ScheduledTaskSidebarItem|scheduledTaskApi|isScheduledTasksCollapsed/,
  );
  expect(source).toContain('navigate("/scheduled-tasks")');
  expect(source).toContain("!session.metadata?.scheduled_task_id");
  expect(taskPanel).toContain("scheduledTaskApi.list(");
  expect(taskPanel).toContain("<TaskSessionList");
});
